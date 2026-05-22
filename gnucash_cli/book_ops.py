"""Reusable book operation wrappers."""

from contextlib import contextmanager

from gnucash_cli.backup import auto_backup_if_needed
from gnucash_cli.book_access import safe_open_book
from gnucash_cli.locks import book_mutation_lock


@contextmanager
def writable_book(
    book_path: str,
    config: dict,
    *,
    action_name: str,
    no_auto_backup: bool = False,
):
    """Open a book for mutation with the required lock and safety backup."""
    with book_mutation_lock(book_path, config=config):
        auto_backup_if_needed(book_path, no_auto_backup, action_name=action_name, config=config)
        with safe_open_book(book_path, readonly=False, do_backup=False) as book:
            yield book


@contextmanager
def readonly_book(book_path: str):
    """Open a book for read-only access."""
    with safe_open_book(book_path, readonly=True) as book:
        yield book
