"""AirCursor Network Pairing & QR Code Generator.

Discovers local network IPv4 address and generates QR codes in:
- Terminal ASCII/Unicode format (compact half-block or full block)
- Scalable Vector Graphics (SVG) format for web and GUI integration
- Interactive HTML format with glassmorphic styling
Pure Python implementation with zero mandatory external dependencies.
"""

from __future__ import annotations

import socket
from typing import List, Optional, Tuple

try:
    import qrcode
    _HAS_QRCODE_PKG = True
except ImportError:
    qrcode = None
    _HAS_QRCODE_PKG = False


def get_local_ip() -> str:
    """Discovers machine's local LAN IPv4 address (e.g. 192.168.x.x, 10.x.x.x).
    
    Uses UDP socket routing trick (zero packets sent) to determine the real
    active network interface IP, falling back to hostname lookup or loopback.
    """
    # Strategy 1: UDP routing probe (standard, most reliable cross-platform)
    for probe_dest in [("10.255.255.255", 1), ("8.8.8.8", 80), ("1.1.1.1", 80)]:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.settimeout(0.3)
                s.connect(probe_dest)
                ip = s.getsockname()[0]
                if ip and not ip.startswith("127.") and not ip.startswith("169.254."):
                    return ip
        except Exception:
            continue

    # Strategy 2: Hostname resolution with candidate filtering
    try:
        hostname = socket.gethostname()
        candidates = socket.gethostbyname_ex(hostname)[2]
        # Prefer private RFC 1918 addresses
        for ip in candidates:
            if ip.startswith("192.168.") or ip.startswith("10."):
                return ip
        for ip in candidates:
            if ip.startswith("172."):
                parts = ip.split(".")
                if len(parts) > 1 and 16 <= int(parts[1]) <= 31:
                    return ip
        for ip in candidates:
            if not ip.startswith("127.") and not ip.startswith("169.254."):
                return ip
    except Exception:
        pass

    return "127.0.0.1"


def get_pairing_url(port: int = 8765, ip: Optional[str] = None) -> str:
    """Returns the HTTP URL to access the mobile web remote."""
    host_ip = ip or get_local_ip()
    return f"http://{host_ip}:{port}"


# -----------------------------------------------------------------------------
# Pure-Python QR Code Engine (Zero External Dependencies)
# ISO/IEC 18004 Compliant Minimal Matrix Generator
# -----------------------------------------------------------------------------

GF_EXP = [0] * 512
GF_LOG = [0] * 256
_x = 1
for _i in range(255):
    GF_EXP[_i] = _x
    GF_LOG[_x] = _i
    _x <<= 1
    if _x & 0x100:
        _x ^= 0x11D
for _i in range(255, 512):
    GF_EXP[_i] = GF_EXP[_i - 255]


def _gf_mul(x: int, y: int) -> int:
    if x == 0 or y == 0:
        return 0
    return GF_EXP[GF_LOG[x] + GF_LOG[y]]


def _rs_poly_mul(p1: List[int], p2: List[int]) -> List[int]:
    out = [0] * (len(p1) + len(p2) - 1)
    for i, a in enumerate(p1):
        for j, b in enumerate(p2):
            out[i + j] ^= _gf_mul(a, b)
    return out


def _rs_generator_poly(num_ec: int) -> List[int]:
    poly = [1]
    for i in range(num_ec):
        poly = _rs_poly_mul(poly, [1, GF_EXP[i]])
    return poly


def _rs_calc_ec(data: List[int], num_ec: int) -> List[int]:
    gen = _rs_generator_poly(num_ec)
    rem = list(data) + [0] * num_ec
    for i in range(len(data)):
        lead = rem[i]
        if lead != 0:
            for j, g in enumerate(gen):
                rem[i + j] ^= _gf_mul(g, lead)
    return rem[len(data):]


# Version specifications: (version, size, data_codewords, ec_codewords, ec_blocks, align_coord)
# Supports versions 1 through 5, covering up to 134 bytes (easily accommodates pairing URLs)
_VERSION_SPECS = [
    # V1: 21x21, EC M: 16 data, 10 EC (1 block)
    (1, 21, 16, 10, [(1, 16, 10)], []),
    # V2: 25x25, EC M: 28 data, 16 EC (1 block)
    (2, 25, 28, 16, [(1, 28, 16)], [18]),
    # V3: 29x29, EC M: 44 data, 26 EC (1 block)
    (3, 29, 44, 26, [(1, 44, 26)], [22]),
    # V4: 33x33, EC M: 64 data, 36 EC (2 blocks: 32 data, 18 EC each)
    (4, 33, 64, 36, [(2, 32, 18)], [26]),
    # V5: 37x37, EC M: 86 data, 48 EC (2 blocks: 43 data, 24 EC each)
    (5, 37, 86, 48, [(2, 43, 24)], [30]),
]


def _calc_format_info(ec_level: str = "M", mask: int = 0) -> int:
    # EC bits: L=1, M=0, Q=3, H=2
    ec_map = {"L": 1, "M": 0, "Q": 3, "H": 2}
    data = (ec_map[ec_level] << 3) | mask
    rem = data << 10
    g = 0x537
    for i in range(14, 9, -1):
        if rem & (1 << i):
            rem ^= g << (i - 10)
    return ((data << 10) | rem) ^ 0x5412


def _pure_python_qr(data: str) -> List[List[bool]]:
    """Encodes ASCII string into a 2D boolean QR matrix using pure Python."""
    raw_bytes = data.encode("latin-1", errors="replace")
    payload_len = len(raw_bytes)

    # Pick smallest version that fits payload in Byte mode
    # Byte mode overhead: 4-bit mode indicator (0100) + 8-bit count indicator = 12 bits
    spec = None
    for v_spec in _VERSION_SPECS:
        version, size, data_cw, ec_cw, blocks, align = v_spec
        # Max data capacity in bytes: data_cw - 2 (for 12 bits header + terminator)
        if payload_len <= (data_cw - 2):
            spec = v_spec
            break

    if spec is None:
        # Fallback to largest supported version
        spec = _VERSION_SPECS[-1]

    version, size, data_cw, ec_cw, blocks, align_coords = spec

    # 1. Bitstream assembly: Byte mode
    bits: List[int] = []

    def append_bits(val: int, count: int):
        for i in range(count - 1, -1, -1):
            bits.append((val >> i) & 1)

    # Mode 0100 (Byte mode)
    append_bits(0b0100, 4)
    # Character count indicator (8 bits for versions 1-9 in Byte mode)
    append_bits(payload_len, 8)
    # Data bytes
    for b in raw_bytes:
        append_bits(b, 8)
    # Terminator (up to 4 zero bits)
    capacity_bits = data_cw * 8
    term_len = min(4, capacity_bits - len(bits))
    append_bits(0, term_len)
    # Pad to byte boundary
    pad_len = (8 - (len(bits) % 8)) % 8
    append_bits(0, pad_len)
    # Pad bytes 0xEC and 0x11
    pad_bytes = [0xEC, 0x11]
    pad_idx = 0
    while len(bits) < capacity_bits:
        append_bits(pad_bytes[pad_idx % 2], 8)
        pad_idx += 1

    # Convert bitstream to bytes
    data_bytes: List[int] = []
    for i in range(0, len(bits), 8):
        byte_val = 0
        for b in bits[i : i + 8]:
            byte_val = (byte_val << 1) | b
        data_bytes.append(byte_val)

    # 2. Divide data into EC blocks and calculate Reed-Solomon codewords
    block_data: List[List[int]] = []
    block_ec: List[List[int]] = []
    cw_offset = 0

    for num_blocks, b_data_len, b_ec_len in blocks:
        for _ in range(num_blocks):
            sub_data = data_bytes[cw_offset : cw_offset + b_data_len]
            cw_offset += b_data_len
            ec = _rs_calc_ec(sub_data, b_ec_len)
            block_data.append(sub_data)
            block_ec.append(ec)

    # 3. Interleave data codewords then EC codewords
    final_codewords: List[int] = []
    max_data_len = max(len(b) for b in block_data)
    for col in range(max_data_len):
        for b in block_data:
            if col < len(b):
                final_codewords.append(b[col])

    max_ec_len = max(len(b) for b in block_ec)
    for col in range(max_ec_len):
        for b in block_ec:
            if col < len(b):
                final_codewords.append(b[col])

    # Convert final codewords into bit sequence
    final_bits: List[int] = []
    for cw in final_codewords:
        for i in range(7, -1, -1):
            final_bits.append((cw >> i) & 1)

    # 4. Initialize matrix and mark reserved areas
    modules: List[List[Optional[bool]]] = [[None] * size for _ in range(size)]
    reserved: List[List[bool]] = [[False] * size for _ in range(size)]

    # Finder patterns at (0, 0), (0, size-7), (size-7, 0)
    def add_finder(r: int, c: int):
        for dr in range(-1, 8):
            for dc in range(-1, 8):
                nr, nc = r + dr, c + dc
                if 0 <= nr < size and 0 <= nc < size:
                    reserved[nr][nc] = True
                    if 0 <= dr <= 6 and 0 <= dc <= 6:
                        is_dark = (
                            dr in (0, 6)
                            or dc in (0, 6)
                            or (2 <= dr <= 4 and 2 <= dc <= 4)
                        )
                        modules[nr][nc] = is_dark
                    else:
                        modules[nr][nc] = False

    add_finder(0, 0)
    add_finder(0, size - 7)
    add_finder(size - 7, 0)

    # Timing patterns
    for i in range(8, size - 8):
        is_dark = i % 2 == 0
        if not reserved[6][i]:
            modules[6][i] = is_dark
            reserved[6][i] = True
        if not reserved[i][6]:
            modules[i][6] = is_dark
            reserved[i][6] = True

    # Alignment pattern(s)
    for ac in align_coords:
        # For small versions with single alignment coordinate
        ar, ac = ac, ac
        if not reserved[ar][ac]:
            for dr in range(-2, 3):
                for dc in range(-2, 3):
                    nr, nc = ar + dr, ac + dc
                    reserved[nr][nc] = True
                    modules[nr][nc] = max(abs(dr), abs(dc)) in (0, 2)

    # Dark module
    dark_r, dark_c = 4 * version + 9, 8
    modules[dark_r][dark_c] = True
    reserved[dark_r][dark_c] = True

    # Format info reserved areas
    for i in range(9):
        reserved[8][i] = True
        reserved[i][8] = True
        if i < 8:
            reserved[8][size - 1 - i] = True
            reserved[size - 1 - i][8] = True

    # 5. Place data bits in zig-zag 2-column tracks right-to-left
    bit_idx = 0
    num_final_bits = len(final_bits)
    col = size - 1
    upward = True

    # Mask function 0: (row + col) % 2 == 0
    def mask_fn(r: int, c: int) -> bool:
        return (r + c) % 2 == 0

    while col > 0:
        if col == 6:  # Skip vertical timing pattern column
            col -= 1
        rows = range(size - 1, -1, -1) if upward else range(size)
        for r in rows:
            for c in (col, col - 1):
                if not reserved[r][c]:
                    bit_val = final_bits[bit_idx] if bit_idx < num_final_bits else 0
                    bit_idx += 1
                    # Invert module if mask condition is met
                    if mask_fn(r, c):
                        bit_val ^= 1
                    modules[r][c] = bool(bit_val)
        col -= 2
        upward = not upward

    # 6. Format info placement (EC M, Mask 0)
    format_bits = _calc_format_info(ec_level="M", mask=0)
    for i in range(15):
        bit_val = bool((format_bits >> (14 - i)) & 1)
        # Around top-left
        if i < 6:
            modules[8][i] = bit_val
        elif i == 6:
            modules[8][7] = bit_val
        elif i == 7:
            modules[8][8] = bit_val
        elif i == 8:
            modules[7][8] = bit_val
        else:
            modules[14 - i][8] = bit_val

        # Around top-right and bottom-left
        if i < 8:
            modules[size - 1 - i][8] = bit_val
        else:
            modules[8][size - 15 + i] = bit_val

    # Ensure all elements are booleans
    return [[bool(cell) for cell in row] for row in modules]


def generate_qr_matrix(data: str) -> List[List[bool]]:
    """Generates a 2D boolean matrix for the given string (True=black, False=white).
    
    If the optional 'qrcode' library is installed, it is leveraged for performance;
    otherwise, the robust built-in pure Python QR engine is utilized automatically.
    """
    if _HAS_QRCODE_PKG:
        try:
            qr = qrcode.QRCode(
                version=None,
                error_correction=qrcode.constants.ERROR_CORRECT_M,
                box_size=1,
                border=0,
            )
            qr.add_data(data)
            qr.make(fit=True)
            return [[bool(cell) for cell in row] for row in qr.modules]
        except Exception:
            pass

    return _pure_python_qr(data)


# -----------------------------------------------------------------------------
# Output Renderers: ASCII, SVG, HTML
# -----------------------------------------------------------------------------

def matrix_to_ascii(
    matrix: List[List[bool]],
    border: int = 2,
    compact: bool = True,
    invert: bool = False,
) -> str:
    """Renders QR matrix as text using Unicode half-blocks or full blocks.
    
    When compact=True (default), packs two vertical modules per character using
    Unicode half-blocks (▀, ▄, █, space), yielding a perfectly square, high-density
    code suitable for modern terminals.
    """
    n = len(matrix)
    padded_size = n + 2 * border
    # Pad matrix with False (white quiet zone)
    padded = [[False] * padded_size for _ in range(border)]
    for row in matrix:
        padded.append([False] * border + list(row) + [False] * border)
    for _ in range(border):
        padded.append([False] * padded_size)

    lines: List[str] = []

    if compact:
        # Two rows per terminal line
        for y in range(0, len(padded), 2):
            r1 = padded[y]
            r2 = padded[y + 1] if y + 1 < len(padded) else [False] * len(r1)
            line_chars = []
            for c1, c2 in zip(r1, r2):
                if invert:
                    c1, c2 = not c1, not c2
                # In standard dark terminal:
                # White module is represented by foreground block character '█'
                # Black module is represented by background/space ' '
                if not c1 and not c2:
                    line_chars.append("█")
                elif c1 and not c2:
                    line_chars.append("▄")
                elif not c1 and c2:
                    line_chars.append("▀")
                else:
                    line_chars.append(" ")
            lines.append("".join(line_chars))
    else:
        # Full blocks (2 chars per module for 1:1 aspect ratio)
        for row in padded:
            line_chars = []
            for cell in row:
                val = not cell if invert else cell
                line_chars.append("  " if val else "██")
            lines.append("".join(line_chars))

    return "\n".join(lines)


def matrix_to_svg(
    matrix: List[List[bool]],
    box_size: int = 10,
    border: int = 4,
    fg: str = "#00f0ff",
    bg: str = "#0b101b",
) -> str:
    """Renders QR matrix as an ultra-crisp SVG string with dark-mode aesthetic."""
    n = len(matrix)
    total_size = (n + 2 * border) * box_size
    path_cmds = []

    for r in range(n):
        y = (r + border) * box_size
        for c in range(n):
            if matrix[r][c]:
                x = (c + border) * box_size
                path_cmds.append(f"M{x},{y}h{box_size}v{box_size}h-{box_size}z")

    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {total_size} {total_size}" '
        f'width="{total_size}" height="{total_size}" shape-rendering="crispEdges">\n'
        f'  <rect width="100%" height="100%" fill="{bg}"/>\n'
        f'  <path d="{" ".join(path_cmds)}" fill="{fg}"/>\n'
        f'</svg>'
    )
    return svg


def matrix_to_html(
    matrix: List[List[bool]],
    url: str,
    title: str = "AirCursor Mobile Remote Pairing",
) -> str:
    """Renders a standalone, responsive pairing card with neon glow styling."""
    svg_code = matrix_to_svg(matrix, box_size=8, border=3, fg="#00f0ff", bg="#080c14")
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <style>
    body {{
      margin: 0;
      padding: 24px;
      background: #050811;
      color: #f1f5f9;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      min-height: 90vh;
    }}
    .card {{
      background: rgba(15, 23, 42, 0.75);
      backdrop-filter: blur(16px);
      border: 1px solid rgba(56, 189, 248, 0.25);
      box-shadow: 0 10px 40px rgba(0, 240, 255, 0.15);
      border-radius: 20px;
      padding: 32px 28px;
      text-align: center;
      max-width: 360px;
      width: 100%;
    }}
    .title {{
      font-size: 20px;
      font-weight: 700;
      letter-spacing: 0.5px;
      color: #38bdf8;
      margin: 0 0 8px 0;
    }}
    .subtitle {{
      font-size: 13px;
      color: #94a3b8;
      margin: 0 0 20px 0;
    }}
    .qr-box {{
      background: #080c14;
      border: 1px solid rgba(56, 189, 248, 0.3);
      border-radius: 14px;
      padding: 12px;
      display: inline-block;
      margin-bottom: 20px;
      box-shadow: 0 0 20px rgba(0, 240, 255, 0.1);
    }}
    .qr-box svg {{
      display: block;
      max-width: 100%;
      height: auto;
    }}
    .url-badge {{
      display: block;
      background: rgba(56, 189, 248, 0.1);
      border: 1px solid rgba(56, 189, 248, 0.3);
      color: #38bdf8;
      padding: 10px 14px;
      border-radius: 10px;
      font-family: monospace;
      font-size: 14px;
      text-decoration: none;
      word-break: break-all;
      transition: all 0.2s ease;
    }}
    .url-badge:hover {{
      background: rgba(56, 189, 248, 0.2);
      border-color: #38bdf8;
      color: #ffffff;
      box-shadow: 0 0 12px rgba(56, 189, 248, 0.4);
    }}
    .instruction {{
      margin-top: 14px;
      font-size: 12px;
      color: #64748b;
    }}
  </style>
</head>
<body>
  <div class="card">
    <h2 class="title">{title}</h2>
    <p class="subtitle">Scan with phone camera (iPhone / Android) to connect</p>
    <div class="qr-box">
      {svg_code}
    </div>
    <a class="url-badge" href="{url}" target="_blank">{url}</a>
    <p class="instruction">Ensure phone is connected to the same Wi-Fi / Local Network.</p>
  </div>
</body>
</html>"""
    return html


# -----------------------------------------------------------------------------
# High-Level PairingQR Helper Class
# -----------------------------------------------------------------------------

class PairingQR:
    """Convenience helper encapsulating host discovery and multi-format QR generation."""

    def __init__(self, port: int = 8765, ip: Optional[str] = None):
        self._ip = ip or get_local_ip()
        self._port = int(port)
        self._url = f"http://{self._ip}:{self._port}"
        self._matrix: Optional[List[List[bool]]] = None

    @property
    def ip(self) -> str:
        return self._ip

    @property
    def port(self) -> int:
        return self._port

    @property
    def url(self) -> str:
        return self._url

    @property
    def matrix(self) -> List[List[bool]]:
        if self._matrix is None:
            self._matrix = generate_qr_matrix(self._url)
        return self._matrix

    def to_ascii(
        self, border: int = 2, compact: bool = True, invert: bool = False
    ) -> str:
        return matrix_to_ascii(self.matrix, border=border, compact=compact, invert=invert)

    def to_svg(
        self,
        box_size: int = 10,
        border: int = 4,
        fg: str = "#00f0ff",
        bg: str = "#0b101b",
    ) -> str:
        return matrix_to_svg(self.matrix, box_size=box_size, border=border, fg=fg, bg=bg)

    def to_html(self, title: str = "AirCursor Mobile Remote Pairing") -> str:
        return matrix_to_html(self.matrix, self._url, title=title)

    def to_dict(self) -> dict:
        return {
            "url": self._url,
            "ip": self._ip,
            "port": self._port,
            "qr_ascii": self.to_ascii(),
            "qr_svg": self.to_svg(),
        }

    def print_terminal(self) -> None:
        """Prints a nicely styled banner with ASCII QR code to terminal."""
        print(f"\n\033[96m[AirCursor Mobile Remote Pairing]\033[0m")
        print(f"URL: \033[92m{self._url}\033[0m\n")
        print(self.to_ascii())
        print(f"\nScan the QR code above or visit {self._url} on your phone.\n")
