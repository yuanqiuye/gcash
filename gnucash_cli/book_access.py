"""Safe GnuCash book access and GUI lock detection."""

import os
from contextlib import contextmanager

import piecash

from gnucash_cli.book_backend import is_postgres_book
from gnucash_cli.exceptions import BookLockedError
from gnucash_cli.logging_config import logger


@contextmanager
def safe_open_book(book_path: str, readonly: bool = False, open_if_lock: bool = False, do_backup: bool = True):
    """Safely open a piecash book after checking GnuCash GUI locks."""
    ensure_book_unlocked(book_path)

    mode = "readonly" if readonly else "readwrite"
    logger.debug("Opening book [%s]: %s (mode=%s)", book_path, "with backup" if do_backup else "no backup", mode)

    open_kwargs = {
        "readonly": readonly,
        "open_if_lock": open_if_lock,
        "do_backup": do_backup,
    }
    if is_postgres_book(book_path):
        open_kwargs["uri_conn"] = book_path
    else:
        open_kwargs["sqlite_file"] = book_path

    with piecash.open_book(**open_kwargs) as book:
        yield book


def ensure_book_unlocked(book_path: str) -> None:
    """Raise if local GnuCash lock files indicate the book is in use."""
    if "://" in book_path:
        return

    lck_file = f"{book_path}.LCK"
    lnk_file = f"{book_path}.LNK"

    if os.path.exists(lck_file) or os.path.exists(lnk_file):
        logger.warning("Database lock detected: %s or %s exists", lck_file, lnk_file)
        raise BookLockedError(
            "Cannot open database: GnuCash GUI is currently holding a lock "
            "(.LCK/.LNK file exists). Please close GnuCash before running this "
            "agent command to prevent database corruption."
        )


def ensure_book_unlocked_for_write(book_path: str) -> None:
    """Raise if GnuCash appears to have the book open for SQL or file writes."""
    if is_postgres_book(book_path):
        _ensure_postgres_gnclock_empty(book_path)
        return

    ensure_book_unlocked(book_path)


def _ensure_postgres_gnclock_empty(book_path: str) -> None:
    """Refuse writes when GnuCash SQL backend lock table has an active row."""
    from sqlalchemy import create_engine, text

    engine = create_engine(book_path)
    try:
        with engine.connect() as conn:
            rows = conn.execute(text("SELECT * FROM gnclock")).fetchall()
    except Exception as e:
        if _is_missing_gnclock_table_error(e):
            return
        raise BookLockedError(
            "Cannot verify PostgreSQL GnuCash lock state before writing. "
            "Refusing to write until the database lock check succeeds."
        ) from e
    finally:
        engine.dispose()

    if rows:
        holders = ", ".join(
            f"{_row_value(row, 0, 'Hostname', 'hostname') or 'unknown'}:"
            f"{_row_value(row, 1, 'PID', 'pid') or '?'}"
            for row in rows
        )
        raise BookLockedError(
            "Cannot write: GnuCash SQL lock table 'gnclock' is not empty "
            f"({holders}). Close GnuCash GUI before automated writes."
        )


def _row_value(row, index: int, *names: str):
    for name in names:
        try:
            return getattr(row, name)
        except AttributeError:
            pass
        try:
            return row._mapping[name]
        except (AttributeError, KeyError):
            pass
    try:
        return row[index]
    except IndexError:
        return None


def _is_missing_gnclock_table_error(exc: Exception) -> bool:
    orig = getattr(exc, "orig", None)
    sqlstate = getattr(orig, "pgcode", None) or getattr(orig, "sqlstate", None)
    if sqlstate == "42P01":
        return True

    message = str(exc).lower()
    return "gnclock" in message and (
        "does not exist" in message
        or "undefined table" in message
        or "no such table" in message
    )
