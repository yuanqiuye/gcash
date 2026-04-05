"""Utility functions for gcash CLI."""

import json
import logging
import os
import piecash
from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from rich.console import Console
from rich.table import Table
from rich.tree import Tree

console = Console()
err_console = Console(stderr=True)

# Structured logger for audit trail and debugging
logger = logging.getLogger("gcash")


def setup_logging(level: str = "WARNING") -> None:
    """Configure the gcash logger with a standard format.

    Call this early in the application lifecycle (e.g. in cli.py main()).
    """
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    logger.addHandler(handler)
    logger.setLevel(getattr(logging, level.upper(), logging.WARNING))


def output_result(data: Any, fmt: str = "table", table_builder=None):
    """Output data in the requested format.

    Args:
        data: The data to output (dict or list).
        fmt: "json" or "table".
        table_builder: A callable that takes data and returns a Rich Table/Tree.
    """
    if fmt == "json":
        print(json.dumps(data, ensure_ascii=False, indent=2, default=_json_default))
    elif table_builder:
        table_builder(data)
    else:
        print(json.dumps(data, ensure_ascii=False, indent=2, default=_json_default))


def _json_default(obj):
    """JSON serializer for non-standard types."""
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    return str(obj)


def success(message: str):
    """Print a success message."""
    console.print(f"[green]✓[/green] {message}")


def error(message: str):
    """Print an error message."""
    err_console.print(f"[red]✗[/red] {message}")


@contextmanager
def safe_open_book(book_path: str, readonly: bool = False, open_if_lock: bool = True, do_backup: bool = True):
    """Safely open a piecash book, checking for GnuCash GUI LCK files.
    
    This is highly recommended to prevent database corruption when automated
    agents and the local GnuCash GUI try to write simultaneously.
    """
    lck_file = f"{book_path}.LCK"
    lnk_file = f"{book_path}.LNK"
    
    # We enforce lock checking even for readonly, because reading while 
    # GnuCash is actively writing might yield unexpected states for the Agent.
    if os.path.exists(lck_file) or os.path.exists(lnk_file):
        logger.warning("Database lock detected: %s or %s exists", lck_file, lnk_file)
        error("Cannot open database: GnuCash GUI is currently holding a lock (.LCK/.LNK file exists).")
        error("Please close GnuCash before running this agent command to prevent database corruption.")
        raise SystemExit(1)

    mode = "readonly" if readonly else "readwrite"
    logger.debug("Opening book [%s]: %s (mode=%s)", book_path, "with backup" if do_backup else "no backup", mode)
        
    with piecash.open_book(book_path, readonly=readonly, open_if_lock=open_if_lock, do_backup=do_backup) as book:
        yield book


def build_account_tree_data(book) -> list[dict]:
    """Build account data list from a piecash book."""
    accounts = []
    for acc in book.accounts:
        children_names = [c.fullname for c in acc.children] if acc.children else []
        try:
            balance = float(acc.get_balance())
        except Exception:
            balance = 0.0

        accounts.append({
            "fullname": acc.fullname,
            "name": acc.name,
            "type": acc.type,
            "currency": acc.commodity.mnemonic if acc.commodity else None,
            "placeholder": bool(acc.placeholder),
            "balance": balance,
            "description": acc.description or "",
            "children": children_names,
        })
    return accounts


def print_account_tree(book, type_filter: str = None):
    """Print accounts as a Rich tree."""
    root = book.root_account
    tree = Tree(f"[bold]{root.name or 'Root'}[/bold]")
    _add_children_to_tree(tree, root, type_filter)
    console.print(tree)


def _add_children_to_tree(tree_node, account, type_filter: str = None):
    """Recursively add children to tree."""
    for child in sorted(account.children, key=lambda a: a.name):
        if type_filter and child.type != type_filter:
            # Still check children in case they match
            _add_children_to_tree(tree_node, child, type_filter)
            continue

        currency = child.commodity.mnemonic if child.commodity else "?"
        try:
            balance = child.get_balance()
            balance_str = f" [dim]({balance:,.2f} {currency})[/dim]"
        except Exception:
            balance_str = ""

        type_color = _type_color(child.type)
        label = (
            f"{child.name} "
            f"[{type_color}][{child.type}][/{type_color}] "
            f"[cyan]{currency}[/cyan]"
            f"{balance_str}"
        )
        if child.placeholder:
            label = f"[bold]{child.name}[/bold] [{type_color}][{child.type}][/{type_color}] [cyan]{currency}[/cyan]{balance_str}"

        branch = tree_node.add(label)
        _add_children_to_tree(branch, child, type_filter)


def _type_color(account_type: str) -> str:
    """Get color for account type."""
    colors = {
        "ASSET": "green",
        "BANK": "green",
        "CASH": "green",
        "CREDIT": "red",
        "LIABILITY": "red",
        "INCOME": "blue",
        "EXPENSE": "yellow",
        "EQUITY": "magenta",
    }
    return colors.get(account_type, "white")


def print_transactions_table(transactions_data: list[dict]):
    """Print transactions as a Rich table."""
    table = Table(title="Transactions", show_lines=True)
    table.add_column("Date", style="cyan", width=12)
    table.add_column("Description", style="white", min_width=20)
    table.add_column("Splits", style="dim")

    for tx in transactions_data:
        splits_str = "\n".join(
            f"  {s['account']}: {s['quantity']:+,.2f} {s['currency']}"
            for s in tx["splits"]
        )
        table.add_row(tx["date"], tx["description"], splits_str)

    console.print(table)
