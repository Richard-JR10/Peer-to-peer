# Trackerless Peer-to-Peer File Sharing

A decentralized file sharing application for local networks. Each computer runs the same peer application — there is no central tracker or server. Peers discover each other automatically via UDP broadcast, exchange file metadata, and download chunks directly from one another.

The web frontend is served through Docker. The peer backend runs natively so that UDP broadcast discovery continues to work across Wi-Fi.

---

## Features

- Trackerless peer-to-peer file sharing
- Automatic LAN peer discovery via UDP broadcast (no IP entry needed)
- Optional bootstrap peers for VPNs or networks that block broadcast
- File chunking and parallel reconstruction
- SHA-256 file and chunk verification
- Parallel chunk downloads (4 workers)
- Downloaded files remain shareable even when the original source goes offline
- React web dashboard served via Docker + Nginx
- Drag-and-drop file publishing from the browser
- Fine-grained mutex locking for thread-safe concurrent transfers

---

## Requirements

| Tool | Minimum version | Check |
|---|---|---|
| Python | 3.12 | `python --version` |
| Node.js | 18 | `node --version` |
| Docker Desktop | any | `docker --version` |

No third-party Python packages are required.

---

## Project Structure

```
.
├── start.bat               ← Windows launch script (edit this first)
├── start.sh                ← Unix launch script
├── Dockerfile              ← 2-stage build: Node → Nginx
├── docker-compose.yml
├── docker/
│   └── nginx.conf          ← proxies /api/* to native peer.py
├── frontend/               ← React + TypeScript + Tailwind source
│   ├── src/
│   │   ├── App.tsx
│   │   ├── api.ts
│   │   ├── types.ts
│   │   ├── hooks/
│   │   │   └── usePolling.ts
│   │   └── components/
│   │       ├── Header.tsx
│   │       ├── FileTable.tsx
│   │       ├── UploadZone.tsx
│   │       ├── PeersPanel.tsx
│   │       └── LocalPanel.tsx
│   ├── package.json
│   └── vite.config.ts
├── src/
│   ├── peer.py             ← peer server, discovery, chunk transfer
│   ├── chunking.py         ← file splitting and reconstruction
│   └── http_utils.py       ← JSON HTTP helpers
├── gui_launcher.py         ← legacy Tkinter desktop launcher
└── data/                   ← runtime peer data (gitignored)
```

---

## Architecture

```
HOST MACHINE (native Python):
  peer.py  →  TCP 9000   HTTP API + chunk transfer
           →  UDP 9999   peer discovery broadcast  ← must stay native

DOCKER CONTAINER:
  Nginx    →  port 8080
    /api/* →  proxy to host.docker.internal:9000
    /*     →  serve React web UI
```

The P2P layer (peer discovery, chunk transfer) runs natively on the host. Docker only packages the web frontend. This design keeps UDP broadcast working on real Wi-Fi networks.

---

## Quick Start

### 1. Find your Wi-Fi IP

```powershell
ipconfig
# Look for: Wireless LAN adapter Wi-Fi → IPv4 Address
# Example: 192.168.1.105
```

### 2. Edit `start.bat`

Open `start.bat` and set your values at the top:

```batch
set PEER_ID=peer1                     ← unique name for this laptop
set PEER_ADVERTISE_HOST=192.168.1.105 ← your actual Wi-Fi IP
set PEER_PORT=9000
set DATA_DIR=data\peer1
```

Every laptop in the demo needs a **different** `PEER_ID` and its **own** Wi-Fi IP.

### 3. Start Docker Desktop

Make sure Docker Desktop is running (whale icon in the system tray, "Engine running").

### 4. Run

```batch
start.bat
```

This starts `peer.py` natively and brings up the Docker frontend. Open **http://localhost:8080** in your browser.

---

## Multi-Laptop Demo (Same Wi-Fi)

On each laptop, edit `start.bat` with that laptop's own values, then run it:

| | Laptop A | Laptop B | Laptop C |
|---|---|---|---|
| `PEER_ID` | `peer-alice` | `peer-bob` | `peer-charlie` |
| `PEER_ADVERTISE_HOST` | `192.168.1.101` | `192.168.1.102` | `192.168.1.103` |
| `DATA_DIR` | `data\alice` | `data\bob` | `data\charlie` |

Open **http://localhost:8080** on each laptop. Peers discover each other automatically within 5 seconds — no manual IP entry required.

### Firewall

Allow these on every laptop (Windows Security → Firewall → Allow an app):

```
TCP 9000   peer HTTP API and chunk transfer
UDP 9999   peer discovery broadcast
```

---

## Dev Mode (No Docker)

Useful for development. Open two terminals:

**Terminal 1 — peer backend:**

```powershell
$env:PYTHONPATH = "src"
$env:PEER_ID = "peer1"
$env:PEER_ADVERTISE_HOST = "127.0.0.1"
$env:PEER_PORT = "9000"
$env:DATA_DIR = "data\peer1"
python -m peer
```

**Terminal 2 — React dev server:**

```powershell
cd frontend
npm run dev
```

Open **http://localhost:5173**. The Vite dev server proxies `/api/*` to `peer.py` on port 9000.

---

## Same-Computer Testing (Multiple Peers)

Run multiple peer processes on one machine. Each needs a unique peer ID, unique peer port, and separate data folder.

**Terminal 1:**
```powershell
$env:PYTHONPATH = "src"; $env:PEER_ID = "peer1"
$env:PEER_ADVERTISE_HOST = "127.0.0.1"; $env:PEER_PORT = "9000"
$env:DATA_DIR = "data\peer1"; python -m peer
```

**Terminal 2:**
```powershell
$env:PYTHONPATH = "src"; $env:PEER_ID = "peer2"
$env:PEER_ADVERTISE_HOST = "127.0.0.1"; $env:PEER_PORT = "9001"
$env:DATA_DIR = "data\peer2"; python -m peer
```

Peers advertising `127.0.0.1` automatically probe local ports `9000–9010`, so bootstrap peers can stay blank.

---

## Different Wi-Fi (VPN)

UDP broadcast does not cross different networks. Use [Tailscale](https://tailscale.com) to create a shared LAN.

1. Install Tailscale on each computer and sign in to the same network.
2. Use each computer's Tailscale IP as `PEER_ADVERTISE_HOST`.
3. Set `BOOTSTRAP_PEERS` to the other computer's Tailscale address.

```batch
Computer 1:  PEER_ADVERTISE_HOST=100.80.12.34   BOOTSTRAP_PEERS=100.90.55.10:9000
Computer 2:  PEER_ADVERTISE_HOST=100.90.55.10   BOOTSTRAP_PEERS=100.80.12.34:9000
```

---

## How It Works

### Peer Discovery

Every peer broadcasts a `peer_hello` UDP packet every 5 seconds on port 9999. Any peer on the same LAN that receives it adds the sender to its peer registry. Inactive peers are removed after 45 seconds.

### Publishing a File

1. The file is split into 512 KB chunks.
2. Each chunk receives a SHA-256 hash.
3. The full file receives a SHA-256 hash (used as its permanent network identity).
4. The peer records its chunk ownership in the local catalog.
5. Other peers learn about the file through `/manifest` metadata exchange every 8 seconds.

### Downloading a File

1. The peer looks up which peers own each chunk.
2. Up to 4 chunks are fetched in parallel from different peers.
3. Each chunk is verified against its SHA-256 hash.
4. The file is reconstructed and the peer becomes a new source for those chunks.

### File Status

| Status | Meaning |
|---|---|
| **Downloaded** | All chunks stored locally; no peers needed |
| **Partial** | Some chunks local; remaining chunks need peers |
| **Available** | No local chunks; at least one peer online with the file |
| **Unavailable** | No local chunks and no reachable peers |

### Concurrency and Mutex Design

The peer server is multi-threaded. Two separate locks protect shared state:

- `PEERS_LOCK` — guards the peer registry
- `CATALOG_LOCK` — guards the file catalog and chunk ownership records

Locks are always acquired in the order `PEERS_LOCK → CATALOG_LOCK` to prevent deadlock. A per-file download lock (`_file_dl_locks`) prevents concurrent downloads of the same file from racing on chunk writes and file assembly.

---

## HTTP API

Each peer exposes these endpoints on its peer port (default 9000):

```
GET  /health                              service status
GET  /peers                               known peer list
GET  /files                               full network file catalog
GET  /manifest                            export manifest for peer sync
GET  /local                               local shared/downloaded files
GET  /chunk?file_hash=<hash>&index=<n>    download one chunk
POST /publish   {"path": "/abs/path"}     publish a local file by path
POST /upload?name=<filename>  <raw body>  publish a file uploaded from browser
POST /download  {"file_hash": "..."}      download a file from peers
POST /manifest  <manifest object>         receive manifest from peer
```

**Publish by path (CLI):**
```powershell
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:9000/publish" `
  -ContentType "application/json" `
  -Body '{"path":"C:\\Users\\you\\Documents\\file.pdf"}'
```

**Upload from browser (curl):**
```powershell
curl.exe -X POST "http://127.0.0.1:9000/upload?name=file.pdf" `
  --data-binary @file.pdf
```

**Download a file:**
```powershell
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:9000/download" `
  -ContentType "application/json" `
  -Body '{"file_hash":"PASTE_HASH_HERE"}'
```

---

## Legacy Desktop Launcher

The original Tkinter GUI is still available:

```powershell
python gui_launcher.py
```

---

## Stopping Everything

```powershell
docker compose down
taskkill /F /IM python.exe
```

---

## Troubleshooting

**502 Bad Gateway at localhost:8080**
peer.py is not running. Check `peer.log` in the project folder. Wait a few seconds and refresh.

**Docker won't start**
Docker Desktop is not running. Open it from the Start menu and wait for "Engine running" in the system tray.

**Peers don't discover each other**
- All laptops must be on the same Wi-Fi network.
- `PEER_ADVERTISE_HOST` must be set to the actual Wi-Fi IP, not `127.0.0.1`.
- Windows Firewall must allow Python on TCP 9000 and UDP 9999.

**Peers discover each other but downloads fail**
- The peer advertised the wrong IP. Run `ipconfig` and confirm the IPv4 matches `PEER_ADVERTISE_HOST`.

**PowerShell curl error**
Use `curl.exe` instead of `curl`. PowerShell's `curl` is an alias for `Invoke-WebRequest`.

**Cannot publish an empty file**
The publish and upload endpoints reject files with 0 bytes.

---

## Development

Compile all Python files:

```powershell
python -m compileall gui_launcher.py src
```

Build the React frontend:

```powershell
cd frontend
npm run build
```

Build and run the Docker image locally:

```powershell
docker compose up --build
```

Clean Python caches:

```powershell
Remove-Item -Recurse -Force __pycache__, src\__pycache__
```
