"""Currency management commands."""

import logging
from datetime import date
from decimal import Decimal

import click
import piecash

from gnucash_cli.config import resolve_book_path
from gnucash_cli.utils import console, error, output_result, success, safe_open_book, logger
from gnucash_cli.commands.db import auto_backup_if_needed


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
        with safe_open_book(book_path, readonly=True, open_if_lock=True) as book:
            currencies = [
                c for c in book.commodities
                if c.namespace == "CURRENCY"
            ]
            data = [
                {
                    "mnemonic": c.mnemonic,
                    "fullname": c.fullname or c.mnemonic,
                    "fraction": c.fraction,
                }
                for c in currencies
            ]

            if fmt == "json":
                output_result({"currencies": data}, fmt="json")
            else:
                from rich.table import Table
                table = Table(title="Currencies")
                table.add_column("Code", style="cyan", width=6)
                table.add_column("Name", style="white")
                table.add_column("Fraction", style="dim")
                for d in data:
                    table.add_row(d["mnemonic"], d["fullname"], str(d["fraction"]))
                console.print(table)

    except Exception as e:
        error(f"Failed to list currencies: {e}")
        raise SystemExit(1)


@currencies_group.command("add")
@click.option("--code", required=True, help="ISO 4217 currency code (e.g. USD, EUR, JPY).")
@click.option("--format", "fmt", type=click.Choice(["table", "json"]), default="table",
              help="Output format.")
@click.option("--no-auto-backup", is_flag=True, help="Disable automatic database backup before this action.")
@click.pass_context
def add_currency(ctx, code, fmt, no_auto_backup):
    """Add a new ISO currency to the book."""
    config = ctx.obj["config"]
    book_path = resolve_book_path(ctx.obj.get("book"), config)
    code = code.upper()

    auto_backup_if_needed(book_path, no_auto_backup, action_name="pre_currency_add")

    try:
        with safe_open_book(book_path, readonly=False, open_if_lock=True, do_backup=False) as book:
            # Check if already exists
            existing = [c for c in book.commodities if c.namespace == "CURRENCY" and c.mnemonic == code]
            if existing:
                error(f"Currency '{code}' already exists in the book.")
                raise SystemExit(1)

            commodity = piecash.factories.create_currency_from_ISO(code)
            book.add(commodity)
            book.save()

            result = {
                "status": "success",
                "currency": {
                    "mnemonic": code,
                    "fullname": commodity.fullname or code,
                    "fraction": commodity.fraction,
                },
            }

            if fmt == "json":
                output_result(result, fmt="json")
            else:
                success(f"Added currency: {code} ({commodity.fullname})")

    except SystemExit:
        raise
    except Exception as e:
        error(f"Failed to add currency: {e}")
        raise SystemExit(1)


@currencies_group.command("update-prices")
@click.option("--base", default=None,
              help="Base currency for rate fetching. Defaults to config default_currency.")
@click.option("--format", "fmt", type=click.Choice(["table", "json"]), default="table",
              help="Output format.")
@click.option("--no-auto-backup", is_flag=True, help="Disable automatic database backup before this action.")
@click.pass_context
def update_prices(ctx, base, fmt, no_auto_backup):
    """Fetch latest exchange rates and save to the book.

    Uses Open Exchange Rates API (free, no API key, supports 150+ currencies
    including TWD, JPY, etc.). Rates are stored as Price objects in the book.
    """
    import requests

    config = ctx.obj["config"]
    book_path = resolve_book_path(ctx.obj.get("book"), config)
    base_currency = base or config.get("default_currency", "TWD")

    auto_backup_if_needed(book_path, no_auto_backup, action_name="pre_update_prices")

    try:
        with safe_open_book(book_path, readonly=False, open_if_lock=True, do_backup=False) as book:
            # Get all currencies in the book except the base
            currencies = [
                c for c in book.commodities
                if c.namespace == "CURRENCY" and c.mnemonic != base_currency
            ]

            if not currencies:
                console.print("[dim]No other currencies found in the book.[/dim]")
                return

            target_codes = [c.mnemonic for c in currencies]

            # Fetch rates from open.er-api.com (free, no key, supports 150+ currencies)
            try:
                logger.info("Fetching exchange rates from open.er-api.com (base=%s)", base_currency)
                resp = requests.get(
                    f"https://open.er-api.com/v6/latest/{base_currency}",
                    timeout=15,
                )
                resp.raise_for_status()
                rate_data = resp.json()
            except requests.RequestException as e:
                logger.error("Failed to fetch exchange rates: %s", e)
                error(f"Failed to fetch exchange rates: {e}")
                raise SystemExit(1)

            if rate_data.get("result") != "success":
                error(f"API error: {rate_data.get('error-type', 'unknown error')}")
                raise SystemExit(1)

            all_rates = rate_data.get("rates", {})

            # Get base commodity
            try:
                base_commodity = book.commodities.get(mnemonic=base_currency)
            except Exception:
                error(f"Base currency '{base_currency}' not found in book.")
                raise SystemExit(1)

            from piecash.core.commodity import Price as PiecashPrice

            results = []
            today = date.today()

            for target_code in target_codes:
                target_commodity = None
                for c in currencies:
                    if c.mnemonic == target_code:
                        target_commodity = c
                        break
                if not target_commodity:
                    continue

                rate = all_rates.get(target_code)
                if rate is None or rate == 0:
                    console.print(f"[yellow]⚠ No rate available for {target_code}, skipping.[/yellow]")
                    continue

                # API returns: 1 BASE = rate TARGET
                # GnuCash Price stores: 1 TARGET = X BASE
                # So: price_value = 1 / rate
                price_value = (Decimal("1") / Decimal(str(rate))).quantize(Decimal("0.000001"))

                PiecashPrice(
                    commodity=target_commodity,
                    currency=base_commodity,
                    date=today,
                    value=price_value,
                    source="user:price-gcash",
                    type="last",
                )

                results.append({
                    "currency": target_code,
                    "rate": float(price_value),
                    "meaning": f"1 {target_code} = {price_value} {base_currency}",
                })

            book.save()
            logger.info("Updated %d exchange rates (base=%s)", len(results), base_currency)

            if fmt == "json":
                output_result({
                    "status": "success",
                    "base": base_currency,
                    "date": today.isoformat(),
                    "prices": results,
                }, fmt="json")
            else:
                success(f"Updated {len(results)} exchange rates (base: {base_currency}, date: {today})")
                from rich.table import Table
                table = Table()
                table.add_column("Currency", style="cyan")
                table.add_column(f"Rate (per 1 unit in {base_currency})", style="white")
                table.add_column("Meaning", style="dim")
                for r in results:
                    table.add_row(r["currency"], f"{r['rate']:.6f}", r["meaning"])
                console.print(table)

    except SystemExit:
        raise
    except Exception as e:
        error(f"Failed to update prices: {e}")
        raise SystemExit(1)

