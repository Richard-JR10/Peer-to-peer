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
from ipaddress import ip_address
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from chunking import CHUNK_SIZE, assemble_file, chunk_file, sha256_bytes, sha256_file
from http_utils import not_found, read_json, request_json, send_json


PEER_ID = os.getenv("PEER_ID", "peer")
PEER_HOST = os.getenv("PEER_HOST", "0.0.0.0")
PEER_ADVERTISE_HOST = os.getenv("PEER_ADVERTISE_HOST", PEER_HOST)
PEER_PORT = int(os.getenv("PEER_PORT", "9000"))
DISCOVERY_PORT = int(os.getenv("DISCOVERY_PORT", "9999"))
BOOTSTRAP_PEERS = [item.strip() for item in os.getenv("BOOTSTRAP_PEERS", "").split(",") if item.strip()]
AUTO_BOOTSTRAP_PORTS = os.getenv("AUTO_BOOTSTRAP_PORTS", "9000-9010")
PEER_TTL_SECONDS = int(os.getenv("PEER_TTL_SECONDS", "45"))
HELLO_INTERVAL_SECONDS = int(os.getenv("HELLO_INTERVAL_SECONDS", "5"))
MANIFEST_INTERVAL_SECONDS = int(os.getenv("MANIFEST_INTERVAL_SECONDS", "8"))
DATA_DIR = Path(os.getenv("DATA_DIR", "/data"))
SHARED_DIR = DATA_DIR / "shared"
CHUNKS_DIR = DATA_DIR / "chunks"
DOWNLOADS_DIR = DATA_DIR / "downloads"
GUI_MODE = os.getenv("PEER_GUI_MODE") == "gui"
GUI_DOCKER_PEER_PORTS = {
    "peer1": 9001,
    "peer2": 9002,
    "peer3": 9003,
}

LOCK = threading.RLock()
PEERS = {}
CATALOG = {}


def now():
    return int(time.time())


def ensure_dirs():
    SHARED_DIR.mkdir(parents=True, exist_ok=True)
    CHUNKS_DIR.mkdir(parents=True, exist_ok=True)
    DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)


def chunk_path(file_hash, index):
    return CHUNKS_DIR / file_hash / f"{index}.chunk"


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


def upsert_peer(peer_id, host, port, digest=None, last_seen=None):
    if not peer_id or peer_id == PEER_ID:
        return
    with LOCK:
        PEERS[peer_id] = {
            "peer_id": peer_id,
            "host": host,
            "port": int(port),
            "last_seen": int(last_seen or now()),
            "digest": digest or PEERS.get(peer_id, {}).get("digest", ""),
        }


def remove_peer(peer_id):
    with LOCK:
        PEERS.pop(peer_id, None)
        for file_info in CATALOG.values():
            file_info.get("peers", {}).pop(peer_id, None)


def cleanup_inactive_peers():
    cutoff = now() - PEER_TTL_SECONDS
    with LOCK:
        inactive = [peer_id for peer_id, peer in PEERS.items() if peer.get("last_seen", 0) < cutoff]
    for peer_id in inactive:
        remove_peer(peer_id)


def add_file_to_catalog(file_hash, name, size, chunks, owner_peer_id, owned_chunks):
    normalized_chunks = normalize_chunks(chunks)
    owned = normalize_owned_chunks(owned_chunks)
    with LOCK:
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
    return file_hash


def add_own_chunk(file_hash, chunk):
    with LOCK:
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
    with LOCK:
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
            files.append(
                {
                    "file_hash": file_info["file_hash"],
                    "name": file_info["name"],
                    "size": int(file_info["size"]),
                    "chunk_size": int(file_info.get("chunk_size", CHUNK_SIZE)),
                    "chunks": normalize_chunks(file_info["chunks"]),
                    "peers": peers,
                }
            )
    return sorted(files, key=lambda item: (item["name"], item["file_hash"]))


def peers_snapshot():
    cleanup_inactive_peers()
    with LOCK:
        peers = list(PEERS.values())
    return sorted(peers, key=lambda item: item["peer_id"])


def catalog_digest():
    with LOCK:
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
    if peer:
        upsert_peer(peer.get("peer_id"), peer.get("host"), peer.get("port"), peer.get("digest"))

    for known_peer in manifest.get("peers", []):
        upsert_peer(
            known_peer.get("peer_id"),
            known_peer.get("host"),
            known_peer.get("port"),
            known_peer.get("digest"),
            known_peer.get("last_seen"),
        )

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


def load_bootstrap_peers():
    for value in BOOTSTRAP_PEERS:
        try:
            peer_id, host, port = parse_bootstrap_peer(value)
            upsert_peer(peer_id, host, port, last_seen=now())
        except Exception as exc:
            print(f"[{PEER_ID}] ignored bootstrap peer {value}: {exc}", flush=True)
    if should_probe_local_bootstrap():
        try:
            for port in parse_port_range(AUTO_BOOTSTRAP_PORTS):
                if port != PEER_PORT:
                    upsert_peer(f"local-{port}", "127.0.0.1", port, last_seen=now())
        except Exception as exc:
            print(f"[{PEER_ID}] ignored AUTO_BOOTSTRAP_PORTS={AUTO_BOOTSTRAP_PORTS}: {exc}", flush=True)


def peer_url(peer, path):
    url_peer = gui_bridge_peer(peer)
    return f"http://{url_peer['host']}:{url_peer['port']}{path}"


def peer_chunk_url(peer, file_hash, chunk):
    return peer_url(peer, f"/chunk?file_hash={file_hash}&index={chunk['index']}")


def fetch_chunk(peer, file_hash, chunk):
    url = peer_chunk_url(peer, file_hash, chunk)
    payload = request_json("GET", url, timeout=10)
    data = base64.b64decode(payload["data"].encode("ascii"))
    actual_hash = sha256_bytes(data)
    if actual_hash != chunk["hash"]:
        raise ValueError(f"chunk {chunk['index']} failed hash check")
    target = chunk_path(file_hash, chunk["index"])
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    add_own_chunk(file_hash, chunk)
    return chunk["index"]


def gui_bridge_peer(peer):
    if not GUI_MODE:
        return peer
    host = str(peer.get("host", "")).strip().lower()
    if int(peer.get("port", 0)) == 9000 and host in GUI_DOCKER_PEER_PORTS:
        bridged = dict(peer)
        bridged["host"] = "127.0.0.1"
        bridged["port"] = GUI_DOCKER_PEER_PORTS[host]
        return bridged
    return peer


def is_gui_reachable_host(host):
    if not GUI_MODE:
        return True
    if not host:
        return False
    normalized = host.strip().lower()
    if normalized in GUI_DOCKER_PEER_PORTS:
        return True
    if normalized in {"localhost"}:
        return True
    try:
        ip_address(normalized)
        return True
    except ValueError:
        pass
    return "." in normalized


def peer_lookup():
    with LOCK:
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


def publish_file(path):
    ensure_dirs()
    source = Path(path)
    if not source.exists():
        raise FileNotFoundError(f"{source} does not exist")

    file_hash = sha256_file(source)
    file_chunk_dir = CHUNKS_DIR / file_hash
    if file_chunk_dir.exists():
        shutil.rmtree(file_chunk_dir)
    chunks = chunk_file(source, file_chunk_dir)
    add_file_to_catalog(
        file_hash,
        source.name,
        source.stat().st_size,
        chunks,
        PEER_ID,
        [chunk["index"] for chunk in chunks],
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


def download_file(file_hash):
    ensure_dirs()
    cleanup_inactive_peers()
    with LOCK:
        file_info = CATALOG.get(file_hash)
        if not file_info:
            raise FileNotFoundError(f"file {file_hash} is not known by this peer yet")
        file_info = json.loads(json.dumps(file_info))

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

    output = assemble_file(CHUNKS_DIR / file_hash, DOWNLOADS_DIR / file_info["name"], file_hash)
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


def discovery_broadcast_loop():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    while True:
        try:
            raw = json.dumps(discovery_message()).encode("utf-8")
            sock.sendto(raw, ("255.255.255.255", DISCOVERY_PORT))
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
        if actual_peer_id and actual_peer_id != peer.get("peer_id"):
            with LOCK:
                PEERS.pop(peer.get("peer_id"), None)
    except Exception as exc:
        print(f"[{PEER_ID}] manifest sync failed from {peer.get('peer_id')}: {exc}", flush=True)
        remove_peer(peer.get("peer_id"))


def manifest_sync_loop():
    while True:
        load_bootstrap_peers()
        cleanup_inactive_peers()
        peers = peers_snapshot()
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
            path = chunk_path(file_hash, int(index)) if file_hash and index is not None else None
            if not path or not path.exists():
                send_json(self, HTTPStatus.NOT_FOUND, {"error": "chunk not found"})
                return
            data = base64.b64encode(path.read_bytes()).decode("ascii")
            send_json(self, HTTPStatus.OK, {"file_hash": file_hash, "index": int(index), "data": data})
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
                result = download_file(payload["file_hash"])
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
    publish_shared_files()
    load_bootstrap_peers()
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
