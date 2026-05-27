# System Documentation

## 1. System Overview

This is a **trackerless peer-to-peer file sharing and messaging application**. There is no central server — every node is equal. Each peer runs a Python HTTP + UDP server (`peer.py`) that handles file sharing, chunk transfer, peer discovery, and messaging, alongside a React frontend that the peer's operator uses to interact with the network. Peers discover each other automatically via UDP broadcasts and synchronize file availability through a gossip protocol, achieving eventual consistency without any coordination server.

---

## 2. Architecture

### Per-node stack

```
┌─────────────────────────────────────────────────────────────┐
│  BROWSER (React)                                            │
│  App.tsx → api.ts → /api/* (relative URL)                   │
└────────────────────┬────────────────────────────────────────┘
                     │ HTTP (same origin — no CORS)
┌────────────────────▼────────────────────────────────────────┐
│  VITE DEV SERVER / NGINX (proxy)                            │
│  /api/* → strip /api prefix → localhost:9000                │
└────────────────────┬────────────────────────────────────────┘
                     │ HTTP localhost
┌────────────────────▼────────────────────────────────────────┐
│  peer.py  (HTTP :9000  +  UDP :9999)                        │
│  ┌──────────────┐  ┌─────────────────┐  ┌───────────────┐  │
│  │ HTTP Server  │  │  UDP Discovery  │  │ Manifest Sync │  │
│  │ (per-request │  │  (broadcast +   │  │ (gossip loop) │  │
│  │  threads)    │  │   listener)     │  │               │  │
│  └──────────────┘  └─────────────────┘  └───────────────┘  │
└────────────────────┬────────────────────────────────────────┘
                     │ HTTP  (direct peer-to-peer, no proxy)
        ┌────────────┴─────────────┐
        ▼                          ▼
   peer.py (John)            peer.py (Mark)
   100.80.161.84:9000        100.74.1.15:9000
```

### Why the browser uses `/api` (relative URL)

Each peer's frontend is served from that peer's own machine. Using a relative URL (`/api`) means the browser always talks to **its own** origin — no hardcoded IP, no CORS issue. The Vite proxy (dev) or Nginx (prod) strips the `/api` prefix and forwards the request to `localhost:9000`. The target IP is configurable via `frontend/.env` (`VITE_API_TARGET`).

Peer-to-peer communication (chunk transfer, manifest sync, messaging) happens **directly between `peer.py` instances** using their public Tailscale/LAN IPs. Python's HTTP client has no CORS restrictions, so no proxy is needed there.

---

## 3. Source File Reference

| File | Role |
|---|---|
| `src/peer.py` | Main server — HTTP endpoints, UDP discovery, gossip, chunk download/upload logic |
| `src/crypto.py` | AES-256-GCM encrypt/decrypt, PBKDF2-SHA256 key derivation |
| `src/chunking.py` | File splitting into 512 KB chunks, SHA256 hashing, chunk reassembly |
| `frontend/src/App.tsx` | Root React component — all state, polling intervals, event handlers |
| `frontend/src/api.ts` | Axios HTTP client — typed wrappers for every `peer.py` endpoint |
| `frontend/src/types.ts` | TypeScript interfaces (`NetworkFile`, `Peer`, `Message`, …) + helpers |
| `frontend/src/components/FileTable.tsx` | Network file list — status, chunk map, download/delete/pause controls |
| `frontend/src/components/UploadZone.tsx` | Drag-and-drop upload with real-time progress bar |
| `frontend/src/components/MessagingPanel.tsx` | Peer-to-peer chat with optimistic message insertion |
| `frontend/src/components/PeersPanel.tsx` | Live peer list with last-seen timestamps |
| `frontend/src/components/LocalPanel.tsx` | Diagnostic panel — locally stored files and chunks |
| `frontend/vite.config.ts` | Vite proxy config — reads `VITE_API_TARGET` from `.env` |
| `frontend/.env` | `VITE_API_TARGET=http://localhost:9000` (git-ignored) |
| `frontend/.env.example` | Committed template for the env file |

---

## 4. Global State in `peer.py`

All state lives in module-level variables protected by locks.

| Variable | Type | Purpose |
|---|---|---|
| `CATALOG` | `dict` | In-memory file registry: `file_hash → {name, size, chunks, peers, allowed_peers, password_protected}` |
| `PEERS` | `dict` | Known peers: `peer_id → {host, port, last_seen, digest}` |
| `DELETED_HASHES` | `set` | Tombstone set — hashes deleted by this peer; blocks gossip resurrection |
| `SHARING_PAUSED` | `set` | Hashes where chunk serving is paused (reversible, no data deleted) |
| `MESSAGES` | `list` | Received messages from other peers |
| `ENCRYPTION_KEY` | `bytes \| None` | 32-byte AES key derived from `PEER_PASSPHRASE`; `None` if passphrase not set |
| `PEERS_LOCK` | `Lock` | Guards `PEERS` |
| `CATALOG_LOCK` | `Lock` | Guards `CATALOG`, `DELETED_HASHES`, `SHARING_PAUSED` |
| `MESSAGES_LOCK` | `Lock` | Guards `MESSAGES` |
| `_file_dl_locks` | `dict` | Per-file locks — serialize concurrent downloads of the same file |

**Lock acquisition order:** always `PEERS_LOCK` before `CATALOG_LOCK` when both are needed. Violating this order can cause deadlocks.

---

## 5. HTTP API Reference

### Browser → peer.py (via proxy)

| Method | Path | Request | Response |
|---|---|---|---|
| GET | `/health` | — | `{status, peer_id, known_peers, known_files}` |
| GET | `/files` | — | `{files: [NetworkFile, …]}` |
| GET | `/peers` | — | `{peers: [Peer, …]}` |
| GET | `/local` | — | `{shared: […], downloads: […], chunks: […]}` |
| GET | `/messages` | — | `{messages: [Message, …]}` |
| POST | `/upload` | binary body; query: `name`, `allowed_peers?`, `file_password?` | `{file_hash, name, size, chunks}` |
| POST | `/download` | `{file_hash, file_password?}` | `{file_hash, saved_to, chunks: [indices]}` |
| POST | `/delete` | `{file_hash}` | `{ok: true}` |
| POST | `/stop_sharing` | `{file_hash}` | `{ok: true}` |
| POST | `/resume_sharing` | `{file_hash}` | `{ok: true}` |
| POST | `/open_local` | `{file_hash}` | `{ok: true}` |
| POST | `/send_message` | `{to_peer_id, text}` | `{ok: true}` |

### peer.py → peer.py (direct HTTP)

| Method | Path | Request | Response |
|---|---|---|---|
| GET | `/manifest` | — | `{peer, peers, files}` (full catalog snapshot) |
| POST | `/manifest` | full manifest object | `{ok: true}` |
| GET | `/chunk` | query: `file_hash`, `index`, `peer_id` | `{data: base64-encoded chunk}` |
| POST | `/message` | `{from_peer, text: hex-encrypted}` | `{ok: true}` |

---

## 6. Process Walkthroughs

### 6a. Peer Discovery

Two daemon threads run from startup:

```
discovery_broadcast_loop  (every 5 seconds)
  └── UDP broadcast to 255.255.255.255 + subnet (e.g. 10.0.0.255)
        Payload: { type:"peer_hello", peer_id, host, port, digest }

discovery_listener_loop  (always running)
  └── Receives UDP datagrams on port 9999
        Ignores own broadcasts (peer_id == PEER_ID)
        Calls upsert_peer() → adds/updates PEERS registry
```

**Bootstrap peers** (`BOOTSTRAP_PEERS` env var, format `host:port` or `peer_id@host:port`) are contacted by the manifest sync loop on the first cycle, before UDP discovery has had time to find them. This is how peers on different subnets (e.g. Tailscale) find each other.

**Peer liveness:** peers are removed from `PEERS` if `last_seen` exceeds `PEER_TTL_SECONDS` (default 45s). `DELETED_HASHES` persist past peer removal so deleted files cannot be resurrected.

---

### 6b. Manifest Gossip (Eventual Consistency)

A third daemon thread synchronizes file availability across the network:

```
manifest_sync_loop  (every 8 seconds)
  ├── cleanup_inactive_peers()  — prune peers not seen in 45s
  ├── For each peer in PEERS (shuffled for load balancing):
  │     GET /manifest          ← pull their catalog
  │     merge_manifest()       ← integrate into local CATALOG + PEERS
  │     POST /manifest         ← push our catalog to them
  └── For bootstrap candidates not yet in PEERS:
        Same pull + push cycle (quiet, no error logs)
```

`merge_manifest()` rules:
- Skips any `file_hash` in `DELETED_HASHES` (tombstone wins)
- Skips files where `allowed_peers` is set and `PEER_ID` is not in the list (access control)
- Adds new peers and files to local state
- Removes a peer from a file's peer list if they no longer claim it (deletion propagation)

Result: within ~8 seconds of a file being published or a peer leaving, all reachable peers converge on the same view of the network.

---

### 6c. File Upload

```
Browser
  └── UploadZone: user drops file
        → postUpload() streams binary → POST /upload?name=X[&allowed_peers=Y][&file_password=Z]

peer.py  (POST /upload handler)
  ├── Write raw bytes to data/shared/{safe_name}
  ├── If file_password provided:
  │     derive_key(file_password) → encrypt entire file (AES-256-GCM)
  │     overwrite file with encrypted bytes
  ├── chunk_file()
  │     Split into 512 KB chunks → data/chunks/{hash}.tmp/0.chunk, 1.chunk, …
  │     Compute SHA256 of each chunk
  ├── Atomic directory swap: .tmp → active (prevents partial reads)
  ├── add_file_to_catalog()
  │     Register PEER_ID as owner of all chunk indices
  │     Set allowed_peers and password_protected flags
  └── persist_file_manifest() → save to data/manifests/{hash}.json
        Returns {file_hash, name, size, chunks}

Browser
  └── fetchAll() poll → new file appears in FileTable
        Other peers pick it up within ~8s via gossip
```

---

### 6d. File Download

```
Browser
  └── FileTable: user clicks Download (enters password if required)
        → postDownload(hash, password?) → POST /download

peer.py  (POST /download handler)
  ├── Acquire per-file lock (_file_dl_locks[file_hash])
  ├── Deep-copy file_info from CATALOG (stable snapshot, no lock held during I/O)
  ├── ThreadPoolExecutor (4 workers) — for each chunk in parallel:
  │     if chunk on disk + SHA256 matches → use cached chunk
  │     else:
  │       peers_for_chunk() → list peer candidates that have this chunk
  │       fetch_chunk_from_candidates() → try each candidate in turn:
  │           GET /chunk?file_hash=X&index=N&peer_id=PEER_ID  (to other peer)
  │           base64-decode response → decrypt with ENCRYPTION_KEY (if set)
  │           SHA256 verify → write to data/chunks/{hash}/{index}.chunk
  │           add_own_chunk() → register in CATALOG
  ├── assemble_file()
  │     Concatenate chunks in index order → data/downloads/{name}
  │     SHA256 verify assembled file
  ├── If password_protected:
  │     derive_key(file_password) → decrypt assembled file
  │     On failure → delete chunks + remove PEER_ID from CATALOG → raise "wrong password"
  │     On success → overwrite file with decrypted bytes
  └── Returns {file_hash, saved_to, chunks: [indices]}

Browser
  └── downloading Set cleared → polling reverts 500ms → 3000ms
        File shows "Downloaded" status; Open button appears
```

---

### 6e. Chunk Serving (Incoming from Another Peer)

```
Other peer.py
  └── fetch_chunk() → GET /chunk?file_hash=X&index=N&peer_id=Y

Your peer.py  (GET /chunk handler)
  ├── Check allowed_peers:
  │     If set and requesting peer_id not in list → 403 Forbidden
  ├── Check SHARING_PAUSED:
  │     If file_hash in set → 403 "sharing paused"
  ├── Read data/chunks/{hash}/{index}.chunk
  ├── If ENCRYPTION_KEY set → encrypt chunk bytes (AES-256-GCM)
  ├── base64-encode
  └── Return {file_hash, index, data: "...base64..."}
```

The requesting peer then base64-decodes, decrypts with its own `ENCRYPTION_KEY`, verifies the SHA256 hash, and writes the chunk to disk. Both peers must share the same `PEER_PASSPHRASE` for this to succeed.

---

### 6f. Messaging

```
Browser
  └── MessagingPanel: select peer → type text → send
        → POST /send_message {to_peer_id, text}

peer.py  (POST /send_message handler)
  ├── Look up target peer in PEERS → get host:port
  ├── Encode text as UTF-8 bytes
  ├── If ENCRYPTION_KEY set → encrypt → hex-encode
  └── POST /message to target's peer.py {from_peer: PEER_ID, text: hex}

Target peer.py  (POST /message handler)
  ├── hex-decode → decrypt with ENCRYPTION_KEY (if set)
  └── Append {from_peer, text, timestamp} to MESSAGES list

Browser (target peer's operator)
  └── GET /messages polled every 2s → MessagingPanel shows new message

Optimistic UI: sent message is added to React state immediately
(before the API call resolves), so the sender sees it instantly.
```

Both peers must share the same `PEER_PASSPHRASE`; mismatched passphrases cause decryption to fail and the message is dropped.

---

### 6g. Stop Sharing / Resume

```
Browser: clicks Stop
  → POST /stop_sharing {file_hash}
  → peer.py: SHARING_PAUSED.add(file_hash)

Effects:
  - catalog_files_snapshot() omits this peer from the file's peers dict
    → within ~8s, other peers stop listing you as a source
  - GET /chunk returns 403 if another peer tries to fetch from you
  - Your local chunks are untouched; file stays on disk

Browser: clicks Resume
  → POST /resume_sharing {file_hash}
  → peer.py: SHARING_PAUSED.discard(file_hash)
  → You reappear as a source within ~8s (next gossip cycle)

Note: SHARING_PAUSED is in-memory only. Restarting peer.py clears it.
```

---

### 6h. Delete

```
Browser: two-click confirm → POST /delete {file_hash}

peer.py  (POST /delete handler)
  ├── with CATALOG_LOCK:
  │     CATALOG.pop(file_hash)
  │     DELETED_HASHES.add(file_hash)   ← tombstone
  ├── shutil.rmtree(CHUNKS_DIR / file_hash)
  ├── (data/manifests/{hash}.json).unlink()
  └── (data/shared/{name}).unlink()  if present

Gossip propagation:
  - This peer no longer includes file in its manifest broadcasts
  - Other peers: merge_manifest() skips hashes in DELETED_HASHES
  - File disappears from all peers' dashboards within ~8s
  - DELETED_HASHES persists for the lifetime of the process,
    preventing any peer from resurrecting the file via gossip
```

---

## 7. Encryption Layers

There are two independent encryption layers that can both be active at the same time.

### Layer 1 — Transit Encryption (`PEER_PASSPHRASE`)

Protects chunks and messages as they travel between peers.

| Property | Value |
|---|---|
| Applies to | Every chunk served/fetched + every message |
| Key derivation | `PBKDF2-HMAC-SHA256(passphrase, salt=b"pdc-p2p-v1", iterations=100_000)` → 32 bytes |
| Algorithm | AES-256-GCM with random 12-byte nonce (prepended to ciphertext) |
| Scope | All peers in the network must share the same `PEER_PASSPHRASE` |
| Failure mode | Decryption exception → SHA256 mismatch → chunk rejected; message dropped |

Chunks are stored **decrypted** on disk. Encryption only wraps them in transit (during `GET /chunk`).

### Layer 2 — File Password (`file_password`)

Protects the content of a specific file at rest.

| Property | Value |
|---|---|
| Applies to | The entire assembled file (not individual chunks) |
| Key derivation | Same PBKDF2 scheme, but keyed from the per-file password |
| When encrypted | On upload, before chunking — chunks contain encrypted data |
| When decrypted | After reassembly on download — decrypted to `downloads/` |
| Failure mode | Wrong password → chunks deleted, PEER_ID removed from CATALOG, error returned |
| Scope | Only peers who know the password can decrypt; others see the file but can't read it |

Both layers are optional and independent. A file can have:
- Neither (plaintext, open access)
- Layer 1 only (transit encryption, network-wide passphrase)
- Layer 2 only (file password, no transit encryption)
- Both (transit encrypted + file password required to read)

---

## 8. Frontend Data Flow

### Polling intervals

| Data fetched | Normal interval | Fast interval |
|---|---|---|
| Health (`/health`) | 2 000 ms | — |
| Files + Peers (`/files`, `/peers`) | 3 000 ms | 500 ms while any file is downloading |
| Messages (`/messages`) | 2 000 ms | — |

Fast polling is triggered by adding a hash to the `downloading` Set in `App.tsx` and cleared when the download resolves.

### State management

All state lives in `App.tsx`. There is no Redux, Zustand, or React Context. Components receive data as props and communicate upward via callback props:

```
App.tsx
  ├── state: files, peers, local, messages, health, downloading, search, toast
  ├── handlers: handleDownload, handleUpload, handleDelete,
  │             handleStopSharing, handleResumeSharing,
  │             handleSend, handleOpenLocal
  └── renders:
        ├── Header         ← peerId, connected, peerCount, fileCount
        ├── FileTable      ← files, downloading, onDownload, onDelete,
        │                     onStopSharing, onResumeSharing, peerId
        ├── UploadZone     ← peers (for access control selector), onUpload
        ├── PeersPanel     ← peers
        ├── LocalPanel     ← local
        └── MessagingPanel ← peers, messages, peerId, onSend
```

### Key component behaviours

| Component | Internal state | Notable behaviour |
|---|---|---|
| `FileTable` | `expanded` (chunk map rows), `filePasswords`, `confirmingDelete` | Two-click delete confirm; "Only source!" pulse warning; chunk map visualization; Open button for downloaded files |
| `UploadZone` | `uploading`, `uploadPct`, `selectedPeers`, `filePassword` | Streams file as binary with progress callback; optional access control + file password |
| `MessagingPanel` | `selectedPeer`, `text`, `sending` | Optimistic message insert; auto-scroll on new message; Enter to send |

---

## 9. Thread Model

```
Main thread         → ThreadingHTTPServer.serve_forever()
                       Spawns one thread per incoming HTTP request

Daemon thread 1     → discovery_listener_loop
                       Blocks on UDP recv(), port 9999
                       Calls upsert_peer() on each valid HELLO

Daemon thread 2     → discovery_broadcast_loop
                       Wakes every HELLO_INTERVAL_SECONDS (5s)
                       Sends UDP broadcast to 255.255.255.255 + subnet

Daemon thread 3     → manifest_sync_loop
                       Wakes every MANIFEST_INTERVAL_SECONDS (8s)
                       Pulls + pushes manifests to all known peers

Download pool       → ThreadPoolExecutor(max_workers=4)
                       Created per download call
                       Fetches up to 4 chunks in parallel
```

HTTP request threads and the manifest sync thread both access `CATALOG` and `PEERS`. Locks ensure safety; the acquisition order (PEERS_LOCK → CATALOG_LOCK) prevents circular waits.

---

## 10. Data Directory Layout

```
data/{peer_name}/
│
├── shared/                     ← original files you uploaded/published
│     example.pdf
│     report.docx
│
├── chunks/
│     └── {file_hash}/          ← one directory per file
│           0.chunk             ← 512 KB raw chunk (stored decrypted)
│           1.chunk
│           2.chunk
│           …
│
├── downloads/                  ← fully assembled + decrypted output files
│     example.pdf               ← ready to open
│
└── manifests/
      {file_hash}.json          ← persisted CATALOG entry for files you own
                                   Restored on startup via restore_local_manifests()
```

Manifests are the only state persisted to disk. `PEERS`, `DELETED_HASHES`, `SHARING_PAUSED`, and `MESSAGES` are in-memory only and reset on restart. File chunks and downloaded files survive restarts.

---

## 11. Configuration Reference

All configuration is via environment variables (set in `start.bat` or shell before launching `peer.py`).

| Variable | Default | Description |
|---|---|---|
| `PEER_ID` | `"peer"` | Unique identifier for this node |
| `PEER_HOST` | `"0.0.0.0"` | Bind address for HTTP server |
| `PEER_ADVERTISE_HOST` | `PEER_HOST` | IP advertised to other peers (use Tailscale IP) |
| `PEER_PORT` | `9000` | HTTP server port |
| `DISCOVERY_PORT` | `9999` | UDP broadcast port |
| `BOOTSTRAP_PEERS` | `""` | Comma-separated `host:port` or `peer_id@host:port` entries |
| `PEER_PASSPHRASE` | `""` | Shared passphrase for transit encryption; empty = no encryption |
| `DATA_DIR` | `"/data"` | Root data directory (`data\peer1` on Windows) |
| `PEER_TTL_SECONDS` | `45` | Seconds before an inactive peer is removed |
| `HELLO_INTERVAL_SECONDS` | `5` | UDP broadcast frequency |
| `MANIFEST_INTERVAL_SECONDS` | `8` | Gossip sync frequency |
| `AUTO_BOOTSTRAP_PORTS` | `"9000-9010"` | Port range scanned for local peers (localhost only) |

Frontend:

| Variable | File | Description |
|---|---|---|
| `VITE_API_TARGET` | `frontend/.env` | URL of this peer's `peer.py` HTTP server |
