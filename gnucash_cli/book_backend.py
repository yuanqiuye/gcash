"""Book backend detection and database URL helpers."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from urllib.parse import parse_qs, unquote, urlparse

BookBackend = Literal["sqlite", "postgresql", "unknown"]


@dataclass(frozen=True)
class BookRef:
    """Normalized reference to a GnuCash book."""

    raw: str
    backend: BookBackend

    @property
    def is_sqlite(self) -> bool:
        return self.backend == "sqlite"

    @property
    def is_postgres(self) -> bool:
        return self.backend == "postgresql"


def parse_book_ref(book_path: str) -> BookRef:
    return BookRef(raw=book_path, backend=detect_book_backend(book_path))


def detect_book_backend(book_path: str | None) -> BookBackend | None:
    if not book_path:
        return None

    if Path(book_path).drive:
        return "sqlite"

    parsed = urlparse(book_path)
    if parsed.scheme in {"postgresql", "postgres"}:
        return "postgresql"
    if parsed.scheme:
        return "unknown"
    return "sqlite"


def is_postgres_book(book_path: str) -> bool:
    return detect_book_backend(book_path) == "postgresql"


def is_sqlite_book(book_path: str) -> bool:
    return detect_book_backend(book_path) == "sqlite"


def normalized_book_identity(book_path: str) -> str:
    """Return a stable lock identity without changing database URLs."""
    if "://" in book_path:
        return book_path
    return str(Path(book_path).expanduser().resolve())


def postgres_env(book_path: str) -> dict[str, str]:
    """Build libpq environment variables from a PostgreSQL book URL."""
    parsed = urlparse(book_path)
    env = os.environ.copy()

    if parsed.hostname:
        env["PGHOST"] = parsed.hostname
    if parsed.port:
        env["PGPORT"] = str(parsed.port)
    if parsed.path and parsed.path != "/":
        env["PGDATABASE"] = unquote(parsed.path.lstrip("/"))
    if parsed.username:
        env["PGUSER"] = unquote(parsed.username)
    if parsed.password:
        env["PGPASSWORD"] = unquote(parsed.password)

    query = parse_qs(parsed.query)
    sslmode = query.get("sslmode", [None])[0]
    if sslmode:
        env["PGSSLMODE"] = sslmode

    return env
