import base64
import hashlib
import json
import os
import random
import shutil
import socket
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from chunking import CHUNK_SIZE, assemble_file, chunk_file, sha256_bytes, sha256_file
from crypto import derive_key, encrypt, decrypt
from http_utils import not_found, read_json, request_json, send_json


PEER_ID = os.getenv("PEER_ID", "peer")
PEER_HOST = os.getenv("PEER_HOST", "0.0.0.0")
PEER_ADVERTISE_HOST = os.getenv("PEER_ADVERTISE_HOST", PEER_HOST)
PEER_PORT = int(os.getenv("PEER_PORT", "9000"))
DISCOVERY_PORT = int(os.getenv("DISCOVERY_PORT", "9999"))
BOOTSTRAP_PEERS = [item.strip() for item in os.getenv("BOOTSTRAP_PEERS", "").split(",") if item.strip()]
PEER_PASSPHRASE = os.getenv("PEER_PASSPHRASE", "")
ENCRYPTION_KEY = derive_key(PEER_PASSPHRASE) if PEER_PASSPHRASE else None
AUTO_BOOTSTRAP_PORTS = os.getenv("AUTO_BOOTSTRAP_PORTS", "9000-9010")
PEER_TTL_SECONDS = int(os.getenv("PEER_TTL_SECONDS", "45"))
HELLO_INTERVAL_SECONDS = int(os.getenv("HELLO_INTERVAL_SECONDS", "5"))
MANIFEST_INTERVAL_SECONDS = int(os.getenv("MANIFEST_INTERVAL_SECONDS", "8"))
DATA_DIR = Path(os.getenv("DATA_DIR", "/data"))
SHARED_DIR = DATA_DIR / "shared"
CHUNKS_DIR = DATA_DIR / "chunks"
DOWNLOADS_DIR = DATA_DIR / "downloads"
MANIFESTS_DIR = DATA_DIR / "manifests"
GUI_MODE = os.getenv("PEER_GUI_MODE") == "gui"

# Fine-grained mutexes: separate locks per resource reduce contention across threads.
# Acquisition order rule: always PEERS_LOCK before CATALOG_LOCK when both are needed
# to prevent deadlock (consistent ordering eliminates circular wait).
PEERS_LOCK = threading.Lock()        # mutual exclusion for the PEERS registry
CATALOG_LOCK = threading.Lock()      # mutual exclusion for CATALOG and chunk ownership records
PEERS = {}
CATALOG = {}
# Hashes explicitly deleted by this peer; merge_manifest skips them so peers
# cannot resurrect files the user has chosen to remove.
DELETED_HASHES: set = set()

MESSAGES: list = []
MESSAGES_LOCK = threading.Lock()

# Per-file download lock registry: one Lock per file_hash so concurrent /download
# requests for the same file serialize instead of racing on chunk writes and assembly.
_file_dl_locks: dict = {}
_file_dl_locks_mu = threading.Lock()    # guards _file_dl_locks dict itself


def now():
    return int(time.time())


def ensure_dirs():
    SHARED_DIR.mkdir(parents=True, exist_ok=True)
    CHUNKS_DIR.mkdir(parents=True, exist_ok=True)
    DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
    MANIFESTS_DIR.mkdir(parents=True, exist_ok=True)


def chunk_path(file_hash, index):
    return CHUNKS_DIR / file_hash / f"{index}.chunk"


def manifest_path(file_hash):
    return MANIFESTS_DIR / f"{file_hash}.json"


def normalize_chunks(chunks):
    return sorted(
        [
            {
                "index": int(chunk["index"]),
                "hash": str(chunk["hash"]),
                "size": int(chunk["size"]),
            }
            for chunk in chunks
        ],
        key=lambda item: item["index"],
    )


def normalize_owned_chunks(chunks):
    return sorted({int(index) for index in chunks})


def chunk_metadata_matches(existing_chunks, incoming_chunks):
    return normalize_chunks(existing_chunks) == normalize_chunks(incoming_chunks)


def persist_file_manifest(file_info):
    ensure_dirs()
    manifest = {
        "file_hash": file_info["file_hash"],
        "name": file_info["name"],
        "size": int(file_info["size"]),
        "chunk_size": int(file_info.get("chunk_size", CHUNK_SIZE)),
        "chunks": normalize_chunks(file_info["chunks"]),
        "allowed_peers": list(file_info.get("allowed_peers", [])),
        "password_protected": bool(file_info.get("password_protected", False)),
    }
    target = manifest_path(file_info["file_hash"])
    temp_target = target.with_suffix(".tmp")
    temp_target.write_text(json.dumps(manifest, sort_keys=True, indent=2), encoding="utf-8")
    temp_target.replace(target)


def verified_local_chunks(file_hash, chunks):
    owned = []
    for chunk in normalize_chunks(chunks):
        path = chunk_path(file_hash, chunk["index"])
        if not path.exists():
            continue
        try:
            if sha256_bytes(path.read_bytes()) == chunk["hash"]:
                owned.append(chunk["index"])
        except OSError:
            continue
    return owned


def upsert_peer(peer_id, host, port, digest=None, last_seen=None):
    if not peer_id or peer_id == PEER_ID:
        return
    with PEERS_LOCK:
        PEERS[peer_id] = {
            "peer_id": peer_id,
            "host": host,
            "port": int(port),
            "last_seen": int(last_seen or now()),
            "digest": digest or PEERS.get(peer_id, {}).get("digest", ""),
        }


def remove_peer(peer_id):
    # Acquire locks separately (not nested) in the canonical order: PEERS first, CATALOG second.
    with PEERS_LOCK:
        PEERS.pop(peer_id, None)
    with CATALOG_LOCK:
        for file_info in CATALOG.values():
            file_info.get("peers", {}).pop(peer_id, None)


def cleanup_inactive_peers():
    cutoff = now() - PEER_TTL_SECONDS
    with PEERS_LOCK:
        inactive = [pid for pid, p in PEERS.items() if p.get("last_seen", 0) < cutoff]
        for pid in inactive:
            PEERS.pop(pid, None)
    # Only acquire CATALOG_LOCK if there is actually something to clean up.
    if inactive:
        with CATALOG_LOCK:
            for pid in inactive:
                for file_info in CATALOG.values():
                    file_info.get("peers", {}).pop(pid, None)


def add_file_to_catalog(file_hash, name, size, chunks, owner_peer_id, owned_chunks,
                         allowed_peers=None, password_protected=False):
    normalized_chunks = normalize_chunks(chunks)
    owned = normalize_owned_chunks(owned_chunks)
    with CATALOG_LOCK:
        if file_hash in DELETED_HASHES:
            return file_hash
        existing = CATALOG.get(file_hash)
        if existing and not chunk_metadata_matches(existing["chunks"], normalized_chunks):
            raise ValueError(f"conflicting metadata for file {file_hash}")
        file_info = CATALOG.setdefault(
            file_hash,
            {
                "file_hash": file_hash,
                "name": name,
                "size": int(size),
                "chunk_size": CHUNK_SIZE,
                "chunks": normalized_chunks,
                "peers": {},
                "allowed_peers": list(allowed_peers or []),
                "password_protected": bool(password_protected),
            },
        )
        file_info["name"] = file_info.get("name") or name
        file_info["size"] = int(file_info.get("size") or size)
        if owned:
            file_info["peers"][owner_peer_id] = {
                "peer_id": owner_peer_id,
                "chunks": owned,
                "last_seen": now(),
            }
        # Snapshot before releasing the lock so persist sees a consistent state.
        manifest_snapshot = json.loads(json.dumps(file_info))
    # Persist outside the lock: file I/O under a mutex would block all other threads
    # waiting on CATALOG_LOCK (chunk downloads, manifest sync, health checks, etc.).
    persist_file_manifest(manifest_snapshot)
    return file_hash


def add_own_chunk(file_hash, chunk):
    with CATALOG_LOCK:
        file_info = CATALOG.get(file_hash)
        if not file_info:
            return
        owned = file_info["peers"].setdefault(
            PEER_ID,
            {"peer_id": PEER_ID, "chunks": [], "last_seen": now()},
        )
        chunks = set(int(index) for index in owned.get("chunks", []))
        chunks.add(int(chunk["index"]))
        owned["chunks"] = sorted(chunks)
        owned["last_seen"] = now()


def local_peer_entry():
    return {
        "peer_id": PEER_ID,
        "host": PEER_ADVERTISE_HOST,
        "port": PEER_PORT,
        "last_seen": now(),
        "digest": catalog_digest(),
    }


def catalog_files_snapshot():
    with CATALOG_LOCK:
        files = []
        for file_info in CATALOG.values():
            peers = {
                peer_id: {
                    "peer_id": peer_id,
                    "chunks": normalize_owned_chunks(owner.get("chunks", [])),
                    "last_seen": int(owner.get("last_seen", 0)),
                }
                for peer_id, owner in file_info.get("peers", {}).items()
            }
            local_chunks = len(peers.get(PEER_ID, {}).get("chunks", []))
            files.append(
                {
                    "file_hash": file_info["file_hash"],
                    "name": file_info["name"],
                    "size": int(file_info["size"]),
                    "chunk_size": int(file_info.get("chunk_size", CHUNK_SIZE)),
                    "chunks": normalize_chunks(file_info["chunks"]),
                    "peers": peers,
                    "local_chunks": local_chunks,
                    "allowed_peers": list(file_info.get("allowed_peers", [])),
                    "password_protected": bool(file_info.get("password_protected", False)),
                }
            )
    return sorted(files, key=lambda item: (item["name"], item["file_hash"]))


def peers_snapshot():
    cleanup_inactive_peers()
    with PEERS_LOCK:
        peers = list(PEERS.values())
    return sorted(peers, key=lambda item: item["peer_id"])


def catalog_digest():
    with CATALOG_LOCK:
        digest_input = []
        for file_hash, file_info in sorted(CATALOG.items()):
            owners = []
            for peer_id, owner in sorted(file_info.get("peers", {}).items()):
                owners.append([peer_id, normalize_owned_chunks(owner.get("chunks", []))])
            digest_input.append([file_hash, normalize_chunks(file_info["chunks"]), owners])
    raw = json.dumps(digest_input, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def build_manifest():
    return {
        "peer": local_peer_entry(),
        "peers": [local_peer_entry(), *peers_snapshot()],
        "files": catalog_files_snapshot(),
    }


def merge_manifest(manifest, source_peer=None):
    peer = manifest.get("peer") or {}
    advertising_peer_id = peer.get("peer_id")
    if peer:
        upsert_peer(advertising_peer_id, peer.get("host"), peer.get("port"), peer.get("digest"))

    for known_peer in manifest.get("peers", []):
        upsert_peer(
            known_peer.get("peer_id"),
            known_peer.get("host"),
            known_peer.get("port"),
            known_peer.get("digest"),
            known_peer.get("last_seen"),
        )

    # Collect hashes that the advertising peer currently claims ownership of.
    advertised_hashes = set()
    for file_info in manifest.get("files", []):
        owners = file_info.get("peers", {})
        if advertising_peer_id and advertising_peer_id in owners and owners[advertising_peer_id].get("chunks"):
            advertised_hashes.add(file_info["file_hash"])

    for file_info in manifest.get("files", []):
        for peer_id, owner in file_info.get("peers", {}).items():
            try:
                add_file_to_catalog(
                    file_info["file_hash"],
                    file_info["name"],
                    file_info["size"],
                    file_info["chunks"],
                    peer_id,
                    owner.get("chunks", []),
                )
            except ValueError as exc:
                print(f"[{PEER_ID}] rejected metadata from {source_peer or 'peer'}: {exc}", flush=True)

    # Remove the advertising peer from any files it is no longer claiming.
    # This ensures deletions propagate: once a peer stops advertising a file,
    # other peers stop listing it as a source within one sync cycle.
    if advertising_peer_id:
        with CATALOG_LOCK:
            for file_hash, file_info in CATALOG.items():
                if advertising_peer_id in file_info.get("peers", {}) and file_hash not in advertised_hashes:
                    file_info["peers"].pop(advertising_peer_id, None)


def prefer_observed_peer_host(manifest, observed_host):
    if not observed_host or observed_host.startswith("127."):
        return manifest
    adjusted = json.loads(json.dumps(manifest))
    peer = adjusted.get("peer") or {}
    advertised_host = str(peer.get("host", "")).strip()
    if advertised_host and advertised_host != observed_host:
        peer["host"] = observed_host
        adjusted["peer"] = peer
        for known_peer in adjusted.get("peers", []):
            if known_peer.get("peer_id") == peer.get("peer_id"):
                known_peer["host"] = observed_host
        print(
            f"[{PEER_ID}] learned {peer.get('peer_id')} is reachable at {observed_host} "
            f"instead of advertised {advertised_host}",
            flush=True,
        )
    return adjusted


def parse_bootstrap_peer(value):
    peer_id = None
    target = value
    if "@" in value:
        peer_id, target = value.split("@", 1)
    host, _, port = target.rpartition(":")
    if not host or not port:
        raise ValueError(f"bootstrap peer must be host:port or peer_id@host:port: {value}")
    return peer_id or f"bootstrap-{host}-{port}", host, int(port)


def parse_port_range(value):
    ports = set()
    for part in value.split(","):
        item = part.strip()
        if not item:
            continue
        if "-" in item:
            start, end = item.split("-", 1)
            ports.update(range(int(start), int(end) + 1))
        else:
            ports.add(int(item))
    return sorted(port for port in ports if 1 <= port <= 65535)


def should_probe_local_bootstrap():
    host = PEER_ADVERTISE_HOST.strip().lower()
    return host in {"127.0.0.1", "localhost", "::1"} or host.startswith("127.")


def bootstrap_peer_candidates():
    candidates = []
    for value in BOOTSTRAP_PEERS:
        try:
            peer_id, host, port = parse_bootstrap_peer(value)
            candidates.append(
                {
                    "peer_id": peer_id,
                    "host": host,
                    "port": port,
                    "last_seen": now(),
                    "digest": "",
                    "candidate": True,
                    "quiet": False,
                }
            )
        except Exception as exc:
            print(f"[{PEER_ID}] ignored bootstrap peer {value}: {exc}", flush=True)
    if should_probe_local_bootstrap():
        try:
            for port in parse_port_range(AUTO_BOOTSTRAP_PORTS):
                if port != PEER_PORT:
                    candidates.append(
                        {
                            "peer_id": f"local-{port}",
                            "host": "127.0.0.1",
                            "port": port,
                            "last_seen": now(),
                            "digest": "",
                            "candidate": True,
                            "quiet": True,
                        }
                    )
        except Exception as exc:
            print(f"[{PEER_ID}] ignored AUTO_BOOTSTRAP_PORTS={AUTO_BOOTSTRAP_PORTS}: {exc}", flush=True)
    return candidates


def sync_targets():
    cleanup_inactive_peers()
    targets = peers_snapshot()
    seen_addresses = {(peer.get("host"), int(peer.get("port", 0))) for peer in targets}
    seen_peer_ids = {peer.get("peer_id") for peer in targets}
    for candidate in bootstrap_peer_candidates():
        address = (candidate.get("host"), int(candidate.get("port", 0)))
        if address in seen_addresses or candidate.get("peer_id") in seen_peer_ids:
            continue
        targets.append(candidate)
        seen_addresses.add(address)
        seen_peer_ids.add(candidate.get("peer_id"))
    return targets


def peer_url(peer, path):
    return f"http://{peer['host']}:{peer['port']}{path}"


def peer_chunk_url(peer, file_hash, chunk):
    return peer_url(peer, f"/chunk?file_hash={file_hash}&index={chunk['index']}&peer_id={PEER_ID}")


def fetch_chunk(peer, file_hash, chunk):
    url = peer_chunk_url(peer, file_hash, chunk)
    payload = request_json("GET", url, timeout=10)
    raw = base64.b64decode(payload["data"].encode("ascii"))
    data = decrypt(raw, ENCRYPTION_KEY) if ENCRYPTION_KEY else raw
    actual_hash = sha256_bytes(data)
    if actual_hash != chunk["hash"]:
        raise ValueError(f"chunk {chunk['index']} failed hash check")
    target = chunk_path(file_hash, chunk["index"])
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    add_own_chunk(file_hash, chunk)
    return chunk["index"]


def is_gui_reachable_host(host):
    if not GUI_MODE:
        return True
    return bool(str(host or "").strip())


def peer_lookup():
    with PEERS_LOCK:
        return {peer_id: dict(peer) for peer_id, peer in PEERS.items()}


def peers_for_chunk(file_info, chunk_index, offset=0):
    peers = peer_lookup()
    candidates = []
    for peer_id, owned in file_info["peers"].items():
        if peer_id == PEER_ID:
            continue
        if chunk_index in owned.get("chunks", []) and peer_id in peers:
            peer = peers[peer_id]
            if is_gui_reachable_host(peer.get("host")):
                candidates.append(peer)
    candidates.sort(key=lambda item: item["peer_id"])
    if candidates:
        rotation = offset % len(candidates)
        candidates = candidates[rotation:] + candidates[:rotation]
    return candidates


def fetch_chunk_from_candidates(candidates, file_hash, chunk):
    errors = []
    for peer in candidates:
        try:
            return fetch_chunk(peer, file_hash, chunk)
        except Exception as exc:
            peer_address = f"{peer.get('peer_id')}({peer.get('host')}:{peer.get('port')})"
            errors.append(f"{peer_address}: {exc}")
            remove_peer(peer.get("peer_id"))
    short_errors = "; ".join(errors[:3])
    if len(errors) > 3:
        short_errors += f"; plus {len(errors) - 3} more"
    raise RuntimeError(f"chunk {chunk['index']} failed from all reachable peers: {short_errors}")


def publish_file(path, allowed_peers=None, password_protected=False):
    ensure_dirs()
    source = Path(path)
    if not source.exists():
        raise FileNotFoundError(f"{source} does not exist")
    if source.stat().st_size == 0:
        raise ValueError(f"{source.name}: cannot publish an empty file")

    file_hash = sha256_file(source)
    file_chunk_dir = CHUNKS_DIR / file_hash
    temp_chunk_dir = CHUNKS_DIR / f"{file_hash}.tmp"
    old_chunk_dir = CHUNKS_DIR / f"{file_hash}.old"

    if temp_chunk_dir.exists():
        shutil.rmtree(temp_chunk_dir)
    chunks = chunk_file(source, temp_chunk_dir)

    # Swap temp dir into place so concurrent /chunk readers are never left with a missing dir.
    # The rename window is tiny; a reader that hits it gets a transient 404.
    if file_chunk_dir.exists():
        file_chunk_dir.rename(old_chunk_dir)
    temp_chunk_dir.rename(file_chunk_dir)
    if old_chunk_dir.exists():
        shutil.rmtree(old_chunk_dir)

    add_file_to_catalog(
        file_hash,
        source.name,
        source.stat().st_size,
        chunks,
        PEER_ID,
        [chunk["index"] for chunk in chunks],
        allowed_peers=allowed_peers,
        password_protected=password_protected,
    )
    return {
        "file_hash": file_hash,
        "name": source.name,
        "size": source.stat().st_size,
        "chunks": len(chunks),
    }


def publish_shared_files():
    published = []
    for source in sorted(path for path in SHARED_DIR.iterdir() if path.is_file()):
        try:
            result = publish_file(source)
            published.append(result)
            print(
                f"[{PEER_ID}] auto-published shared file {result['name']} "
                f"({result['chunks']} chunks)",
                flush=True,
            )
        except Exception as exc:
            print(f"[{PEER_ID}] skipped shared file {source.name}: {exc}", flush=True)
    if not published:
        print(f"[{PEER_ID}] no shared files to auto-publish", flush=True)
    return published


def restore_local_manifests():
    restored = []
    for path in sorted(MANIFESTS_DIR.glob("*.json")):
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
            chunks = normalize_chunks(manifest["chunks"])
            owned = verified_local_chunks(manifest["file_hash"], chunks)
            if not owned:
                continue
            add_file_to_catalog(
                manifest["file_hash"],
                manifest["name"],
                manifest["size"],
                chunks,
                PEER_ID,
                owned,
                allowed_peers=manifest.get("allowed_peers", []),
                password_protected=manifest.get("password_protected", False),
            )
            restored.append({"name": manifest["name"], "chunks": len(owned)})
        except Exception as exc:
            print(f"[{PEER_ID}] ignored saved manifest {path.name}: {exc}", flush=True)
    for item in restored:
        print(
            f"[{PEER_ID}] restored shareable downloaded file {item['name']} "
            f"({item['chunks']} verified chunks)",
            flush=True,
        )
    return restored


def _get_file_download_lock(file_hash):
    # Double-checked pattern: only create a new Lock when the file_hash is not yet registered.
    with _file_dl_locks_mu:
        if file_hash not in _file_dl_locks:
            _file_dl_locks[file_hash] = threading.Lock()
        return _file_dl_locks[file_hash]


def download_file(file_hash, file_password=""):
    ensure_dirs()
    cleanup_inactive_peers()
    with CATALOG_LOCK:
        file_info = CATALOG.get(file_hash)
        if not file_info:
            raise FileNotFoundError(f"file {file_hash} is not known by this peer yet")
        # Deep-copy so the download loop works on a stable snapshot independent of CATALOG_LOCK.
        file_info = json.loads(json.dumps(file_info))

    # Per-file mutex: serializes concurrent /download requests for the same file so that
    # chunk writes and the final assembled output file are never written simultaneously.
    with _get_file_download_lock(file_hash):
        downloaded = []
        errors = []
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {}
            for position, chunk in enumerate(file_info["chunks"]):
                local_chunk = chunk_path(file_hash, chunk["index"])
                if local_chunk.exists() and sha256_bytes(local_chunk.read_bytes()) == chunk["hash"]:
                    add_own_chunk(file_hash, chunk)
                    downloaded.append(chunk["index"])
                    continue
                candidates = peers_for_chunk(file_info, chunk["index"], position)
                if not candidates:
                    errors.append(f"no peer available for chunk {chunk['index']}")
                    continue
                futures[executor.submit(fetch_chunk_from_candidates, candidates, file_hash, chunk)] = chunk["index"]

            for future in as_completed(futures):
                try:
                    downloaded.append(future.result())
                except Exception as exc:
                    errors.append(str(exc))

        if errors:
            raise RuntimeError("; ".join(errors))

        safe_name = Path(file_info["name"]).name
        output = assemble_file(CHUNKS_DIR / file_hash, DOWNLOADS_DIR / safe_name, file_hash)

        if file_info.get("password_protected"):
            if not file_password:
                output.unlink(missing_ok=True)
                raise ValueError("this file is password protected — provide a password to download")
            file_key = derive_key(file_password)
            try:
                decrypted = decrypt(output.read_bytes(), file_key)
            except Exception:
                output.unlink(missing_ok=True)
                raise ValueError("wrong password")
            output.write_bytes(decrypted)

        return {"file_hash": file_hash, "saved_to": str(output), "chunks": sorted(downloaded)}


def discovery_message():
    return {
        "type": "peer_hello",
        "peer_id": PEER_ID,
        "host": PEER_ADVERTISE_HOST,
        "port": PEER_PORT,
        "digest": catalog_digest(),
        "timestamp": now(),
    }


def discovery_listener_loop():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind(("", DISCOVERY_PORT))
    except OSError as exc:
        print(f"[{PEER_ID}] discovery listener disabled on UDP {DISCOVERY_PORT}: {exc}", flush=True)
        return
    print(f"[{PEER_ID}] discovery listening on UDP {DISCOVERY_PORT}", flush=True)
    while True:
        try:
            raw, address = sock.recvfrom(65535)
            payload = json.loads(raw.decode("utf-8"))
            if payload.get("type") != "peer_hello" or payload.get("peer_id") == PEER_ID:
                continue
            host = payload.get("host") or address[0]
            if host in {"", "0.0.0.0"}:
                host = address[0]
            upsert_peer(payload.get("peer_id"), host, payload.get("port"), payload.get("digest"))
        except Exception as exc:
            print(f"[{PEER_ID}] discovery receive failed: {exc}", flush=True)


def broadcast_targets():
    targets = ["255.255.255.255"]
    # Also send a directed subnet broadcast so mobile hotspots (which often
    # block 255.255.255.255) still forward the packet to all connected devices.
    host = PEER_ADVERTISE_HOST.strip()
    if host and not host.startswith("127."):
        parts = host.split(".")
        if len(parts) == 4:
            subnet_bcast = f"{parts[0]}.{parts[1]}.{parts[2]}.255"
            if subnet_bcast not in targets:
                targets.append(subnet_bcast)
    return targets


def discovery_broadcast_loop():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    while True:
        try:
            raw = json.dumps(discovery_message()).encode("utf-8")
            for target in broadcast_targets():
                try:
                    sock.sendto(raw, (target, DISCOVERY_PORT))
                except Exception as exc:
                    print(f"[{PEER_ID}] broadcast to {target} failed: {exc}", flush=True)
        except Exception as exc:
            print(f"[{PEER_ID}] discovery broadcast failed: {exc}", flush=True)
        time.sleep(HELLO_INTERVAL_SECONDS)


def sync_manifest(peer):
    try:
        manifest = request_json("GET", peer_url(peer, "/manifest"), timeout=3)
        merge_manifest(manifest, peer.get("peer_id"))
        try:
            request_json("POST", peer_url(peer, "/manifest"), build_manifest(), timeout=3)
        except Exception as exc:
            print(f"[{PEER_ID}] manifest push failed to {peer.get('peer_id')}: {exc}", flush=True)
        actual_peer_id = (manifest.get("peer") or {}).get("peer_id")
        if actual_peer_id and actual_peer_id != peer.get("peer_id") and not peer.get("candidate"):
            with PEERS_LOCK:
                PEERS.pop(peer.get("peer_id"), None)
    except Exception as exc:
        if not peer.get("quiet"):
            print(f"[{PEER_ID}] manifest sync failed from {peer.get('peer_id')}: {exc}", flush=True)
        if not peer.get("candidate"):
            remove_peer(peer.get("peer_id"))


def manifest_sync_loop():
    while True:
        peers = sync_targets()
        random.shuffle(peers)
        for peer in peers:
            sync_manifest(peer)
        time.sleep(MANIFEST_INTERVAL_SECONDS)


class PeerHandler(BaseHTTPRequestHandler):
    server_version = "PeerNode/0.2"

    def log_message(self, fmt, *args):
        print(f"[{PEER_ID}] {self.address_string()} - {fmt % args}", flush=True)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            send_json(
                self,
                HTTPStatus.OK,
                {
                    "status": "ok",
                    "peer_id": PEER_ID,
                    "mode": "trackerless",
                    "known_peers": len(peers_snapshot()),
                    "known_files": len(catalog_files_snapshot()),
                },
            )
            return
        if parsed.path == "/peers":
            send_json(self, HTTPStatus.OK, {"peers": peers_snapshot()})
            return
        if parsed.path == "/files":
            send_json(self, HTTPStatus.OK, {"files": catalog_files_snapshot()})
            return
        if parsed.path == "/manifest":
            send_json(self, HTTPStatus.OK, build_manifest())
            return
        if parsed.path == "/local":
            files = {
                "shared": [str(path.relative_to(DATA_DIR)) for path in SHARED_DIR.glob("*") if path.is_file()],
                "downloads": [str(path.relative_to(DATA_DIR)) for path in DOWNLOADS_DIR.glob("*") if path.is_file()],
                "chunks": [str(path.relative_to(DATA_DIR)) for path in CHUNKS_DIR.glob("*/*.chunk")],
            }
            send_json(self, HTTPStatus.OK, files)
            return
        if parsed.path == "/chunk":
            query = parse_qs(parsed.query)
            file_hash = query.get("file_hash", [None])[0]
            index = query.get("index", [None])[0]
            requesting_peer_id = query.get("peer_id", [""])[0]
            with CATALOG_LOCK:
                _fi = CATALOG.get(file_hash)
                _allowed = list(_fi.get("allowed_peers", [])) if _fi else []
            if _allowed and requesting_peer_id not in _allowed:
                send_json(self, HTTPStatus.FORBIDDEN, {"error": "access denied"})
                return
            try:
                path = chunk_path(file_hash, int(index)) if file_hash and index is not None else None
            except (ValueError, TypeError):
                path = None
            if not path or not path.exists():
                send_json(self, HTTPStatus.NOT_FOUND, {"error": "chunk not found"})
                return
            raw = path.read_bytes()
            if ENCRYPTION_KEY:
                raw = encrypt(raw, ENCRYPTION_KEY)
            data = base64.b64encode(raw).decode("ascii")
            send_json(self, HTTPStatus.OK, {"file_hash": file_hash, "index": int(index), "data": data})
            return
        if parsed.path == "/messages":
            with MESSAGES_LOCK:
                msgs = list(MESSAGES)
            send_json(self, HTTPStatus.OK, {"messages": msgs})
            return
        not_found(self)

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/publish":
            try:
                payload = read_json(self)
                result = publish_file(payload["path"])
                send_json(self, HTTPStatus.OK, result)
            except Exception as exc:
                send_json(self, HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        if parsed.path == "/download":
            try:
                payload = read_json(self)
                result = download_file(payload["file_hash"], file_password=payload.get("file_password", ""))
                send_json(self, HTTPStatus.OK, result)
            except Exception as exc:
                send_json(self, HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        if parsed.path == "/manifest":
            try:
                manifest = prefer_observed_peer_host(read_json(self), self.client_address[0])
                merge_manifest(manifest, "manifest push")
                send_json(self, HTTPStatus.OK, {"ok": True})
            except Exception as exc:
                send_json(self, HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        if parsed.path == "/upload":
            try:
                query = parse_qs(parsed.query)
                raw_name = query.get("name", [""])[0].strip()
                safe_name = Path(raw_name).name
                if not safe_name:
                    send_json(self, HTTPStatus.BAD_REQUEST, {"error": "?name= query param required"})
                    return
                allowed_peers_raw = query.get("allowed_peers", [""])[0].strip()
                allowed_peers = [p.strip() for p in allowed_peers_raw.split(",") if p.strip()]
                file_password = query.get("file_password", [""])[0].strip()
                length = int(self.headers.get("Content-Length", "0"))
                if length == 0:
                    send_json(self, HTTPStatus.BAD_REQUEST, {"error": "empty upload"})
                    return
                data = self.rfile.read(length)
                if file_password:
                    file_key = derive_key(file_password)
                    data = encrypt(data, file_key)
                ensure_dirs()
                tmp_path = SHARED_DIR / (safe_name + ".upload.tmp")
                target_path = SHARED_DIR / safe_name
                tmp_path.write_bytes(data)
                tmp_path.replace(target_path)
                result = publish_file(target_path, allowed_peers=allowed_peers,
                                      password_protected=bool(file_password))
                send_json(self, HTTPStatus.OK, result)
            except Exception as exc:
                send_json(self, HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        if parsed.path == "/delete":
            try:
                payload = read_json(self)
                file_hash = payload.get("file_hash", "").strip()
                if not file_hash:
                    send_json(self, HTTPStatus.BAD_REQUEST, {"error": "file_hash required"})
                    return
                with CATALOG_LOCK:
                    if file_hash not in CATALOG:
                        send_json(self, HTTPStatus.NOT_FOUND, {"error": "file not known"})
                        return
                    file_name = CATALOG[file_hash].get("name", "")
                    CATALOG.pop(file_hash)
                    DELETED_HASHES.add(file_hash)
                chunk_dir = CHUNKS_DIR / file_hash
                if chunk_dir.exists():
                    shutil.rmtree(chunk_dir)
                manifest_path(file_hash).unlink(missing_ok=True)
                if file_name:
                    (SHARED_DIR / file_name).unlink(missing_ok=True)
                send_json(self, HTTPStatus.OK, {"ok": True, "file_hash": file_hash})
            except Exception as exc:
                send_json(self, HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        if parsed.path == "/message":
            try:
                payload = read_json(self)
                from_peer = str(payload.get("from_peer", "?"))
                encrypted_hex = str(payload.get("text", ""))
                raw = bytes.fromhex(encrypted_hex)
                text = decrypt(raw, ENCRYPTION_KEY).decode("utf-8") if ENCRYPTION_KEY else raw.decode("utf-8")
                with MESSAGES_LOCK:
                    MESSAGES.append({
                        "from_peer": from_peer,
                        "text": text,
                        "timestamp": now(),
                    })
                send_json(self, HTTPStatus.OK, {"ok": True})
            except Exception as exc:
                send_json(self, HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        if parsed.path == "/send_message":
            try:
                payload = read_json(self)
                to_peer_id = payload.get("to_peer_id", "").strip()
                text = payload.get("text", "").strip()
                if not to_peer_id or not text:
                    send_json(self, HTTPStatus.BAD_REQUEST, {"error": "to_peer_id and text required"})
                    return
                with PEERS_LOCK:
                    peer = PEERS.get(to_peer_id)
                if not peer:
                    send_json(self, HTTPStatus.NOT_FOUND, {"error": f"peer {to_peer_id!r} not known"})
                    return
                raw = text.encode("utf-8")
                encrypted_hex = encrypt(raw, ENCRYPTION_KEY).hex() if ENCRYPTION_KEY else raw.hex()
                request_json("POST", peer_url(peer, "/message"), {
                    "from_peer": PEER_ID,
                    "text": encrypted_hex,
                }, timeout=5)
                send_json(self, HTTPStatus.OK, {"ok": True})
            except Exception as exc:
                send_json(self, HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        not_found(self)


class QuietThreadingHTTPServer(ThreadingHTTPServer):
    def handle_error(self, request, client_address):
        exc = sys.exc_info()[1]
        if isinstance(exc, (ConnectionResetError, ConnectionAbortedError, BrokenPipeError)):
            print(f"[{PEER_ID}] client disconnected early: {client_address}", flush=True)
            return
        super().handle_error(request, client_address)


def main():
    ensure_dirs()
    restore_local_manifests()
    publish_shared_files()
    threading.Thread(target=discovery_listener_loop, daemon=True).start()
    threading.Thread(target=discovery_broadcast_loop, daemon=True).start()
    threading.Thread(target=manifest_sync_loop, daemon=True).start()
    server = QuietThreadingHTTPServer((PEER_HOST, PEER_PORT), PeerHandler)
    print(
        f"[{PEER_ID}] trackerless peer listening on {PEER_HOST}:{PEER_PORT}, "
        f"advertised as {PEER_ADVERTISE_HOST}:{PEER_PORT}",
        flush=True,
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
