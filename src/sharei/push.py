"""Web Push: RFC 8291 message encryption and RFC 8292 VAPID, on the optional
cryptography package (the `push` extra)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import http.client
import ipaddress
import json
import os
import socket
import struct
import time
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

if TYPE_CHECKING:
    from cryptography.hazmat.primitives.asymmetric.ec import EllipticCurvePrivateKey

RECORD_SIZE = 4096
ENDPOINT_MAX = 2048


def available() -> bool:
    try:
        import cryptography.hazmat.primitives.asymmetric.ec  # noqa: F401
    except ImportError:
        return False
    return True


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def b64url_decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _expand(prk: bytes, info: bytes, length: int) -> bytes:
    """HKDF-Expand for at most one SHA-256 block, all RFC 8291 needs."""
    return hmac.new(prk, info + b"\x01", hashlib.sha256).digest()[:length]


def public_bytes(key: EllipticCurvePrivateKey) -> bytes:
    from cryptography.hazmat.primitives import serialization

    return key.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )


def load_key(path: Path) -> EllipticCurvePrivateKey:
    """The VAPID key pair, created (mode 0600) on first use."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    try:
        key = serialization.load_pem_private_key(path.read_bytes(), password=None)
    except FileNotFoundError:
        key = ec.generate_private_key(ec.SECP256R1())
        pem = key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            return load_key(path)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(pem)
    if not isinstance(key, ec.EllipticCurvePrivateKey) or not isinstance(
        key.curve, ec.SECP256R1
    ):
        raise TypeError(f"{path} is not a P-256 key")
    return key


def valid_keys(p256dh: str, auth: str) -> bool:
    from cryptography.hazmat.primitives.asymmetric import ec

    try:
        point, secret = b64url_decode(p256dh), b64url_decode(auth)
        ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), point)
    except ValueError:
        return False
    return len(point) == 65 and len(secret) == 16


def encrypt(
    payload: bytes,
    ua_public: bytes,
    auth_secret: bytes,
    salt: bytes | None = None,
    server_key: EllipticCurvePrivateKey | None = None,
) -> bytes:
    """One aes128gcm record for a push subscription (RFC 8291 section 3)."""
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    if len(payload) + 17 > RECORD_SIZE:
        raise ValueError("push payload is too large")
    server_key = server_key or ec.generate_private_key(ec.SECP256R1())
    as_public = public_bytes(server_key)
    ua_key = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), ua_public)
    ecdh_secret = server_key.exchange(ec.ECDH(), ua_key)
    prk_key = hmac.new(auth_secret, ecdh_secret, hashlib.sha256).digest()
    ikm = _expand(prk_key, b"WebPush: info\x00" + ua_public + as_public, 32)
    salt = salt or os.urandom(16)
    prk = hmac.new(salt, ikm, hashlib.sha256).digest()
    cek = _expand(prk, b"Content-Encoding: aes128gcm\x00", 16)
    nonce = _expand(prk, b"Content-Encoding: nonce\x00", 12)
    ciphertext = AESGCM(cek).encrypt(nonce, payload + b"\x02", None)
    header = salt + struct.pack("!IB", RECORD_SIZE, len(as_public)) + as_public
    return header + ciphertext


def vapid_authorization(
    key: EllipticCurvePrivateKey, endpoint: str, subject: str, now: float | None = None
) -> str:
    """The Authorization header proving this server sent the message (RFC 8292)."""
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

    parts = urlsplit(endpoint)
    claims = {
        "aud": f"{parts.scheme}://{parts.netloc}",
        "exp": int(now if now is not None else time.time()) + 12 * 3600,
        "sub": subject,
    }
    token = ".".join(
        b64url(json.dumps(part, separators=(",", ":")).encode())
        for part in ({"typ": "JWT", "alg": "ES256"}, claims)
    )
    r, s = decode_dss_signature(key.sign(token.encode(), ec.ECDSA(hashes.SHA256())))
    signature = r.to_bytes(32, "big") + s.to_bytes(32, "big")
    return f"vapid t={token}.{b64url(signature)}, k={b64url(public_bytes(key))}"


def host_is_public(host: str) -> bool:
    """Push services live on the internet; anything else is refused so a
    subscription cannot point sharei at the local network."""
    try:
        infos = socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
    except OSError:
        return False
    addresses = {info[4][0] for info in infos}
    return bool(addresses) and all(
        ipaddress.ip_address(address.split("%", 1)[0]).is_global
        for address in addresses
    )


def endpoint_allowed(endpoint: str) -> bool:
    if not isinstance(endpoint, str) or len(endpoint) > ENDPOINT_MAX:
        return False
    try:
        parts = urlsplit(endpoint)
        port = parts.port
    except ValueError:
        return False
    if parts.scheme != "https" or not parts.hostname or parts.username is not None:
        return False
    if port not in (None, 443):
        return False
    try:
        ipaddress.ip_address(parts.hostname)
    except ValueError:
        return host_is_public(parts.hostname)
    return False


def send(
    subscription: dict,
    payload: bytes,
    key: EllipticCurvePrivateKey,
    subject: str,
    topic: str = "",
    ttl: int = 24 * 3600,
    timeout: float = 10,
) -> int:
    """POST one encrypted message to the subscription's push service; returns the
    HTTP status. Redirects are not followed."""
    endpoint = subscription["endpoint"]
    if not endpoint_allowed(endpoint):
        return 410
    keys = subscription["keys"]
    body = encrypt(payload, b64url_decode(keys["p256dh"]), b64url_decode(keys["auth"]))
    parts = urlsplit(endpoint)
    target = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
    headers = {
        "TTL": str(ttl),
        "Urgency": "normal",
        "Content-Encoding": "aes128gcm",
        "Content-Type": "application/octet-stream",
        "Authorization": vapid_authorization(key, endpoint, subject),
    }
    if topic:
        headers["Topic"] = topic
    connection = http.client.HTTPSConnection(parts.hostname, 443, timeout=timeout)
    try:
        connection.request("POST", target, body=body, headers=headers)
        response = connection.getresponse()
        response.read(8192)
        return response.status
    finally:
        connection.close()
