import click
import pytest
from click.testing import CliRunner

from gnucash_cli.cli import _require_api_key_for_exposed_host, cli
from gnucash_cli.cli_safety import resolve_no_auto_backup
from gnucash_cli.exceptions import ValidationError


def test_exposed_server_requires_api_key(monkeypatch):
    monkeypatch.delenv("GNUCASH_API_KEY", raising=False)

    with pytest.raises(click.UsageError, match="Refusing to expose"):
        _require_api_key_for_exposed_host("0.0.0.0", {"api_key": None})


def test_loopback_server_allows_development_without_api_key(monkeypatch):
    monkeypatch.delenv("GNUCASH_API_KEY", raising=False)

    _require_api_key_for_exposed_host("127.0.0.1", {"api_key": None})


def test_exposed_server_accepts_env_api_key(monkeypatch):
    monkeypatch.setenv("GNUCASH_API_KEY", "secret")

    _require_api_key_for_exposed_host("0.0.0.0", {"api_key": None})


def test_exposed_mcp_http_accepts_specific_env_api_key(monkeypatch):
    monkeypatch.delenv("GNUCASH_API_KEY", raising=False)
    monkeypatch.setenv("GNUCASH_MCP_HTTP_API_KEY", "secret")

    _require_api_key_for_exposed_host("0.0.0.0", {"api_key": None})


def test_exposed_mcp_http_accepts_specific_config_api_key(monkeypatch):
    monkeypatch.delenv("GNUCASH_API_KEY", raising=False)
    monkeypatch.delenv("GNUCASH_MCP_HTTP_API_KEY", raising=False)

    _require_api_key_for_exposed_host("0.0.0.0", {"mcp_http_api_key": "secret"})


def test_no_auto_backup_requires_explicit_unsafe_config():
    with pytest.raises(click.UsageError, match="Refusing to skip"):
        resolve_no_auto_backup({"allow_unsafe_no_auto_backup": False}, requested=True)


def test_no_auto_backup_allowed_by_explicit_unsafe_config():
    assert resolve_no_auto_backup({"allow_unsafe_no_auto_backup": True}, requested=True) is True


def test_cli_domain_errors_are_reported_without_traceback(monkeypatch):
    def fail_with_domain_error(**kwargs):
        raise ValidationError("bad transaction")

    monkeypatch.setattr(
        "gnucash_cli.commands.transactions.service_add_transaction",
        fail_with_domain_error,
    )

    result = CliRunner().invoke(
        cli,
        [
            "-b",
            "dummy.gnucash",
            "tx",
            "add",
            "-d",
            "x",
            "--debit",
            "Assets:Cash 1",
            "--credit",
            "Expenses:Food 1",
        ],
    )

    assert result.exit_code == 1
    assert "bad transaction" in result.output


def test_cli_unexpected_errors_are_not_swallowed(monkeypatch):
    def fail_with_bug(**kwargs):
        raise RuntimeError("programming bug")

    monkeypatch.setattr(
        "gnucash_cli.commands.transactions.service_add_transaction",
        fail_with_bug,
    )

    result = CliRunner().invoke(
        cli,
        [
            "-b",
            "dummy.gnucash",
            "tx",
            "add",
            "-d",
            "x",
            "--debit",
            "Assets:Cash 1",
            "--credit",
            "Expenses:Food 1",
        ],
    )

    assert isinstance(result.exception, RuntimeError)
    assert "programming bug" in str(result.exception)
