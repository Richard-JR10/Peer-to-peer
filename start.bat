@echo off
REM ============================================================
REM  PDC P2P - Launch script
REM  Edit the values below before running.
REM  Run: start.bat
REM ============================================================

set PEER_ID=Richard
set PEER_ADVERTISE_HOST=100.102.71.92
set PEER_PORT=9000
set DISCOVERY_PORT=9999
set DATA_DIR=data\peer1
set BOOTSTRAP_PEERS=100.80.161.84:9000
set PEER_PASSPHRASE=pdc-demo-key

REM ============================================================

set PYTHONPATH=src
set PEER_HOST=0.0.0.0

if not exist "%DATA_DIR%" mkdir "%DATA_DIR%"

echo [PDC] Starting peer.py in a new window...
start "PDC peer.py" cmd /k python -m peer

echo [PDC] Starting web frontend via Docker...
docker compose up -d --build

echo.
echo  Peer window: watch peer.py logs there (close it to stop the peer)
echo  Open http://localhost:8080 in your browser
echo  To stop: close the peer.py window  ^&  docker compose down
echo.
pause
