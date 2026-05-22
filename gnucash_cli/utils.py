"""Backward-compatible utility re-exports.

New code should import from the focused modules directly:
`book_access`, `book_data`, `logging_config`, `presentation`, and
`serialization`.
"""

from gnucash_cli.book_access import (
    ensure_book_unlocked,
    ensure_book_unlocked_for_write,
    safe_open_book,
)
from gnucash_cli.book_data import build_account_tree_data
from gnucash_cli.logging_config import logger, setup_logging
from gnucash_cli.presentation import (
    console,
    err_console,
    error,
    output_result,
    print_account_tree,
    print_transactions_table,
    success,
)
from gnucash_cli.serialization import json_default as _json_default

__all__ = [
    "_json_default",
    "build_account_tree_data",
    "console",
    "ensure_book_unlocked",
    "ensure_book_unlocked_for_write",
    "err_console",
    "error",
    "logger",
    "output_result",
    "print_account_tree",
    "print_transactions_table",
    "safe_open_book",
    "setup_logging",
    "success",
]
