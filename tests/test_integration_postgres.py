"""Optional integration tests for a disposable PostgreSQL database.

Run with:
    GNUCASH_TEST_POSTGRES_DSN=postgresql://... \
    GNUCASH_TEST_POSTGRES_MUTATE=1 \
    uv run pytest -m integration tests/test_integration_postgres.py
"""

import os

import pytest
from sqlalchemy import create_engine, text

from gnucash_cli.book_access import ensure_book_unlocked_for_write
from gnucash_cli.exceptions import BookLockedError

pytestmark = pytest.mark.integration


def _postgres_test_dsn() -> str:
    dsn = os.environ.get("GNUCASH_TEST_POSTGRES_DSN")
    if not dsn:
        pytest.skip("Set GNUCASH_TEST_POSTGRES_DSN to run PostgreSQL integration tests.")
    if os.environ.get("GNUCASH_TEST_POSTGRES_MUTATE") != "1":
        pytest.skip("Set GNUCASH_TEST_POSTGRES_MUTATE=1 for a disposable database.")
    return dsn


def test_postgres_gnclock_check_against_real_database():
    dsn = _postgres_test_dsn()
    engine = create_engine(dsn)

    try:
        with engine.begin() as conn:
            conn.execute(text("DROP TABLE IF EXISTS gnclock"))
            conn.execute(text("CREATE TABLE gnclock (Hostname TEXT, PID INTEGER)"))

        ensure_book_unlocked_for_write(dsn)

        with engine.begin() as conn:
            conn.execute(text("INSERT INTO gnclock (Hostname, PID) VALUES ('gui-client', 1234)"))

        with pytest.raises(BookLockedError, match="gnclock"):
            ensure_book_unlocked_for_write(dsn)
    finally:
        with engine.begin() as conn:
            conn.execute(text("DROP TABLE IF EXISTS gnclock"))
        engine.dispose()
