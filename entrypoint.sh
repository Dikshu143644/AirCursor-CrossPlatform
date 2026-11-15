#!/bin/bash
# ==============================================================================
# AirCursor Container Entrypoint
# Initializes Virtual Display (Xvfb + x11vnc + noVNC) & Headless Server Daemon
# ==============================================================================

set -e

DISPLAY="${DISPLAY:-:99}"
SCREEN_WIDTH="${SCREEN_WIDTH:-1920}"
SCREEN_HEIGHT="${SCREEN_HEIGHT:-1080}"
SCREEN_DEPTH="${SCREEN_DEPTH:-24}"
ENABLE_NOVNC="${ENABLE_NOVNC:-false}"
VNC_PASSWORD="${VNC_PASSWORD:-}"
VNC_PASSFILE=""
NOVNC_PORT="${NOVNC_PORT:-6080}"
VNC_PORT="${VNC_PORT:-5900}"
HTTP_PORT="${HTTP_PORT:-8765}"
UDP_PORT="${UDP_PORT:-4242}"
MODE="${MODE:-synthetic}"
AUTORUN="${AUTORUN:-true}"

export DISPLAY
export SCREEN_WIDTH
export SCREEN_HEIGHT
export HTTP_PORT
export UDP_PORT
export MODE
export AUTORUN
export ENABLE_NOVNC

XVFB_PID=""
VNC_PID=""
NOVNC_PID=""
SERVER_PID=""

cleanup() {
    echo "[*] AirCursor container shutting down, terminating child processes..."
    if [ -n "$SERVER_PID" ]; then
        kill -TERM "$SERVER_PID" 2>/dev/null || true
    fi
    if [ -n "$NOVNC_PID" ]; then
        kill -TERM "$NOVNC_PID" 2>/dev/null || true
    fi
    if [ -n "$VNC_PID" ]; then
        kill -TERM "$VNC_PID" 2>/dev/null || true
    fi
    if [ -n "$XVFB_PID" ]; then
        kill -TERM "$XVFB_PID" 2>/dev/null || true
    fi
    # Remove transient VNC credentials and X11 lock files.
    if [ -n "$VNC_PASSFILE" ]; then rm -f "$VNC_PASSFILE"; fi
    rm -f /tmp/.X99-lock /tmp/.X11-unix/X99 2>/dev/null || true
    exit 0
}

trap cleanup SIGTERM SIGINT

# ------------------------------------------------------------------------------
# 1. Virtual Display Server (Xvfb)
# ------------------------------------------------------------------------------
if command -v Xvfb >/dev/null 2>&1; then
    echo "[*] Initializing Xvfb Virtual Framebuffer on $DISPLAY (${SCREEN_WIDTH}x${SCREEN_HEIGHT}x${SCREEN_DEPTH})..."
    rm -f /tmp/.X99-lock /tmp/.X11-unix/X99 2>/dev/null || true
    Xvfb "$DISPLAY" -screen 0 "${SCREEN_WIDTH}x${SCREEN_HEIGHT}x${SCREEN_DEPTH}" -ac +extension GLX +render -noreset &
    XVFB_PID=$!
    sleep 1
else
    echo "[!] Warning: Xvfb not found. Running in pure headless console mode."
fi

# ------------------------------------------------------------------------------
# 2. Virtual VNC Server & noVNC WebSocket Bridge (Port 6080)
# ------------------------------------------------------------------------------
if [ "$ENABLE_NOVNC" = "true" ] && command -v x11vnc >/dev/null 2>&1; then
    if [ -z "$VNC_PASSWORD" ]; then
        echo "[!] Refusing to start noVNC without VNC_PASSWORD. Keep ENABLE_NOVNC=false or set a strong password."
        exit 1
    fi
    VNC_PASSFILE="$(mktemp /tmp/aircursor-vnc-pass.XXXXXX)"
    chmod 600 "$VNC_PASSFILE"
    x11vnc -storepasswd "$VNC_PASSWORD" "$VNC_PASSFILE" >/dev/null
    unset VNC_PASSWORD
    echo "[*] Starting password-protected x11vnc on port $VNC_PORT..."
    x11vnc -display "$DISPLAY" -forever -shared -rfbport "$VNC_PORT" -rfbauth "$VNC_PASSFILE" -quiet &
    VNC_PID=$!
    sleep 0.5

    NOVNC_DIR=""
    for d in /usr/share/novnc /opt/novnc; do
        if [ -d "$d" ]; then
            NOVNC_DIR="$d"
            break
        fi
    done

    if command -v websockify >/dev/null 2>&1 && [ -n "$NOVNC_DIR" ]; then
        echo "[*] Starting noVNC HTML5 WebSocket bridge on port $NOVNC_PORT (password protected)..."
        websockify --web "$NOVNC_DIR" "$NOVNC_PORT" "localhost:$VNC_PORT" >/dev/null 2>&1 &
        NOVNC_PID=$!
    fi
else
    echo "[*] noVNC is disabled (set ENABLE_NOVNC=true and VNC_PASSWORD only on a trusted private network)."
fi

# ------------------------------------------------------------------------------
# 3. Launch AirCursor Daemon
# ------------------------------------------------------------------------------
echo "[+] Starting AirCursor Cross-Platform Service..."
echo "    - Web Remote & REST API: http://0.0.0.0:$HTTP_PORT"
echo "    - OpenTrack/AirPods UDP: 0.0.0.0:$UDP_PORT/udp"
if [ "$ENABLE_NOVNC" = "true" ]; then
    echo "    - noVNC Web Display:     http://0.0.0.0:$NOVNC_PORT (password protected)"
else
    echo "    - noVNC Web Display:     disabled"
fi
echo "    - Mode:                  $MODE"

if [ $# -gt 0 ]; then
    "$@" &
    SERVER_PID=$!
else
    python3 /app/server.py --port "$HTTP_PORT" --udp-port "$UDP_PORT" --mode "$MODE" &
    SERVER_PID=$!
fi

# Wait for process termination
wait "$SERVER_PID"
