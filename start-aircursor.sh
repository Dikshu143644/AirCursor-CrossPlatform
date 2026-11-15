#!/usr/bin/env bash
# AirCursor Linux / macOS Launcher
cd "$(dirname "$0")"

echo "======================================================================"
echo "                   AirCursor Cross-Platform Daemon"
echo "======================================================================"

if [[ "$OSTYPE" == "linux"* ]]; then
    python3 linux/main_linux.py "$@"
else
    python3 server.py "$@"
fi
