from contextlib import contextmanager
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

from gnucash_cli.auth import is_headers_authorized
from gnucash_cli.book_backend import detect_book_backend, postgres_env
from gnucash_cli.book_ops import readonly_book, writable_book
from gnucash_cli.services.currencies import update_prices


def test_book_backend_detection_handles_windows_paths_and_urls():
    assert detect_book_backend(r"C:\books\personal.gnucash") == "sqlite"
    assert detect_book_backend("/books/personal.gnucash") == "sqlite"
    assert detect_book_backend("postgresql://user:secret@example.com/gnucash") == "postgresql"
    assert detect_book_backend("mysql://example.com/gnucash") == "unknown"
    assert detect_book_backend(None) is None


def test_postgres_env_keeps_credentials_out_of_argv():
    env = postgres_env("postgresql://alice:s3cr%21t@example.com:5433/gnucash?sslmode=require")

    assert env["PGHOST"] == "example.com"
    assert env["PGPORT"] == "5433"
    assert env["PGDATABASE"] == "gnucash"
    assert env["PGUSER"] == "alice"
    assert env["PGPASSWORD"] == "s3cr!t"
    assert env["PGSSLMODE"] == "require"


def test_writable_book_orders_lock_backup_and_open(monkeypatch):
    events = []
    sentinel_book = object()

    @contextmanager
    def fake_lock(book_path, **kwargs):
        events.append(("lock_enter", book_path, kwargs["config"]))
        yield
        events.append(("lock_exit", book_path))

    def fake_backup(book_path, no_auto_backup, action_name, config):
        events.append(("backup", book_path, no_auto_backup, action_name, config))

    @contextmanager
    def fake_open(book_path, **kwargs):
        events.append(("open_enter", book_path, kwargs))
        yield sentinel_book
        events.append(("open_exit", book_path))

    monkeypatch.setattr("gnucash_cli.book_ops.book_mutation_lock", fake_lock)
    monkeypatch.setattr("gnucash_cli.book_ops.auto_backup_if_needed", fake_backup)
    monkeypatch.setattr("gnucash_cli.book_ops.safe_open_book", fake_open)

    config = {"backup_dir": "backups"}
    with writable_book("book.gnucash", config, action_name="pre_tx", no_auto_backup=True) as book:
        assert book is sentinel_book
        events.append(("body",))

    assert events == [
        ("lock_enter", "book.gnucash", config),
        ("backup", "book.gnucash", True, "pre_tx", config),
        ("open_enter", "book.gnucash", {"readonly": False, "do_backup": False}),
        ("body",),
        ("open_exit", "book.gnucash"),
        ("lock_exit", "book.gnucash"),
    ]


def test_readonly_book_opens_without_write_safety(monkeypatch):
    events = []
    sentinel_book = object()

    @contextmanager
    def fake_open(book_path, **kwargs):
        events.append((book_path, kwargs))
        yield sentinel_book

    monkeypatch.setattr("gnucash_cli.book_ops.safe_open_book", fake_open)

    with readonly_book("book.gnucash") as book:
        assert book is sentinel_book

    assert events == [("book.gnucash", {"readonly": True})]


def test_auth_accepts_api_key_or_bearer_header():
    assert is_headers_authorized({"X-API-Key": "secret"}, "secret") is True
    assert is_headers_authorized({"Authorization": "Bearer secret"}, "secret") is True
    assert is_headers_authorized({"X-API-Key": "wrong"}, "secret") is False


def test_update_prices_is_service_layer_operation(monkeypatch):
    class CommodityCollection(list):
        def get(self, mnemonic):
            for commodity in self:
                if commodity.mnemonic == mnemonic:
                    return commodity
            raise LookupError(mnemonic)

    base = SimpleNamespace(namespace="CURRENCY", mnemonic="TWD", fullname="Taiwan Dollar", fraction=100)
    usd = SimpleNamespace(namespace="CURRENCY", mnemonic="USD", fullname="US Dollar", fraction=100)
    book = MagicMock()
    book.commodities = CommodityCollection([base, usd])
    created_prices = []

    @contextmanager
    def fake_writable_book(*_args, **_kwargs):
        yield book

    def fake_price(**kwargs):
        created_prices.append(kwargs)

    monkeypatch.setattr("gnucash_cli.services.currencies.writable_book", fake_writable_book)
    monkeypatch.setattr("gnucash_cli.services.currencies.PiecashPrice", fake_price)

    result = update_prices(
        "book.gnucash",
        base_currency="twd",
        config={},
        rate_fetcher=lambda base_currency: {"result": "success", "rates": {"USD": 2}},
    )

    assert result["status"] == "success"
    assert result["base"] == "TWD"
    assert result["prices"][0]["rate"] == "0.500000"
    assert created_prices[0]["commodity"] is usd
    assert created_prices[0]["currency"] is base
    assert created_prices[0]["value"] == Decimal("0.500000")
    book.save.assert_called_once()
