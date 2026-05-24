@echo off
REM ============================================================
REM  PDC P2P - Launch script
REM  Edit the values below before running.
REM  Run: start.bat
REM ============================================================

set PEER_ID=Richard
set PEER_ADVERTISE_HOST=192.168.0.135
set PEER_PORT=9000
set DISCOVERY_PORT=9999
set DATA_DIR=data\peer1

REM ============================================================

set PYTHONPATH=src
set PEER_HOST=0.0.0.0

echo [PDC] Starting peer.py (P2P backend)...
if not exist "%DATA_DIR%" mkdir "%DATA_DIR%"
start /B python -m peer > peer.log 2>&1

echo [PDC] Starting web frontend via Docker...
docker compose up -d --build

echo.
echo  Open http://localhost:8080 in your browser
echo  Peer log: peer.log
echo  To stop:  docker compose down  ^&  taskkill /F /IM python.exe
echo.
pause
