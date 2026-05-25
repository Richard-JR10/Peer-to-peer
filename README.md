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

## How It Works — Technical Deep Dive

This section explains every major subsystem and the Parallel and Distributed Computing (PDC) concepts each one demonstrates.

---

### 1. Peer Discovery — Broadcast Communication

**PDC concept: message passing in a distributed system, connectionless communication**

Every peer runs two background threads dedicated to discovery:

- **Broadcast thread** — every 5 seconds, serializes a `peer_hello` JSON payload and sends it as a UDP datagram to `255.255.255.255:9999` (the limited broadcast address). A directed subnet broadcast (e.g. `192.168.1.255`) is also sent so hotspots that filter `255.255.255.255` still forward the packet.
- **Listener thread** — blocks on `sock.recvfrom()` waiting for incoming datagrams. Any received `peer_hello` from a different peer ID is immediately added to the `PEERS` registry via `upsert_peer()`.

UDP is used instead of TCP because:
- UDP is **connectionless** — no handshake overhead, no connection state to maintain per peer
- **Broadcast** is only possible with UDP; TCP requires a known destination address
- Packet loss is acceptable — if one hello is dropped, the next arrives in 5 seconds

Each `peer_hello` carries `peer_id`, `host`, `port`, and a `digest` (SHA-256 of the current catalog). The digest lets a peer know immediately whether the sender's catalog has changed without fetching the full manifest.

Peers that haven't sent a `peer_hello` in `PEER_TTL_SECONDS` (45 s) are considered dead. `cleanup_inactive_peers()` removes them from `PEERS` and strips their chunk ownership from `CATALOG` so the dashboard stops showing them as available sources.

---

### 2. Bootstrap and Manifest Sync — Gossip Protocol

**PDC concept: decentralized information dissemination, eventual consistency**

UDP broadcast only reaches the local subnet. For VPN setups or multi-network deployments, explicit `BOOTSTRAP_PEERS` provide a TCP entry point.

Every `MANIFEST_INTERVAL_SECONDS` (8 s) the **manifest sync loop** runs:
1. Builds a list of all known peers plus any bootstrap candidates.
2. Shuffles the list randomly — this distributes sync load evenly and avoids thundering herd patterns.
3. For each peer, calls `sync_manifest(peer)`:
   - `GET /manifest` pulls that peer's full manifest (peer list + file catalog).
   - `merge_manifest()` integrates new peers and new file/chunk data into the local state.
   - `POST /manifest` pushes the local manifest back to the same peer (bidirectional exchange in one round trip).

This is a simplified **gossip protocol**: each node periodically exchanges state with a random subset of known nodes. Information propagates across the network within a few sync cycles even if no two nodes share a direct connection initially — a new peer that knows only Peer A will learn about Peer B within one sync cycle if Peer A's manifest includes Peer B.

**Eventual consistency**: there is no global coordinator. All peers converge to the same view of the network over time through repeated bilateral exchanges. A new file uploaded to Peer A appears on Peer C's dashboard within ~16 seconds (two sync cycles), even if A and C never communicated directly.

---

### 3. File Chunking — Data Parallelism

**PDC concept: data decomposition, parallel I/O**

`chunk_file()` in `chunking.py` reads the source file in 512 KB blocks and writes each block as a separate `.chunk` file under `data/chunks/<file_hash>/`. Each chunk records its index, SHA-256 hash, and byte size.

Chunking enables two things:

1. **Parallel download** — different chunks can be fetched from different peers simultaneously (see section 4).
2. **Partial availability** — a peer that has downloaded only some chunks is already a valid source for those chunks. The file does not need to be complete before it can be shared. This means a swarm of peers can all download a large file simultaneously while simultaneously helping each other.

The file's SHA-256 hash is computed over the entire file before chunking and serves as the permanent network identity. This is content-addressed storage: the hash is the name. Two files with identical content have the same hash and are deduplicated automatically.

---

### 4. Parallel Chunk Downloads — Thread Pool

**PDC concept: task parallelism, ThreadPoolExecutor, concurrent futures**

`download_file()` uses Python's `ThreadPoolExecutor` with `max_workers=4`:

```
for each missing chunk:
    find candidate peers that hold this chunk
    submit fetch_chunk_from_candidates() as a Future
    
for future in as_completed(futures):
    collect result or record error
```

`as_completed()` yields futures as they finish, not in submission order — so a fast peer's result is processed immediately without waiting for a slower peer to finish its chunk. This is **non-blocking result collection**.

Each `fetch_chunk()` call:
1. Issues a `GET /chunk` HTTP request to the selected peer.
2. Base64-decodes the response body.
3. AES-256-GCM decrypts the data (transit key).
4. SHA-256 verifies the decrypted bytes against the expected chunk hash.
5. Writes the chunk to disk.
6. Calls `add_own_chunk()` to register local ownership under `CATALOG_LOCK`.

If a peer fails mid-download, `remove_peer()` is called and the chunk is retried on the next available candidate. The system degrades gracefully — as long as at least one peer holds a chunk, the download completes.

**Chunk rotation**: candidate peers for each chunk are sorted by peer ID and then rotated by chunk position index. This spreads download load across peers rather than hammering one peer for all chunks.

---

### 5. Mutual Exclusion — Mutex Design

**PDC concept: mutual exclusion, deadlock prevention, lock granularity**

The server is fully multi-threaded (`ThreadingHTTPServer` — each HTTP request runs in its own thread). Multiple threads can simultaneously handle chunk downloads, manifest syncs, uploads, deletes, and dashboard polls. Without synchronization, concurrent writes to shared state produce race conditions.

Three levels of locking protect shared state:

#### `PEERS_LOCK` — threading.Lock()
Guards the `PEERS` dictionary. Acquired for reads and writes to peer registration (`upsert_peer`, `remove_peer`, `cleanup_inactive_peers`). Held for the shortest possible time — only dictionary access, never I/O.

#### `CATALOG_LOCK` — threading.Lock()
Guards `CATALOG` (file metadata and chunk ownership), `DELETED_HASHES` (tombstone set), and `SHARING_PAUSED` (pause set). All three are modified atomically together so no thread sees a half-updated state.

**Critical design decision**: file I/O (writing manifest JSON to disk, writing chunk files) is always performed **outside** `CATALOG_LOCK`. Only a snapshot of the needed data is taken under the lock, then the lock is released before touching the filesystem. Holding a mutex during disk I/O would block every other thread — chunk downloads, API responses, manifest syncs — for the entire duration of the write.

```python
# Pattern used throughout peer.py:
with CATALOG_LOCK:
    manifest_snapshot = json.loads(json.dumps(file_info))  # deep copy under lock
# lock released — now safe to write to disk without blocking other threads
persist_file_manifest(manifest_snapshot)
```

#### `_file_dl_locks[hash]` — per-file threading.Lock()
A separate lock is created on demand for each file hash being downloaded. This serializes concurrent `/download` requests for the **same file** — if two users click download simultaneously, one waits rather than both racing to write chunks and assemble the output file. Different files download in parallel without contention.

This is a **double-checked lock pattern**:
```python
with _file_dl_locks_mu:           # guards the dict itself
    if hash not in _file_dl_locks:
        _file_dl_locks[hash] = threading.Lock()
    return _file_dl_locks[hash]
```

#### Deadlock Prevention — Lock Ordering

Deadlock occurs when Thread A holds Lock 1 and waits for Lock 2, while Thread B holds Lock 2 and waits for Lock 1 — circular wait, both blocked forever.

The fix is a **strict global acquisition order**: any code that needs both locks must always acquire `PEERS_LOCK` first, then `CATALOG_LOCK`. This eliminates circular wait because no thread ever holds `CATALOG_LOCK` while waiting for `PEERS_LOCK`.

`remove_peer()` demonstrates this explicitly — it acquires and releases each lock separately rather than nesting them, because the two operations (removing from `PEERS` and removing from `CATALOG`) are independent:

```python
def remove_peer(peer_id):
    with PEERS_LOCK:
        PEERS.pop(peer_id, None)
    with CATALOG_LOCK:                        # acquired after PEERS_LOCK is released
        for file_info in CATALOG.values():
            file_info.get("peers", {}).pop(peer_id, None)
```

#### `MESSAGES_LOCK` — threading.Lock()
Guards the `MESSAGES` list. Simple reader-writer pattern — the list is appended to by incoming `/message` POST requests and read by `/messages` GET requests, which can happen concurrently.

---

### 6. Distributed File Catalog — Shared State Without a Central Server

**PDC concept: distributed shared state, replication, conflict resolution**

Every peer maintains its own in-memory `CATALOG` — a dictionary keyed by file hash, storing file metadata and a map of which peers own which chunks. There is no database and no central authority.

`merge_manifest()` is the reconciliation function. When a peer receives another peer's manifest it:

1. **Upserts peer records** — new peers are added, known peers get their `last_seen` updated.
2. **Merges file entries** — for each file in the incoming manifest, `add_file_to_catalog()` is called. `setdefault` ensures existing entries are not overwritten wholesale — only missing fields are filled in.
3. **Conflict detection** — if the same file hash appears with different chunk metadata (different sizes or hashes), it is rejected with a `ValueError`. The hash is the content identity; different content means a different file.
4. **Stale ownership removal** — after processing all files, the function computes the set of hashes the advertising peer currently claims. Any file the advertising peer previously claimed but no longer includes is stripped of that peer's ownership entry. This is how deletions propagate: once a peer deletes a file and stops advertising it, other peers stop listing it as a source within one sync cycle.

**Tombstones** (`DELETED_HASHES`): when a file is deleted locally, its hash is added to this set permanently (for the lifetime of the process). `add_file_to_catalog()` checks this set first — if the hash is tombstoned, the entry is silently ignored. This prevents manifest sync from resurrecting files the user explicitly chose to remove.

**Manifest persistence**: each time a file entry changes, `persist_file_manifest()` writes a JSON file to `data/manifests/`. On startup, `restore_local_manifests()` reads these files and re-registers all files the peer owns. This means chunk ownership survives process restart without needing to re-download anything.

---

### 7. Encryption — Two-Layer Security

**PDC concept: secure communication in distributed systems**

#### Layer 1 — Transit Encryption (chunk transfer)

All chunk data sent between peers is encrypted with **AES-256-GCM** using a key derived from the shared `PEER_PASSPHRASE`. This protects chunks in flight from eavesdroppers on the network.

- The sender calls `encrypt(raw_bytes, ENCRYPTION_KEY)` before base64-encoding and sending.
- The receiver base64-decodes, then calls `decrypt(data, ENCRYPTION_KEY)` before verifying the chunk hash.
- If `PEER_PASSPHRASE` is empty, encryption is skipped (useful for local testing).

Messages between peers use the same key and same encrypt/decrypt functions.

#### Layer 2 — Per-File Content Encryption

Optional. Set at upload time by providing a `file_password`.

- Before chunking, the entire file is encrypted: `encrypt(file_bytes, derive_key(file_password))`.
- The encrypted blob is what gets chunked and distributed. Peers that download and assemble the chunks get ciphertext, not the original file.
- After assembly, the downloader must supply the correct password. `decrypt(assembled_bytes, derive_key(file_password))` produces the original file. A wrong password raises an exception; the assembled ciphertext is deleted.
- The `password_protected: true` flag is stored in the manifest and propagated to all peers so their dashboards show the lock icon — but the password itself is never stored or transmitted.

#### Key Derivation — PBKDF2-SHA256

Raw passphrases are not used directly as AES keys. `derive_key()` in `crypto.py` runs PBKDF2-SHA256 with 100,000 iterations and a fixed salt (`pdc-p2p-v1`) to produce a 32-byte (256-bit) key. The high iteration count makes brute-forcing the passphrase computationally expensive.

```python
def derive_key(passphrase: str) -> bytes:
    return hashlib.pbkdf2_hmac('sha256', passphrase.encode('utf-8'), b'pdc-p2p-v1', 100_000, dklen=32)
```

#### AES-256-GCM Properties

- **Authenticated encryption** — GCM mode produces an authentication tag. If any byte of the ciphertext is modified in transit, decryption fails with an exception (not silently corrupted data).
- **Random nonce** — a fresh 12-byte nonce is generated for every `encrypt()` call using `os.urandom(12)`. The nonce is prepended to the ciphertext so the receiver can extract it. Reusing a nonce with the same key would break GCM security — the random generation ensures this never happens.

---

### 8. Access Control — Distributed Policy Enforcement

**PDC concept: distributed authorization without a central authority**

#### Peer Restriction

When a file is uploaded with `allowed_peers`, the list is stored in the catalog and propagated in every manifest. When any peer receives a `/chunk` request it checks the requester's `peer_id` against `allowed_peers` before serving data:

```python
if _allowed and requesting_peer_id not in _allowed:
    send_json(self, HTTPStatus.FORBIDDEN, {"error": "access denied"})
    return
```

The requesting peer sends its own `PEER_ID` as a query parameter. This is an honor-system check — a malicious client could send a spoofed peer ID. For a trusted-network classroom demo, this is sufficient; production systems would use cryptographic peer identity (certificates or public keys).

#### Sharing Pause

`SHARING_PAUSED` is an in-memory set of file hashes this peer has voluntarily stopped serving. It is checked in the `/chunk` handler alongside the `allowed_peers` check. Unlike deletion, it does not remove any data and is not persisted — a peer restart clears all pauses and files are re-advertised automatically.

The pause is reflected in the snapshot returned by `/files` and `/manifest`: when a file is paused, this peer's ownership entry is omitted from the `peers` dict (but `local_chunks` still reflects disk reality). Other peers see the count drop to zero for this source within one manifest sync cycle and stop routing chunk requests here.

---

### 9. Deletion and Tombstoning — Distributed Garbage Collection

**PDC concept: distributed state removal, tombstone pattern**

Deleting a distributed resource is harder than deleting a local one. If Peer A deletes a file but Peer B still has it in its catalog, the next manifest exchange would re-add the file to Peer A's catalog — the delete would be undone.

The solution is a **tombstone**: when a file is deleted, its hash is added to `DELETED_HASHES` and never removed. `add_file_to_catalog()` checks this set at the top and returns immediately if the hash is tombstoned, so no manifest from any peer can resurrect it.

The delete also:
- Removes the entry from `CATALOG` (under `CATALOG_LOCK`)
- Adds to `DELETED_HASHES` (under the same `CATALOG_LOCK` — atomically together)
- Deletes chunk files from `data/chunks/<hash>/`
- Deletes the manifest JSON from `data/manifests/`
- Deletes the original file from `data/shared/`

Other peers learn the file is gone via the stale ownership removal in `merge_manifest()`: once this peer stops advertising the file, other peers remove it as a source. If no other peer has the file, it eventually shows as "Unavailable" everywhere.

---

### 10. Messaging — Direct Peer-to-Peer Communication

**PDC concept: point-to-point message passing, no relay**

Unlike file chunks which are served on demand, messages are **pushed** directly from sender to receiver:

1. The sender calls `POST /send_message` on its own peer with `{to_peer_id, text}`.
2. `peer.py` looks up the recipient's address in `PEERS`.
3. The text is encrypted with AES-256-GCM (same transit key as chunks).
4. The ciphertext is hex-encoded and sent as `POST /message` directly to the recipient's HTTP server.
5. The recipient decrypts and appends to its `MESSAGES` list under `MESSAGES_LOCK`.
6. The React dashboard polls `GET /messages` every 2 seconds and merges received messages with locally-tracked sent messages (sorted by timestamp).

**Optimistic UI**: sent messages are added to React state immediately without waiting for the poll cycle, so the chat feels instant. The message is shown with `direction: 'sent'` and the recipient's peer ID so the per-peer conversation filter works correctly.

Messages are **in-memory only** — they do not survive a peer restart. This is an intentional design choice that keeps the implementation simple and avoids any persistence or replay concerns.

---

### 11. Frontend Polling — Simulated Real-Time Updates

**PDC concept: client-side state synchronization in a distributed system**

The React frontend has no persistent connection to `peer.py` (no WebSocket). Instead, `usePolling.ts` runs `setInterval` loops that repeatedly call the REST API:

| Endpoint polled | Interval | Reason |
|---|---|---|
| `/health` | 2 s | Detect peer.py restart; get current peer ID |
| `/files`, `/peers`, `/local` | 3 s idle / 500 ms active | 500 ms during downloads keeps the progress bar smooth |
| `/messages` | 2 s | Near-real-time chat feel |

The fast poll during downloads is triggered by watching the `downloading` Set in React state — when it is non-empty, the interval drops to 500 ms automatically, then returns to 3 s when the download completes.

This polling architecture is **stateless on the server side** — the server never pushes events, never tracks client sessions, and each response is a complete snapshot of current state. This matches the REST model and keeps `peer.py` simple.

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
