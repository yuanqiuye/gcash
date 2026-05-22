import json
import logging
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from gnucash_cli.book_access import ensure_book_unlocked_for_write, safe_open_book
from gnucash_cli.exceptions import BookLockedError
from gnucash_cli.logging_config import logger, setup_logging
from gnucash_cli.presentation import (
    error,
    output_result,
    success,
)
from gnucash_cli.serialization import json_default as _json_default
from gnucash_cli.transaction_input import parse_split_spec as _parse_split_spec


def test_json_default():
    """Test JSON serializer for non-standard types."""
    assert _json_default(Decimal("10.5")) == "10.5"
    
    d = date(2026, 4, 1)
    assert _json_default(d) == "2026-04-01"
    
    dt = datetime(2026, 4, 1, 10, 30)
    assert _json_default(dt) == "2026-04-01T10:30:00"
    
    # Unknown type should fallback to string
    class Dummy:
        def __str__(self):
            return "dummy"
    assert _json_default(Dummy()) == "dummy"

def test_output_result_json(capsys):
    """Test output_result JSON formatting."""
    data = {"amount": Decimal("100.50"), "date": date(2026, 4, 1)}
    
    output_result(data, fmt="json")
    captured = capsys.readouterr()
    
    parsed = json.loads(captured.out)
    assert parsed["amount"] == "100.50"
    assert parsed["date"] == "2026-04-01"

def test_output_result_table():
    """Test output_result uses table_builder when format is not json."""
    data = [{"id": 1}]
    table_builder = MagicMock()
    
    output_result(data, fmt="table", table_builder=table_builder)
    
    table_builder.assert_called_once_with(data)


def test_setup_logging_is_idempotent():
    original_handlers = list(logger.handlers)
    original_level = logger.level
    logger.handlers = []

    try:
        setup_logging("INFO")
        setup_logging("DEBUG")
        gcash_handlers = [handler for handler in logger.handlers if getattr(handler, "_gcash_handler", False)]

        assert len(gcash_handlers) == 1
        assert logger.level == logging.DEBUG
    finally:
        logger.handlers = original_handlers
        logger.setLevel(original_level)


def test_success_and_error_use_valid_ascii_markup(monkeypatch):
    mock_console_print = MagicMock()
    mock_err_print = MagicMock()

    monkeypatch.setattr("gnucash_cli.presentation.console.print", mock_console_print)
    monkeypatch.setattr("gnucash_cli.presentation.err_console.print", mock_err_print)

    success("done")
    error("failed")

    mock_console_print.assert_called_once_with("[green]OK[/green] done")
    mock_err_print.assert_called_once_with("[red]ERROR[/red] failed")


@patch("gnucash_cli.book_access.piecash.open_book")
def test_safe_open_book_defaults_to_not_opening_locked_books(mock_open_book, tmp_path):
    mock_context = MagicMock()
    mock_context.__enter__.return_value = object()
    mock_context.__exit__.return_value = None
    mock_open_book.return_value = mock_context
    book_path = str(tmp_path / "book.gnucash")

    with safe_open_book(book_path, readonly=True):
        pass

    mock_open_book.assert_called_once_with(
        book_path,
        readonly=True,
        open_if_lock=False,
        do_backup=True,
    )


class _FakeSqlResult:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class _FakeSqlConnection:
    def __init__(self, rows=None, error=None):
        self._rows = rows or []
        self._error = error

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def execute(self, statement):
        assert "gnclock" in str(statement)
        if self._error:
            raise self._error
        return _FakeSqlResult(self._rows)


class _FakeSqlEngine:
    def __init__(self, rows=None, error=None):
        self._rows = rows or []
        self._error = error
        self.disposed = False

    def connect(self):
        return _FakeSqlConnection(rows=self._rows, error=self._error)

    def dispose(self):
        self.disposed = True


def test_postgres_gnclock_blocks_writes(monkeypatch):
    engine = _FakeSqlEngine(rows=[("client-host", 1234)])
    monkeypatch.setattr("sqlalchemy.create_engine", lambda _url: engine)

    with pytest.raises(BookLockedError, match="gnclock"):
        ensure_book_unlocked_for_write("postgresql://user:secret@example.com/gnucash")

    assert engine.disposed is True


def test_postgres_empty_gnclock_allows_writes(monkeypatch):
    engine = _FakeSqlEngine(rows=[])
    monkeypatch.setattr("sqlalchemy.create_engine", lambda _url: engine)

    ensure_book_unlocked_for_write("postgresql://user:secret@example.com/gnucash")

    assert engine.disposed is True


def test_missing_postgres_gnclock_table_does_not_block_writes(monkeypatch):
    engine = _FakeSqlEngine(error=RuntimeError('relation "gnclock" does not exist'))
    monkeypatch.setattr("sqlalchemy.create_engine", lambda _url: engine)

    ensure_book_unlocked_for_write("postgresql://user:secret@example.com/gnucash")

    assert engine.disposed is True

def test_parse_split_spec_simple():
    """Test _parse_split_spec simple format: 'Account 100'"""
    spec = "Assets:Cash 100.50"
    res = _parse_split_spec(spec)
    
    assert res["account_fullname"] == "Assets:Cash"
    assert res["value"] == Decimal("100.50")
    assert res["currency"] is None
    assert res["quantity"] is None
    
    # Test negative
    res = _parse_split_spec("Expenses:Food -50")
    assert res["account_fullname"] == "Expenses:Food"
    assert res["value"] == Decimal("-50")

def test_parse_split_spec_with_currency():
    """Test _parse_split_spec format: 'Account 100 USD'"""
    spec = "Assets:Cash 100.50 USD"
    res = _parse_split_spec(spec)
    
    assert res["account_fullname"] == "Assets:Cash"
    assert res["value"] == Decimal("100.50")
    assert res["currency"] == "USD"
    assert res["quantity"] is None

def test_parse_split_spec_multi_currency():
    """Test _parse_split_spec format: 'Account 100 USD 30'"""
    spec = "Assets:Cash 930 TWD 30.0"
    res = _parse_split_spec(spec)
    
    assert res["account_fullname"] == "Assets:Cash"
    assert res["value"] == Decimal("930")
    assert res["currency"] == "TWD"
    assert res["quantity"] == Decimal("30.0")

def test_parse_split_spec_with_spaces():
    """Test _parse_split_spec handles account names with spaces."""
    spec = "Assets:My Cash Account 100"
    res = _parse_split_spec(spec)
    
    assert res["account_fullname"] == "Assets:My Cash Account"
    assert res["value"] == Decimal("100")
    
def test_parse_split_spec_invalid():
    """Test _parse_split_spec raises error for invalid input."""
    with pytest.raises(ValueError):
        _parse_split_spec("InvalidSpec")
        
    with pytest.raises(ValueError):
        _parse_split_spec("Account string_amount")
