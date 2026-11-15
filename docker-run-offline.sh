#!/usr/bin/env bash
# AirCursor Offline Docker Launcher
cd "$(dirname "$0")"

echo "======================================================================"
echo "          AirCursor Multi-Arch Docker Container Launcher"
echo "======================================================================"

# Build image if not present
if ! docker image inspect aircursor:latest >/dev/null 2>&1; then
    echo "[*] Building local aircursor:latest image..."
    docker build -t aircursor:latest .
fi

echo "[*] Launching container 'aircursor'..."
docker run -d \
  --name aircursor \
  --restart unless-stopped \
  -p 8765:8765 \
  -p 4242:4242/udp \
  -p 6080:6080 \
  -e MODE=synthetic \
  -e AUTORUN=true \
  aircursor:latest

echo "[+] AirCursor container started."
echo "    - Web Remote: http://localhost:8765"
echo "    - noVNC:      http://localhost:6080/vnc.html"
echo "    - UDP Port:   4242/udp"
