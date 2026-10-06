"""Password credentials for the seeded users, plus a login lockout.

Hashes live in STATE_DIR/credentials.json (mode 0600) as
`pbkdf2_sha256$<iterations>$<salt hex>$<hash hex>`. Nothing here is used in
demo-login mode (DEMO_LOGIN=1), where the persona picker signs in without a
password.

Set or change a password from a shell on the server:

    python -m app.credentials <user_id>
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import time
from pathlib import Path
from threading import Lock
from typing import Dict, Optional, Tuple

_ITERATIONS = 600_000
MIN_PASSWORD_LENGTH = 12

MAX_FAILURES = 5
LOCKOUT_SECONDS = 300

_lock = Lock()
# (user_id, client ip) -> (consecutive failures, locked until epoch seconds)
_failures: Dict[Tuple[str, str], Tuple[int, float]] = {}

# Hashed once at import so unknown-user logins cost the same as real ones.
_DUMMY_HASH = None


def _path() -> Path:
    from . import persistence
    return persistence.STATE_DIR / "credentials.json"


def _load() -> Dict[str, str]:
    p = _path()
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def hash_password(password: str, *, salt: Optional[bytes] = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _ITERATIONS)
    return f"pbkdf2_sha256${_ITERATIONS}${salt.hex()}${digest.hex()}"


def _matches(password: str, stored: str) -> bool:
    try:
        algo, iterations, salt_hex, hash_hex = stored.split("$")
    except ValueError:
        return False
    if algo != "pbkdf2_sha256":
        return False
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), int(iterations))
    return hmac.compare_digest(digest.hex(), hash_hex)


def verify_password(user_id: Optional[str], password: str) -> bool:
    """True only for a known user with a stored hash that matches. Unknown
    users and users without a password still pay for one hash."""

    global _DUMMY_HASH
    stored = _load().get(user_id) if user_id else None
    if stored is None:
        if _DUMMY_HASH is None:
            _DUMMY_HASH = hash_password("dummy-password-for-timing")
        _matches(password, _DUMMY_HASH)
        return False
    return _matches(password, stored)


def set_password(user_id: str, password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters")
    with _lock:
        creds = _load()
        creds[user_id] = hash_password(password)
        p = _path()
        tmp = p.with_name(f".{p.name}.tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(creds, f, indent=0)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, p)


# --- Lockout -----------------------------------------------------------------


def locked_out(user_key: str, ip: str) -> bool:
    with _lock:
        count, until = _failures.get((user_key, ip), (0, 0.0))
        return count >= MAX_FAILURES and time.time() < until


def record_failure(user_key: str, ip: str) -> None:
    with _lock:
        now = time.time()
        if len(_failures) > 10_000:
            # Keys are attacker-chosen strings; drop expired windows so the
            # table can't grow without bound.
            for key in [k for k, (_, until) in _failures.items() if until <= now]:
                del _failures[key]
        count, until = _failures.get((user_key, ip), (0, 0.0))
        if count >= MAX_FAILURES and time.time() >= until:
            count = 0  # previous lockout expired — start a fresh window
        count += 1
        _failures[(user_key, ip)] = (count, time.time() + LOCKOUT_SECONDS)


def record_success(user_key: str, ip: str) -> None:
    with _lock:
        _failures.pop((user_key, ip), None)


def reset_lockouts() -> None:
    """Test helper."""
    with _lock:
        _failures.clear()


if __name__ == "__main__":
    import getpass
    import sys

    from .tenants import get_user

    if len(sys.argv) != 2:
        sys.exit("usage: python -m app.credentials <user_id>")
    uid = sys.argv[1]
    if get_user(uid) is None:
        sys.exit(f"Unknown user {uid!r}")
    first = getpass.getpass(f"New password for {uid}: ")
    if first != getpass.getpass("Repeat: "):
        sys.exit("Passwords did not match")
    try:
        set_password(uid, first)
    except ValueError as e:
        sys.exit(str(e))
    print(f"Password set for {uid} in {_path()}")
