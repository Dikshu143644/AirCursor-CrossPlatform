"""Local pairing URL and optional QR rendering helpers."""
from urllib.parse import urlsplit, urlunsplit

def pairing_url(base_url: str, token: str) -> str:
    """Store the bearer token in the URL fragment, never in the HTTP request."""
    parts = urlsplit(base_url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ValueError("base_url must be an absolute HTTP(S) URL")
    if not token:
        raise ValueError("token cannot be empty")
    return urlunsplit((parts.scheme, parts.netloc, parts.path or "/", parts.query, token))

def terminal_qr(url: str) -> str:
    """Render a QR code as terminal text; requires the optional qrcode package."""
    try:
        import qrcode
    except ImportError as exc:
        raise RuntimeError("Install aircursor_core[qr] to render QR codes") from exc
    code = qrcode.QRCode(border=1)
    code.add_data(url)
    code.make(fit=True)
    matrix = code.get_matrix()
    return "\n".join("".join("██" if cell else "  " for cell in row) for row in matrix)
