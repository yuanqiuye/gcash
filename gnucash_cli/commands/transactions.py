"""Transaction management commands."""

from datetime import datetime

import click

from gnucash_cli.config import resolve_book_path
from gnucash_cli.utils import (
    console,
    error,
    output_result,
    print_transactions_table,
    success,
    safe_open_book,
)
from gnucash_cli.service import add_transaction as service_add_transaction
from gnucash_cli.service import parse_split_spec as _parse_split_spec
from gnucash_cli.service import build_split as _build_split


@click.group("tx")
def transactions_group():
    """Manage transactions (add, list)."""
    pass


@transactions_group.command("add")
@click.option("-d", "--description", help="Transaction description.")
@click.option("--debit", "debits", multiple=True,
              help='Debit split: "Account:Name amount [CURRENCY [quantity]]". Can be specified multiple times.')
@click.option("--credit", "credits_", multiple=True,
              help='Credit split: "Account:Name amount [CURRENCY [quantity]]". Can be specified multiple times.')
@click.option("--date", "tx_date", default=None,
              help="Transaction date (YYYY-MM-DD). Defaults to today.")
@click.option("--currency", "tx_currency", default=None,
              help="Transaction currency (ISO code). Defaults to config default_currency.")
@click.option("--notes", default="", help="Transaction notes/memo.")
@click.option("-f", "--file", "file_path", type=click.Path(exists=True, dir_okay=False),
              help="Load tx parameters from JSON file to bypass shell encoding limitations (Agent Friendly).")
@click.option("--format", "fmt", type=click.Choice(["table", "json"]), default="table",
              help="Output format.")
@click.option("--no-auto-backup", is_flag=True, help="Disable automatic database backup before this transaction.")
@click.pass_context
def add_transaction(ctx, description, debits, credits_, tx_date, tx_currency, notes, file_path, fmt, no_auto_backup):
    """Add a new transaction.

    Multi-currency example:
      gcash tx add -d "USD expense" \\
        --debit "Expenses:Food 930" \\
        --credit "Assets:USD Account 930 USD 30"

    This means: debit 930 TWD to Expenses:Food, credit from USD Account where
    the value is 930 TWD but the actual quantity is 30 USD.
    """
    import json
    if file_path:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            description = data.get("description", description)
            debits = data.get("debits", debits) or []
            credits_ = data.get("credits", credits_) or []
            tx_date = data.get("date", tx_date)
            tx_currency = data.get("currency", tx_currency)
            notes = data.get("notes", notes)

    if not description or not debits or not credits_:
        error("Missing required parameters: --description, --debit, and --credit OR --file.")
        raise SystemExit(1)

    config = ctx.obj["config"]
    book_path = resolve_book_path(ctx.obj.get("book"), config)

    try:
        result = service_add_transaction(
            book_path=book_path,
            description=description,
            debits=debits,
            credits_=credits_,
            tx_date=tx_date,
            tx_currency=tx_currency,
            notes=notes,
            config=config,
            no_auto_backup=no_auto_backup
        )

        if fmt == "json":
            output_result(result, fmt="json")
        else:
            tx = result["transaction"]
            success(f"Transaction recorded: {tx['description']} ({tx['date']})")
            for s in tx["splits"]:
                console.print(f"  {s['account']}: {s['quantity']:+,.2f} {s['currency']}")

    except Exception as e:
        error(f"Failed to add transaction: {e}")
        raise SystemExit(1)

@transactions_group.command("list")
@click.option("--account", "account_name", default=None,
              help="Filter by account fullname.")
@click.option("--from", "from_date", default=None,
              help="Start date (YYYY-MM-DD).")
@click.option("--to", "to_date", default=None,
              help="End date (YYYY-MM-DD).")
@click.option("-n", "--limit", default=20, type=int,
              help="Max number of transactions to show.")
@click.option("--format", "fmt", type=click.Choice(["table", "json"]), default="table",
              help="Output format.")
@click.pass_context
def list_transactions(ctx, account_name, from_date, to_date, limit, fmt):
    """List recent transactions."""
    config = ctx.obj["config"]
    book_path = resolve_book_path(ctx.obj.get("book"), config)

    try:
        # Parse dates
        try:
            date_from = datetime.strptime(from_date, "%Y-%m-%d").date() if from_date else None
            date_to = datetime.strptime(to_date, "%Y-%m-%d").date() if to_date else None
        except ValueError as e:
            error(f"Invalid date format: {e}. Use YYYY-MM-DD.")
            raise SystemExit(1)

        with safe_open_book(book_path, readonly=True, open_if_lock=True) as book:
            transactions = book.transactions

            # Filter by date
            if date_from:
                transactions = [t for t in transactions if t.post_date >= date_from]
            if date_to:
                transactions = [t for t in transactions if t.post_date <= date_to]

            # Filter by account
            if account_name:
                transactions = [
                    t for t in transactions
                    if any(s.account.fullname == account_name for s in t.splits)
                ]

            # Sort by date descending, take limit
            transactions = sorted(transactions, key=lambda t: t.post_date, reverse=True)[:limit]

            # Build data
            tx_data = []
            for tr in transactions:
                splits_data = []
                for sp in tr.splits:
                    splits_data.append({
                        "account": sp.account.fullname,
                        "value": float(sp.value),
                        "quantity": float(sp.quantity),
                        "currency": sp.account.commodity.mnemonic if sp.account.commodity else "?",
                        "memo": sp.memo or "",
                    })
                tx_data.append({
                    "date": tr.post_date.isoformat(),
                    "description": tr.description,
                    "currency": tr.currency.mnemonic,
                    "splits": splits_data,
                })

            if fmt == "json":
                output_result({"transactions": tx_data, "count": len(tx_data)}, fmt="json")
            else:
                if tx_data:
                    print_transactions_table(tx_data)
                else:
                    console.print("[dim]No transactions found.[/dim]")

    except Exception as e:
        error(f"Failed to list transactions: {e}")
        raise SystemExit(1)
