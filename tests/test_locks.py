import os
import time

import pytest

from gnucash_cli.exceptions import MutationLockError
from gnucash_cli.locks import book_mutation_lock, book_mutation_lock_path


def test_book_mutation_lock_serializes_same_book(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    book_path = str(tmp_path / "book.gnucash")

    with book_mutation_lock(book_path, timeout_seconds=0.01, poll_seconds=0.001):
        with pytest.raises(MutationLockError):
            with book_mutation_lock(book_path, timeout_seconds=0.01, poll_seconds=0.001):
                pass

    assert not book_mutation_lock_path(book_path).exists()


def test_book_mutation_lock_removes_stale_lock(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    book_path = str(tmp_path / "book.gnucash")
    lock_path = book_mutation_lock_path(book_path)
    lock_path.mkdir()
    (lock_path / "owner.json").write_text("{}", encoding="utf-8")
    old = time.time() - 3600
    os.utime(lock_path, (old, old))

    with book_mutation_lock(
        book_path,
        timeout_seconds=0.01,
        poll_seconds=0.001,
        stale_after_seconds=1,
    ):
        assert lock_path.exists()

    assert not lock_path.exists()


def test_book_mutation_lock_name_does_not_expose_connection_string(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    book_path = "postgresql://user:secret@example.com/gnucash"

    lock_path = book_mutation_lock_path(book_path)

    assert "secret" not in str(lock_path)
    assert "user" not in str(lock_path)
    assert "example.com" not in str(lock_path)


def test_book_mutation_lock_path_is_stable_across_working_dirs(tmp_path, monkeypatch):
    monkeypatch.setenv("GNUCASH_LOCK_DIR", str(tmp_path / "runtime-locks"))
    book_path = str(tmp_path / "book.gnucash")
    first_cwd = tmp_path / "one"
    second_cwd = tmp_path / "two"
    first_cwd.mkdir()
    second_cwd.mkdir()

    monkeypatch.chdir(first_cwd)
    first = book_mutation_lock_path(book_path)
    monkeypatch.chdir(second_cwd)
    second = book_mutation_lock_path(book_path)

    assert first == second
    assert first.parent == tmp_path / "runtime-locks"
