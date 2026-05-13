import hashlib
from pathlib import Path


CHUNK_SIZE = 512 * 1024


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(CHUNK_SIZE), b""):
            digest.update(block)
    return digest.hexdigest()


def chunk_file(source_path, chunk_dir):
    source = Path(source_path)
    chunk_dir = Path(chunk_dir)
    chunk_dir.mkdir(parents=True, exist_ok=True)

    chunks = []
    with source.open("rb") as handle:
        index = 0
        for data in iter(lambda: handle.read(CHUNK_SIZE), b""):
            chunk_hash = sha256_bytes(data)
            chunk_path = chunk_dir / f"{index}.chunk"
            chunk_path.write_bytes(data)
            chunks.append(
                {
                    "index": index,
                    "hash": chunk_hash,
                    "size": len(data),
                    "path": str(chunk_path),
                }
            )
            index += 1
    return chunks


def assemble_file(chunks_dir, output_path, expected_hash):
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    chunk_paths = sorted(Path(chunks_dir).glob("*.chunk"), key=lambda item: int(item.stem))

    with output.open("wb") as target:
        for chunk_path in chunk_paths:
            target.write(chunk_path.read_bytes())

    actual_hash = sha256_file(output)
    if actual_hash != expected_hash:
        output.unlink(missing_ok=True)
        raise ValueError(f"assembled file hash mismatch: expected {expected_hash}, got {actual_hash}")
    return output
