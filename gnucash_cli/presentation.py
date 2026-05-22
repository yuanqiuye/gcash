"""Human-facing CLI presentation helpers."""

import json
from decimal import Decimal
from typing import Any

from rich.console import Console
from rich.table import Table
from rich.tree import Tree

from gnucash_cli.serialization import json_default

console = Console()
err_console = Console(stderr=True)


def output_result(data: Any, fmt: str = "table", table_builder=None):
    """Output data in the requested format."""
    if fmt == "json":
        print(json.dumps(data, ensure_ascii=False, indent=2, default=json_default))
    elif table_builder:
        table_builder(data)
    else:
        print(json.dumps(data, ensure_ascii=False, indent=2, default=json_default))


def success(message: str):
    """Print a success message."""
    console.print(f"[green]OK[/green] {message}")


def error(message: str):
    """Print an error message."""
    err_console.print(f"[red]ERROR[/red] {message}")


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
            f"  {s['account']}: {Decimal(str(s['quantity'])):+,.2f} {s['currency']}"
            for s in tx["splits"]
        )
        table.add_row(tx["date"], tx["description"], splits_str)

    console.print(table)
