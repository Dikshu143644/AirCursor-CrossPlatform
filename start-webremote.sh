#!/usr/bin/env bash
# AirCursor Web Remote & API Server Launcher
cd "$(dirname "$0")"

echo "======================================================================"
echo "              AirCursor Web Remote & API Server"
echo "======================================================================"
echo "Starting Web Remote on http://localhost:8765 ..."
echo "Starting OpenTrack UDP listener on port 4242/udp ..."

python3 server.py --port 8765 --udp-port 4242 "$@"
