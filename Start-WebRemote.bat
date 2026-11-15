@echo off
title AirCursor Web Remote & API Server
cd /d "%~dp0"

echo ======================================================================
echo                 AirCursor Web Remote & Telemetry Server
echo ======================================================================
echo Starting server on http://localhost:8765 ...
echo OpenTrack UDP listener on port 4242 ...
echo.

start "" "http://localhost:8765"
python server.py --port 8765 --udp-port 4242 --mode synthetic

pause
