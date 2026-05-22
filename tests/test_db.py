from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

from gnucash_cli.backup import auto_backup_if_needed, execute_backup, execute_restore, get_backups_list
from gnucash_cli.exceptions import BookLockedError


def test_sqlite_backup_names_are_unique_within_same_second(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    book = tmp_path / "book.gnucash"
    book.write_text("book-data", encoding="utf-8")

    first = execute_backup(str(book), action_name="test")
    second = execute_backup(str(book), action_name="test")

    assert first
    assert second
    assert first != second
    assert Path(first).exists()
    assert Path(second).exists()


def test_sqlite_backup_defaults_to_book_adjacent_dir(tmp_path, monkeypatch):
    monkeypatch.delenv("GNUCASH_BACKUP_DIR", raising=False)
    book = tmp_path / "book.gnucash"
    book.write_text("book-data", encoding="utf-8")

    backup = execute_backup(str(book), action_name="test", config={"backup_dir": None})

    assert Path(backup).parent == tmp_path / ".backups"
    assert get_backups_list(book_path=str(book), config={"backup_dir": None})


def test_configured_backup_dir_is_stable_across_working_dirs(tmp_path, monkeypatch):
    monkeypatch.delenv("GNUCASH_BACKUP_DIR", raising=False)
    backup_dir = tmp_path / "runtime-backups"
    book = tmp_path / "book.gnucash"
    first_cwd = tmp_path / "one"
    second_cwd = tmp_path / "two"
    book.write_text("book-data", encoding="utf-8")
    first_cwd.mkdir()
    second_cwd.mkdir()

    monkeypatch.chdir(first_cwd)
    first = execute_backup(str(book), action_name="test", config={"backup_dir": str(backup_dir)})
    monkeypatch.chdir(second_cwd)
    second = execute_backup(str(book), action_name="test", config={"backup_dir": str(backup_dir)})

    assert Path(first).parent == backup_dir
    assert Path(second).parent == backup_dir


def test_manual_backup_acquires_mutation_lock(tmp_path, monkeypatch):
    book = tmp_path / "book.gnucash"
    book.write_text("book-data", encoding="utf-8")
    config = {"backup_dir": str(tmp_path / "backups"), "lock_dir": str(tmp_path / "locks")}
    calls = []

    @contextmanager
    def fake_lock(book_path, **kwargs):
        calls.append((book_path, kwargs.get("config")))
        yield

    monkeypatch.setattr("gnucash_cli.backup.book_mutation_lock", fake_lock)

    execute_backup(str(book), action_name="manual", config=config)

    assert calls == [(str(book), config)]


def test_auto_backup_uses_existing_mutation_lock(tmp_path, monkeypatch):
    book = tmp_path / "book.gnucash"
    book.write_text("book-data", encoding="utf-8")
    backup_dir = tmp_path / "backups"

    def fail_if_reentered(*_args, **_kwargs):
        raise AssertionError("auto_backup_if_needed should not acquire the mutation lock again")

    monkeypatch.setattr("gnucash_cli.backup.book_mutation_lock", fail_if_reentered)

    auto_backup_if_needed(
        str(book),
        no_auto_backup=False,
        action_name="pre_tx",
        config={"backup_dir": str(backup_dir), "lock_dir": str(tmp_path / "locks")},
    )

    backups = list(backup_dir.glob("sqlite_backup_pre_tx_*.gnucash"))
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == "book-data"


def test_auto_backup_checks_write_lock_even_when_backup_is_skipped(monkeypatch):
    calls = []

    def fake_write_lock_check(book_path):
        calls.append(book_path)

    monkeypatch.setattr("gnucash_cli.backup.ensure_book_unlocked_for_write", fake_write_lock_check)

    auto_backup_if_needed(
        "postgresql://user:secret@example.com/gnucash",
        no_auto_backup=True,
        action_name="pre_tx",
        config={},
    )

    assert calls == ["postgresql://user:secret@example.com/gnucash"]


def test_sqlite_restore_refuses_locked_book(tmp_path):
    book = tmp_path / "book.gnucash"
    backup = tmp_path / "backup.gnucash"
    lock = tmp_path / "book.gnucash.LCK"
    book.write_text("current", encoding="utf-8")
    backup.write_text("backup", encoding="utf-8")
    lock.write_text("locked", encoding="utf-8")

    with pytest.raises(BookLockedError):
        execute_restore(str(book), str(backup))
    assert book.read_text(encoding="utf-8") == "current"


def test_postgres_backup_does_not_put_credentials_in_argv(tmp_path, monkeypatch):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        return SimpleNamespace(returncode=0, stderr="")

    monkeypatch.setattr("gnucash_cli.backup.subprocess.run", fake_run)

    execute_backup(
        "postgresql://alice:s3cr%21t@example.com:5433/gnucash?sslmode=require",
        action_name="test",
        config={"backup_dir": str(tmp_path / "backups")},
    )

    cmd, kwargs = calls[0]
    argv = " ".join(cmd)
    assert cmd[0] == "pg_dump"
    assert "postgresql://" not in argv
    assert "alice" not in argv
    assert "s3cr" not in argv
    assert kwargs["env"]["PGHOST"] == "example.com"
    assert kwargs["env"]["PGPORT"] == "5433"
    assert kwargs["env"]["PGDATABASE"] == "gnucash"
    assert kwargs["env"]["PGUSER"] == "alice"
    assert kwargs["env"]["PGPASSWORD"] == "s3cr!t"
    assert kwargs["env"]["PGSSLMODE"] == "require"


def test_postgres_restore_does_not_put_credentials_in_argv(tmp_path, monkeypatch):
    backup = tmp_path / "backup.sql"
    backup.write_text("-- backup", encoding="utf-8")
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        return SimpleNamespace(returncode=0, stderr="")

    monkeypatch.setattr("gnucash_cli.backup.subprocess.run", fake_run)
    monkeypatch.setattr("gnucash_cli.backup.ensure_book_unlocked_for_write", lambda _book_path: None)

    execute_restore(
        "postgresql://alice:secret@example.com/gnucash",
        str(backup),
        config={"lock_dir": str(tmp_path / "locks")},
    )

    cmd, kwargs = calls[0]
    argv = " ".join(cmd)
    assert cmd == ["psql", "-f", str(backup)]
    assert "postgresql://" not in argv
    assert "alice" not in argv
    assert "secret" not in argv
    assert kwargs["env"]["PGPASSWORD"] == "secret"
