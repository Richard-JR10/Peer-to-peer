# PDC — Trackerless P2P File Sharing & Messaging

A fully decentralized file sharing and messaging system for local networks and VPNs. Every machine runs the same peer program — there is no central server or tracker. Peers find each other automatically over Wi-Fi, exchange file metadata, transfer chunks directly to each other, and send encrypted messages peer-to-peer.

---

## Features

| Category | What it does |
|---|---|
| **Discovery** | UDP broadcast on LAN — peers appear automatically, no IP entry needed |
| **Bootstrap** | Manual seed peers for VPNs (Tailscale) or networks that block broadcast |
| **Chunking** | Files split into 512 KB chunks; SHA-256 hash verifies every chunk |
| **Parallel transfers** | Up to 4 chunks downloaded simultaneously from different peers |
| **Resilience** | Downloaded chunks stay shareable — original source can go offline |
| **Transit encryption** | AES-256-GCM encrypts every chunk sent over HTTP (`PEER_PASSPHRASE`) |
| **File password** | Optional per-file AES-256-GCM encryption; only holders of the password can open the assembled file |
| **Peer restriction** | Limit which peers may request chunks of a specific file |
| **Stop / Resume sharing** | Pause serving a file without deleting it; resume at any time |
| **Safe delete** | Two-click confirmation; pulsing "Only source!" warning if no other peer has the file |
| **Encrypted messaging** | Direct peer-to-peer text chat encrypted with AES-256-GCM; per-peer conversation view with chat bubble UI |
| **Message delivery** | Messages sent directly to the recipient peer over HTTP — no relay, no server |
| **Web dashboard** | React + Tailwind UI served by Docker; search, chunk map, upload with drag-and-drop |
| **Thread safety** | Fine-grained mutex design — no global lock bottlenecks |

---

## Requirements

| Tool | Minimum | Check |
|---|---|---|
| Python | 3.12 | `python --version` |
| pip package | — | `pip install cryptography` |
| Node.js | 18 | `node --version` |
| Docker Desktop | any | `docker --version` |

Install the Python dependency once:

```powershell
pip install -r requirements.txt
```

---

## Project Structure

```
PDC/
├── start.bat                    ← Windows launch script — edit before first run
├── start.sh                     ← Linux/macOS launch script
├── requirements.txt             ← cryptography
├── Dockerfile                   ← 2-stage: Node build → Nginx serve
├── docker-compose.yml           ← runs the frontend container on port 8080
├── docker/
│   └── nginx.conf               ← /api/* → host peer.py, /* → React SPA
│
├── src/                         ← Python peer backend
│   ├── peer.py                  ← HTTP server, discovery, catalog, transfers
│   ├── chunking.py              ← chunk_file(), assemble_file(), sha256_*()
│   ├── crypto.py                ← derive_key(), encrypt(), decrypt() — AES-256-GCM
│   └── http_utils.py            ← send_json(), read_json(), request_json()
│
├── frontend/src/                ← React + TypeScript + Tailwind
│   ├── App.tsx                  ← root component, polling, handlers
│   ├── api.ts                   ← typed wrappers for every /api/* endpoint
│   ├── types.ts                 ← NetworkFile, Peer, Message, helpers
│   ├── hooks/
│   │   └── usePolling.ts        ← setInterval polling hook
│   └── components/
│       ├── Header.tsx           ← peer ID, connection status, counts
│       ├── FileTable.tsx        ← file list, chunk map, action buttons
│       ├── UploadZone.tsx       ← drag-and-drop + access controls panel
│       ├── PeersPanel.tsx       ← live peer list with last-seen times
│       ├── LocalPanel.tsx       ← local shared / downloaded / chunk files
│       └── MessagingPanel.tsx   ← encrypted P2P chat bubbles
│
├── gui_launcher.py              ← legacy Tkinter desktop launcher (optional)
└── data/                        ← runtime data, gitignored
    ├── shared/                  ← original uploaded files
    ├── chunks/<hash>/           ← per-file chunk storage
    ├── downloads/               ← assembled downloaded files
    └── manifests/               ← persisted file manifests (survive restart)
```

---

## Architecture

```
HOST MACHINE  (runs natively — UDP broadcast needs real network stack)
┌─────────────────────────────────────────────────────┐
│  peer.py                                            │
│    TCP 9000  →  HTTP API, chunk transfers           │
│    UDP 9999  →  peer_hello broadcast / listener     │
└─────────────────────────────────────────────────────┘
          ↑ proxied by Nginx at /api/*
DOCKER CONTAINER
┌─────────────────────────────────────────────────────┐
│  Nginx  port 8080                                   │
│    /api/*  →  http://host.docker.internal:9000      │
│    /*      →  React SPA (static files)              │
└─────────────────────────────────────────────────────┘
```

The peer backend stays native so UDP broadcast works on real Wi-Fi. Docker only hosts the web UI.

---

## Environment Variables

Set these in `start.bat` (Windows) or `start.sh` (Unix) before running.

| Variable | Default | Description |
|---|---|---|
| `PEER_ID` | `peer` | Unique name for this node — shown in the dashboard and used for access control |
| `PEER_HOST` | `0.0.0.0` | Interface peer.py listens on (keep `0.0.0.0`) |
| `PEER_ADVERTISE_HOST` | same as HOST | **Wi-Fi IP** other peers connect to — must be your actual IP, not `127.0.0.1` |
| `PEER_PORT` | `9000` | TCP port for HTTP API and chunk transfers |
| `DISCOVERY_PORT` | `9999` | UDP port for peer discovery broadcast |
| `PEER_PASSPHRASE` | *(empty)* | Shared secret for transit encryption — **all peers must use the same value** |
| `BOOTSTRAP_PEERS` | *(empty)* | Comma-separated `host:port` seed peers for VPNs or multi-network setups |
| `DATA_DIR` | `/data` | Root folder for chunks, downloads, shared files, manifests |
| `AUTO_BOOTSTRAP_PORTS` | `9000-9010` | Local port range probed when `PEER_ADVERTISE_HOST` is `127.0.0.1` |
| `PEER_TTL_SECONDS` | `45` | How long before an unresponsive peer is removed |
| `HELLO_INTERVAL_SECONDS` | `5` | How often UDP discovery packets are broadcast |
| `MANIFEST_INTERVAL_SECONDS` | `8` | How often peers exchange full file catalogs |

---

## Quick Start

### Option A — Dev Mode (no Docker)

Two terminals, both in the project root.

**Terminal 1 — peer backend:**

```powershell
$env:PYTHONPATH     = "src"
$env:PEER_ID        = "my-laptop"
$env:PEER_ADVERTISE_HOST = "192.168.1.101"   # your Wi-Fi IP (ipconfig → IPv4)
$env:PEER_PORT      = "9000"
$env:PEER_PASSPHRASE = "shared-key"
$env:DATA_DIR       = "data\peer1"
python -m peer
```

**Terminal 2 — React dev server:**

```powershell
cd frontend
npm install          # first time only
npm run dev
```

Open **http://localhost:5173**

---

### Option B — Full Mode (Docker frontend)

1. Open `start.bat` and edit the five values at the top (`PEER_ID`, `PEER_ADVERTISE_HOST`, `PEER_PORT`, `PEER_PASSPHRASE`, `DATA_DIR`).
2. Make sure Docker Desktop is running (whale icon in system tray).
3. Double-click `start.bat` or run it in a terminal.

A dedicated **peer.py window** opens with live logs. The Docker container builds and starts automatically.

Open **http://localhost:8080**

To stop: close the peer.py window, then run `docker compose down`.

---

## Multi-Laptop Setup (Same Wi-Fi)

Each laptop runs `start.bat` with its own values:

| | Laptop A | Laptop B | Laptop C |
|---|---|---|---|
| `PEER_ID` | `peer-alice` | `peer-bob` | `peer-charlie` |
| `PEER_ADVERTISE_HOST` | `192.168.1.101` | `192.168.1.102` | `192.168.1.103` |
| `PEER_PASSPHRASE` | `shared-key` | `shared-key` | `shared-key` |
| `DATA_DIR` | `data\alice` | `data\bob` | `data\charlie` |
| `BOOTSTRAP_PEERS` | *(empty)* | *(empty)* | *(empty)* |

Peers discover each other via UDP broadcast within ~5 seconds. No IP entry needed.

### Windows Firewall

Allow on every laptop (Windows Security → Firewall → Allow an app through):

```
TCP 9000   chunk transfers and API
UDP 9999   peer discovery
```

---

## Same-Computer Testing (Multiple Peers)

Each process needs a unique `PEER_ID`, `PEER_PORT`, and `DATA_DIR`.

```powershell
# Terminal 1
$env:PYTHONPATH="src"; $env:PEER_ID="peer1"; $env:PEER_PORT="9000"
$env:PEER_ADVERTISE_HOST="127.0.0.1"; $env:PEER_PASSPHRASE="test"
$env:DATA_DIR="data\peer1"; python -m peer

# Terminal 2
$env:PYTHONPATH="src"; $env:PEER_ID="peer2"; $env:PEER_PORT="9001"
$env:PEER_ADVERTISE_HOST="127.0.0.1"; $env:PEER_PASSPHRASE="test"
$env:DATA_DIR="data\peer2"; python -m peer
```

Peers on `127.0.0.1` automatically probe ports `9000–9010` — no `BOOTSTRAP_PEERS` needed.

---

## VPN Setup (Tailscale)

UDP broadcast does not cross network boundaries. Tailscale creates a shared virtual LAN but does not forward broadcasts — use explicit bootstrap peers.

1. Install [Tailscale](https://tailscale.com) on all computers and join the same network.
2. Set `PEER_ADVERTISE_HOST` to each computer's Tailscale IP (looks like `100.x.x.x`).
3. Set `BOOTSTRAP_PEERS` to at least one other peer's Tailscale address.

```batch
Computer 1:
  PEER_ADVERTISE_HOST = 100.80.12.34
  BOOTSTRAP_PEERS     = 100.90.55.10:9000

Computer 2:
  PEER_ADVERTISE_HOST = 100.90.55.10
  BOOTSTRAP_PEERS     = 100.80.12.34:9000
```

After the first manifest sync, peer lists propagate automatically — Computer 3 only needs to bootstrap to one known peer to learn about all others.

---

## How It Works

### Peer Discovery

Every 5 seconds each peer broadcasts a `peer_hello` UDP packet on port 9999. Any peer on the same network that receives it registers the sender. Peers that haven't been heard from in 45 seconds are removed from the registry and from chunk ownership records.

### Publishing a File

1. The file is split into **512 KB chunks** (`chunking.py`).
2. Each chunk gets a **SHA-256 hash** as its identity.
3. The full assembled file also gets a SHA-256 hash — this is the permanent file ID.
4. The peer writes chunk files to `data/chunks/<file_hash>/` and saves a JSON manifest to `data/manifests/`.
5. The file is registered in the in-memory catalog with the peer's chunk ownership.
6. Other peers learn about it via `/manifest` exchange every 8 seconds.

### Downloading a File

1. The peer's catalog shows which peers own which chunks.
2. Up to 4 chunks are fetched in parallel from different peers.
3. Each received chunk is **AES-256-GCM decrypted** (transit key) then **SHA-256 verified**.
4. Verified chunks are saved locally — this peer now becomes a source for those chunks.
5. Once all chunks are present, `assemble_file()` reconstructs the file and verifies the full-file hash.
6. If the file is password-protected, the assembled blob is **AES-256-GCM decrypted** with the per-file key before saving to `data/downloads/`.

### Encryption

Two independent encryption layers:

| Layer | Key source | Scope |
|---|---|---|
| **Transit** | `PEER_PASSPHRASE` env var (shared across all peers) | Every chunk sent over HTTP — protects in-flight data |
| **Per-file** | Password entered at upload time | Encrypts file content before chunking — only the correct password decrypts the assembled file |

Both use **AES-256-GCM** with a **PBKDF2-SHA256** key derived from the passphrase (100,000 iterations, salt `pdc-p2p-v1`). Implementation in `src/crypto.py`.

### Access Control

| Control | How to set | Effect |
|---|---|---|
| **Peer restriction** | Check peers in Access controls at upload | Chunk requests from unlisted peers get `403 Forbidden` |
| **File password** | Enter password in Access controls at upload | File content is AES-256-GCM encrypted; peers must supply the password to assemble it |
| **Stop sharing** | Click pause button in dashboard | Chunks stay on disk; all `/chunk` requests for this file return `403`; reversible |

### Sharing Pause vs Delete

| Action | Chunks on disk | Peers can download | Reversible |
|---|---|---|---|
| Stop sharing | Yes | No (`403`) | Yes — click Resume |
| Delete | No (wiped) | Only if other peers have it | No — hash tombstoned |

Deleted file hashes are added to `DELETED_HASHES`. Manifest sync never re-adds tombstoned files, even if other peers advertise them.

### Messaging

Each peer exposes `/send_message` and `/message` endpoints. When you send a message:
1. The text is UTF-8 encoded and **AES-256-GCM encrypted** with the shared passphrase.
2. The ciphertext (hex) is POSTed directly to the recipient peer's `/message` endpoint.
3. The recipient decrypts it and stores it in memory.
4. The React dashboard polls `/messages` every 2 seconds and displays a per-peer chat view — sent messages on the right (blue bubbles), received on the left (gray bubbles).

### Concurrency Design

The server is fully multi-threaded (`ThreadingHTTPServer`). Three levels of locking:

| Lock | Protects | Acquisition order |
|---|---|---|
| `PEERS_LOCK` | `PEERS` dict | Always first |
| `CATALOG_LOCK` | `CATALOG`, `DELETED_HASHES`, `SHARING_PAUSED` | Always second |
| `_file_dl_locks[hash]` | per-file chunk write + assemble | Acquired after CATALOG_LOCK is released |

The strict `PEERS_LOCK → CATALOG_LOCK` order eliminates circular wait (deadlock). File I/O (chunk writes, manifest saves) always happens **outside** `CATALOG_LOCK` to avoid blocking the entire server on disk operations.

### Frontend Polling

| Data | Interval | Notes |
|---|---|---|
| Health / peer ID | 2 s | |
| Files + peers + local | 3 s normal, 500 ms during download | Fast polling keeps progress bar smooth |
| Messages | 2 s | |

---

## File Status

| Badge | Meaning |
|---|---|
| **Downloaded** | All chunks stored locally — no peers needed |
| **Partial** | Some chunks local — remaining chunks available from peers |
| **Available** | No local chunks — at least one peer online with the full file |
| **Unavailable** | No local chunks and no reachable peers |
| **Paused** | Local chunks held but not being served (sharing paused) |

Additional indicators in the filename column:

| Icon | Meaning |
|---|---|
| Lock (yellow) | File is password-protected |
| People (blue) | File is restricted to specific peers |

---

## Dashboard Controls

### File Table Actions

| Button | Shown when | What it does |
|---|---|---|
| Pause (circle-pause) | Local chunks, sharing active | Stops serving chunks (`/stop_sharing`); "Paused" badge appears |
| Play (circle-play) | Local chunks, sharing paused | Resumes serving chunks (`/resume_sharing`) |
| Trash → **Confirm?** | Local chunks | Arms delete — click again to confirm, click anywhere else to cancel |
| Trash → **Only source!** *(pulsing red)* | Local chunks, you are the only peer | Same confirm flow but warns the file disappears from the network |
| Download | File not fully local | Fetches chunks from peers |
| Password input | File is password-protected | Must be filled before Download is enabled |

Click any row to expand the **chunk map** — shows which chunks are local (green), held by peers (blue), or missing (gray).

### Upload — Access Controls

Click **Access controls** below the drop zone:

- **Restrict to peers** — check which peer IDs may request chunks. Leave empty = public.
- **File password** — encrypts the file with AES-256-GCM before chunking. Peers need this password to open the file after downloading.

---

## HTTP API Reference

All endpoints on `http://<host>:<PEER_PORT>` (default port 9000). The frontend accesses them through Nginx at `/api/*`.

### GET endpoints

| Path | Returns |
|---|---|
| `/health` | `{status, peer_id, mode, known_peers, known_files}` |
| `/peers` | `{peers: [{peer_id, host, port, last_seen, digest}]}` |
| `/files` | `{files: [NetworkFile]}` — full catalog with ownership and paused state |
| `/manifest` | Full manifest for peer-to-peer sync |
| `/local` | `{shared, downloads, chunks}` — local file paths |
| `/chunk?file_hash=H&index=N&peer_id=ID` | `{data: base64}` — one AES-256-GCM encrypted chunk |
| `/messages` | `{messages: [{from_peer, text, timestamp}]}` |

### POST endpoints

| Path | Body | Effect |
|---|---|---|
| `/upload?name=F[&allowed_peers=a,b][&file_password=pw]` | raw file bytes | Publish file; encrypts content if `file_password` set |
| `/publish` | `{"path": "/abs/path"}` | Publish a file already on disk (no encryption) |
| `/download` | `{"file_hash": "H", "file_password": "pw"}` | Fetch chunks from peers, assemble, decrypt if needed |
| `/delete` | `{"file_hash": "H"}` | Wipe chunks + manifest + shared file; tombstone hash |
| `/stop_sharing` | `{"file_hash": "H"}` | Pause chunk serving for this file |
| `/resume_sharing` | `{"file_hash": "H"}` | Resume chunk serving |
| `/manifest` | manifest object | Receive and merge a peer's manifest |
| `/send_message` | `{"to_peer_id": "P", "text": "T"}` | Encrypt and deliver message to peer |
| `/message` | `{"from_peer": "P", "text": "<hex>"}` | Receive an encrypted message (peer-to-peer) |

### Example curl commands

```powershell
# Upload with password + peer restriction
curl.exe -X POST "http://127.0.0.1:9000/upload?name=report.pdf&file_password=secret&allowed_peers=peer-bob" `
  --data-binary @report.pdf

# Download password-protected file
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:9000/download" `
  -ContentType "application/json" `
  -Body '{"file_hash":"HASH_HERE","file_password":"secret"}'

# Pause sharing
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:9000/stop_sharing" `
  -ContentType "application/json" -Body '{"file_hash":"HASH_HERE"}'

# Resume sharing
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:9000/resume_sharing" `
  -ContentType "application/json" -Body '{"file_hash":"HASH_HERE"}'

# Delete a file
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:9000/delete" `
  -ContentType "application/json" -Body '{"file_hash":"HASH_HERE"}'
```

---

## Troubleshooting

**502 Bad Gateway at localhost:8080**
peer.py is not running. Check the peer window for error output. In dev mode, make sure `python -m peer` is still running in its terminal.

**Peers don't discover each other**
- All machines must be on the same Wi-Fi network (or Tailscale).
- `PEER_ADVERTISE_HOST` must be the actual Wi-Fi IP, not `127.0.0.1` or `0.0.0.0`.
- Windows Firewall must allow Python on TCP 9000 and UDP 9999.

**Peers discover each other but downloads fail**
The peer advertised the wrong IP. Run `ipconfig`, confirm the IPv4 address matches `PEER_ADVERTISE_HOST`.

**Wrong password / decryption error on download**
The `file_password` doesn't match what was used at upload time.

**All chunk transfers fail with decryption errors**
The `PEER_PASSPHRASE` values don't match across peers. Every peer must use the identical passphrase.

**403 access denied on chunk request**
The file owner restricted it to specific peer IDs. Your `PEER_ID` is not on the allowed list.

**File comes back after I delete it**
Make sure you're using the Delete button in the dashboard (not just removing the file from disk manually). The dashboard delete tombstones the hash so manifest sync cannot resurrect it.

**Sharing paused but other peers still see me as a source**
The pause takes effect on the next manifest sync cycle (~8 seconds). Other peers' dashboards update when they next poll `/files`.

**Docker won't start**
Docker Desktop is not running. Open it from the Start menu and wait for "Engine running" in the system tray.

**PowerShell `curl` error**
Use `curl.exe` not `curl`. In PowerShell, `curl` is an alias for `Invoke-WebRequest`.

**Empty file rejected**
`/upload` and `/publish` reject files with 0 bytes.

---

## Development

```powershell
# Install Python dependencies
pip install -r requirements.txt

# Run React dev server (hot reload)
cd frontend
npm install
npm run dev

# Build React for production (baked into Docker image)
cd frontend
npm run build

# Build and start Docker container
docker compose up --build

# Type-check Python
python -m compileall src

# Clean caches
Remove-Item -Recurse -Force __pycache__, src\__pycache__
```

---

## Stopping Everything

```powershell
docker compose down          # stop Docker container
taskkill /F /IM python.exe   # stop peer.py (all Python processes)
```
