# Trackerless Peer-to-Peer File Sharing

This project is a Python prototype for decentralized file sharing on a local network. Each computer runs the same peer application. There is no central tracker server: peers discover each other, exchange metadata, and download file chunks directly from one another.

The current name and visual branding are temporary. They can be replaced later without changing the core peer-to-peer system.

## Features

- Trackerless peer-to-peer file sharing
- LAN peer discovery using UDP broadcast
- Optional bootstrap peers for Docker, VPNs, or networks that block broadcast
- File chunking and reconstruction
- SHA-256 file and chunk verification
- Parallel chunk downloads
- Direct peer-to-peer chunk serving over HTTP/TCP
- Tkinter desktop launcher
- Docker Compose demo with three peers

## Requirements

For native desktop usage:

- Python 3.12 or newer recommended
- Windows, macOS, or Linux
- No third-party Python packages required

For Docker usage:

- Docker Desktop or Docker Engine
- Docker Compose

## Project Structure

```text
.
|-- Dockerfile
|-- docker-compose.yml
|-- gui_launcher.py
|-- README.md
|-- data/
|   `-- peer folders and runtime files
`-- src/
    |-- chunking.py
    |-- http_utils.py
    `-- peer.py
```

Important files:

- `src/peer.py`: peer server, discovery, metadata sync, publish/download endpoints
- `src/chunking.py`: file splitting, hashing, and reconstruction
- `src/http_utils.py`: shared JSON HTTP helpers
- `gui_launcher.py`: desktop GUI launcher
- `docker-compose.yml`: local three-peer Docker demo

## How It Works

Each peer runs an HTTP server for local control and peer-to-peer transfer. HTTP uses TCP. Peers also send UDP discovery messages on the discovery port.

Default ports:

- Peer HTTP/TCP: `9000`
- UDP discovery: `9999`

Peer discovery works in two ways:

- **UDP broadcast:** peers on the same LAN can automatically find each other.
- **Bootstrap peers:** a peer can be given one or more `host:port` addresses to contact at startup.

In short:

```text
UDP 9999 = peer discovery
TCP 9000 = metadata, control API, and file chunk transfer
```

When a peer starts, it automatically publishes files that already exist directly inside its `shared/` folder.
Manual publishing is only needed for files added after the peer is already running.

When a file is published:

1. The file is split into chunks.
2. Each chunk receives a SHA-256 hash.
3. The full file receives a SHA-256 hash.
4. The local peer records that it owns the chunks.
5. Other peers learn about the file through `/manifest` metadata exchange.

When a file is downloaded:

1. The downloader checks its local metadata catalog.
2. It finds peers that own the needed chunks.
3. It requests chunks directly with `/chunk`.
4. It verifies each chunk hash.
5. It reconstructs the final file.
6. It becomes a source for the chunks it now owns.

## Native GUI Setup

Start the desktop launcher from the project folder:

```powershell
python -m gui_launcher
```

If Python cannot find the module, run it as a script instead:

```powershell
python gui_launcher.py
```

Fill in the peer settings:

```text
Peer ID: peer1
This laptop IP: 127.0.0.1 or your LAN/Tailscale IP
Peer port: 9000
Discovery port: 9999
Bootstrap peers: optional
Data folder: data/gui-peer
```

Click **Start service**.

Use the GUI to:

- publish files
- refresh known network files
- download selected files
- view local shared/downloaded files
- view discovered peers

Files already in the selected data folder's `shared/` directory are published automatically when the service starts.

## Same-Computer Testing

You can run multiple GUI windows on one computer. Each peer needs a unique peer ID, unique peer port, and separate data folder.

Example:

```text
Peer 1
Peer ID: peer1
This laptop IP: 127.0.0.1
Peer port: 9000
Discovery port: 9999
Bootstrap peers: blank
Data folder: data/gui-peer1

Peer 2
Peer ID: peer2
This laptop IP: 127.0.0.1
Peer port: 9001
Discovery port: 9999
Bootstrap peers: blank
Data folder: data/gui-peer2
```

For local testing, peers advertising `127.0.0.1` automatically probe local ports `9000-9010`, so `Bootstrap peers` can usually stay blank.

## Same-Wi-Fi Testing

On each computer:

1. Copy or clone this project.
2. Open the project folder.
3. Run:

```powershell
python -m gui_launcher
```

Find each computer's Wi-Fi IPv4 address:

```powershell
ipconfig
```

Use the Wi-Fi IPv4 address in **This laptop IP**.

Example:

```text
Computer 1
Peer ID: peer1
This laptop IP: 192.168.1.25
Peer port: 9000
Discovery port: 9999
Bootstrap peers: blank

Computer 2
Peer ID: peer2
This laptop IP: 192.168.1.40
Peer port: 9000
Discovery port: 9999
Bootstrap peers: blank
```

If automatic discovery does not work, use bootstrap peers:

```text
Computer 1 Bootstrap peers: 192.168.1.40:9000
Computer 2 Bootstrap peers: 192.168.1.25:9000
```

Allow firewall access on every computer:

```text
TCP 9000
UDP 9999
```

## Different-Wi-Fi Testing

UDP broadcast usually does not cross different Wi-Fi networks. Use a VPN-style LAN such as Tailscale.

1. Install Tailscale on each computer.
2. Sign in to the same Tailscale network.
3. Use each computer's Tailscale IP in **This laptop IP**.
4. Put the other computer's Tailscale address in **Bootstrap peers**.

Example:

```text
Computer 1
This laptop IP: 100.80.12.34
Bootstrap peers: 100.90.55.10:9000

Computer 2
This laptop IP: 100.90.55.10
Bootstrap peers: 100.80.12.34:9000
```

## Docker Setup

Docker is used for a local backend demo. It starts three peer containers on one machine. The Docker image runs only the peer backend from `src/`; it does not include the desktop GUI.

Build and start the three-peer demo:

```powershell
docker compose up --build
```

The peers are exposed on:

```text
Peer 1: http://localhost:9001
Peer 2: http://localhost:9002
Peer 3: http://localhost:9003
```

Internally, every container listens on TCP `9000`; Docker maps those internal ports to host ports `9001`, `9002`, and `9003`.

Stop the demo:

```powershell
docker compose down
```

## Docker Demo Commands

Use `curl.exe` in PowerShell so Windows does not use the `curl` alias for `Invoke-WebRequest`.

The sample file in `data/peer1/shared/` is published automatically when peer 1 starts. After a few seconds, list files known by peer 1:

```powershell
curl.exe http://localhost:9001/files
```

List files known by peer 2 after manifest sync:

```powershell
curl.exe http://localhost:9002/files
```

Copy the returned `file_hash`, then download from peer 2:

```powershell
curl.exe -X POST http://localhost:9002/download -H "Content-Type: application/json" -d "{\"file_hash\":\"PASTE_FILE_HASH_HERE\"}"
```

Download from peer 3:

```powershell
curl.exe -X POST http://localhost:9003/download -H "Content-Type: application/json" -d "{\"file_hash\":\"PASTE_FILE_HASH_HERE\"}"
```

Inspect peers and local files:

```powershell
curl.exe http://localhost:9001/peers
curl.exe http://localhost:9002/local
curl.exe http://localhost:9003/local
```

## Native HTTP API

Each peer exposes these endpoints:

```text
GET  /health
GET  /peers
GET  /files
GET  /manifest
GET  /local
GET  /chunk?file_hash=<hash>&index=<chunk_index>
POST /publish
POST /download
POST /manifest
```

Publish a local file:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:9000/publish" `
  -ContentType "application/json" `
  -Body '{"path":"C:\\path\\to\\file.pdf"}'
```

Use this endpoint for files added while the peer is already running. Files already in `shared/` are published at startup.

Download a known file:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:9000/download" `
  -ContentType "application/json" `
  -Body '{"file_hash":"PASTE_FILE_HASH_HERE"}'
```

## Troubleshooting

### Both GUI windows show the same peer

Both windows are probably using the same peer port. Use different ports:

```text
peer1: 9000
peer2: 9001
peer3: 9002
```

### Peers do not discover each other

Check:

- each peer has a unique peer ID
- each peer advertises the correct LAN/Tailscale IP
- TCP peer port is allowed by firewall
- UDP discovery port is allowed by firewall
- bootstrap peers are written as `host:port`

### Timeout to the wrong IP

If logs show a timeout to an unexpected IP, the peer probably advertised the wrong network adapter. Set **This laptop IP** to the reachable Wi-Fi or Tailscale IP.

### PowerShell curl error

Use `curl.exe`, not `curl`, or use `Invoke-RestMethod`.

## Development Checks

Compile all Python files:

```powershell
python -m compileall gui_launcher.py src
```

Validate Docker Compose:

```powershell
docker compose config
```

## Cleanup

Stop Docker containers:

```powershell
docker compose down
```

Remove generated Python caches if needed:

```powershell
Remove-Item -Recurse -Force __pycache__, src\__pycache__
```

Runtime file data is stored under `data/`. Delete only the peer data folders you no longer need.
