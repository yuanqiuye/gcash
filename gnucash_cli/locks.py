"""Cross-process mutation locking for GnuCash books."""

import hashlib
import json
import os
import socket
import time
from contextlib import contextmanager
from pathlib import Path

from gnucash_cli.book_backend import normalized_book_identity
from gnucash_cli.config import DEFAULT_CONFIG_DIR, load_config
from gnucash_cli.exceptions import MutationLockError


def _lock_root(config: dict | None = None) -> Path:
    effective_config = config if config is not None else load_config()
    configured_dir = os.environ.get("GNUCASH_LOCK_DIR") or effective_config.get("lock_dir")
    root = Path(configured_dir).expanduser() if configured_dir else DEFAULT_CONFIG_DIR / "locks"
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


def _book_lock_name(book_path: str) -> str:
    identity = normalized_book_identity(book_path)
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
    return f"{digest}.lock"


def book_mutation_lock_path(book_path: str, config: dict | None = None) -> Path:
    """Return the lock directory path for a book without exposing the book path."""
    return _lock_root(config=config) / _book_lock_name(book_path)


def _metadata_path(lock_path: Path) -> Path:
    return lock_path / "owner.json"


def _write_metadata(lock_path: Path) -> None:
    metadata = {
        "pid": os.getpid(),
        "host": socket.gethostname(),
        "created_at": time.time(),
    }
    _metadata_path(lock_path).write_text(json.dumps(metadata, indent=2), encoding="utf-8")


def _remove_lock_dir(lock_path: Path) -> None:
    metadata = _metadata_path(lock_path)
    if metadata.exists():
        metadata.unlink()
    lock_path.rmdir()


def _try_remove_stale_lock(lock_path: Path, stale_after_seconds: float) -> bool:
    try:
        age = time.time() - lock_path.stat().st_mtime
    except FileNotFoundError:
        return True

    if age < stale_after_seconds:
        return False

    try:
        _remove_lock_dir(lock_path)
        return True
    except OSError:
        return False


@contextmanager
def book_mutation_lock(
    book_path: str,
    timeout_seconds: float = 30.0,
    poll_seconds: float = 0.1,
    stale_after_seconds: float = 6 * 60 * 60,
    config: dict | None = None,
):
    """Serialize mutations for a single book across gcash processes.

    The lock is an atomically-created directory under a stable runtime lock
    root, so separate gcash processes can serialize mutations even when they
    were started from different working directories.
    """
    lock_path = book_mutation_lock_path(book_path, config=config)
    deadline = time.monotonic() + timeout_seconds
    acquired = False

    while not acquired:
        try:
            lock_path.mkdir()
            _write_metadata(lock_path)
            acquired = True
        except FileExistsError:
            _try_remove_stale_lock(lock_path, stale_after_seconds)
            if time.monotonic() >= deadline:
                raise MutationLockError(
                    "Another gcash process is already modifying this book. "
                    "Try again after the current operation finishes."
                )
            time.sleep(poll_seconds)

    try:
        yield
    finally:
        if acquired:
            try:
                _remove_lock_dir(lock_path)
            except OSError:
                pass
