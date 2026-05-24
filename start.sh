#!/usr/bin/env bash
set -e

# ============================================================
#  PDC P2P - Launch script
#  Edit the values below before running.
#  Run: chmod +x start.sh && ./start.sh
# ============================================================

export PEER_ID="peer1"
export PEER_ADVERTISE_HOST="YOUR_LAN_IP_HERE"
export PEER_PORT="9000"
export DISCOVERY_PORT="9999"
export DATA_DIR="data/peer1"

# ============================================================

export PYTHONPATH="src"
export PEER_HOST="0.0.0.0"

mkdir -p "$DATA_DIR"

echo "[PDC] Starting peer.py (P2P backend)..."
python3 -m peer > peer.log 2>&1 &
PEER_PID=$!
echo "[PDC] peer.py started (PID $PEER_PID)"

echo "[PDC] Starting web frontend via Docker..."
docker compose up -d --build

echo ""
echo "  Open http://localhost:8080 in your browser"
echo "  Peer log: peer.log  (PID $PEER_PID)"
echo "  To stop:  docker compose down && kill $PEER_PID"
