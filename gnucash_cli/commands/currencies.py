"""Currency management commands."""

import click

from gnucash_cli.cli_safety import resolve_no_auto_backup
from gnucash_cli.config import resolve_book_path
from gnucash_cli.exceptions import GCashError
from gnucash_cli.presentation import console, error, output_result, success
from gnucash_cli.services.currencies import (
    add_currency as service_add_currency,
)
from gnucash_cli.services.currencies import (
    list_currencies as service_list_currencies,
)
from gnucash_cli.services.currencies import (
    update_prices as service_update_prices,
)


@click.group("currencies")
def currencies_group():
    """Manage currencies (list, add, update exchange rates)."""
    pass


@currencies_group.command("list")
@click.option("--format", "fmt", type=click.Choice(["table", "json"]), default="table",
              help="Output format.")
@click.pass_context
def list_currencies(ctx, fmt):
    """List all currencies in the book."""
    config = ctx.obj["config"]
    book_path = resolve_book_path(ctx.obj.get("book"), config)

    try:
        result = service_list_currencies(book_path)
        if fmt == "json":
            output_result(result, fmt="json")
        else:
            from rich.table import Table
            table = Table(title="Currencies")
            table.add_column("Code", style="cyan", width=6)
            table.add_column("Name", style="white")
            table.add_column("Fraction", style="dim")
            for currency in result["currencies"]:
                table.add_row(currency["mnemonic"], currency["fullname"], str(currency["fraction"]))
            console.print(table)
    except GCashError as e:
        error(f"Failed to list currencies: {e}")
        raise SystemExit(1)


@currencies_group.command("add")
@click.option("--code", required=True, help="ISO 4217 currency code (e.g. USD, EUR, JPY).")
@click.option("--format", "fmt", type=click.Choice(["table", "json"]), default="table",
              help="Output format.")
@click.option("--unsafe-no-auto-backup", "unsafe_no_auto_backup", is_flag=True,
              help="Disable automatic safety backup. Requires allow_unsafe_no_auto_backup: true.")
@click.option("--no-auto-backup", "legacy_no_auto_backup", is_flag=True, hidden=True)
@click.pass_context
def add_currency(ctx, code, fmt, unsafe_no_auto_backup, legacy_no_auto_backup):
    """Add a new ISO currency to the book."""
    config = ctx.obj["config"]
    book_path = resolve_book_path(ctx.obj.get("book"), config)
    no_auto_backup = resolve_no_auto_backup(config, unsafe_no_auto_backup or legacy_no_auto_backup)

    try:
        result = service_add_currency(
            book_path=book_path,
            code=code,
            config=config,
            no_auto_backup=no_auto_backup,
        )
        if fmt == "json":
            output_result(result, fmt="json")
        else:
            currency = result["currency"]
            success(f"Added currency: {currency['mnemonic']} ({currency['fullname']})")
    except GCashError as e:
        error(f"Failed to add currency: {e}")
        raise SystemExit(1)


@currencies_group.command("update-prices")
@click.option("--base", default=None,
              help="Base currency for rate fetching. Defaults to config default_currency.")
@click.option("--format", "fmt", type=click.Choice(["table", "json"]), default="table",
              help="Output format.")
@click.option("--unsafe-no-auto-backup", "unsafe_no_auto_backup", is_flag=True,
              help="Disable automatic safety backup. Requires allow_unsafe_no_auto_backup: true.")
@click.option("--no-auto-backup", "legacy_no_auto_backup", is_flag=True, hidden=True)
@click.pass_context
def update_prices(ctx, base, fmt, unsafe_no_auto_backup, legacy_no_auto_backup):
    """Fetch latest exchange rates and save them to the book."""
    config = ctx.obj["config"]
    book_path = resolve_book_path(ctx.obj.get("book"), config)
    no_auto_backup = resolve_no_auto_backup(config, unsafe_no_auto_backup or legacy_no_auto_backup)
    base_currency = base or config.get("default_currency", "TWD")

    try:
        result = service_update_prices(
            book_path=book_path,
            base_currency=base_currency,
            config=config,
            no_auto_backup=no_auto_backup,
        )

        if fmt == "json":
            output_result(result, fmt="json")
            return

        if not result["prices"]:
            console.print("[dim]No other currencies found in the book.[/dim]")
            return

        success(f"Updated {len(result['prices'])} exchange rates (base: {result['base']}, date: {result['date']})")
        from rich.table import Table
        table = Table()
        table.add_column("Currency", style="cyan")
        table.add_column(f"Rate (per 1 unit in {result['base']})", style="white")
        table.add_column("Meaning", style="dim")
        for price in result["prices"]:
            table.add_row(price["currency"], price["rate"], price["meaning"])
        console.print(table)
    except GCashError as e:
        error(f"Failed to update prices: {e}")
        raise SystemExit(1)
