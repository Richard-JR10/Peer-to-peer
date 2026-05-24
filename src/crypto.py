import hashlib
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_SALT = b'pdc-p2p-v1'


def derive_key(passphrase: str) -> bytes:
    return hashlib.pbkdf2_hmac('sha256', passphrase.encode('utf-8'), _SALT, 100_000, dklen=32)


def encrypt(data: bytes, key: bytes) -> bytes:
    nonce = os.urandom(12)
    return nonce + AESGCM(key).encrypt(nonce, data, None)


def decrypt(data: bytes, key: bytes) -> bytes:
    nonce, ct = data[:12], data[12:]
    return AESGCM(key).decrypt(nonce, ct, None)
