"""Account management commands."""

import click

from gnucash_cli.book_access import safe_open_book
from gnucash_cli.cli_safety import resolve_no_auto_backup
from gnucash_cli.config import resolve_book_path
from gnucash_cli.exceptions import GCashError
from gnucash_cli.presentation import (
    error,
    output_result,
    print_account_tree,
    success,
)
from gnucash_cli.services.accounts import create_account as service_create_account
from gnucash_cli.services.accounts import list_accounts as service_list_accounts


@click.group("accounts")
def accounts_group():
    """Manage accounts (list, create)."""
    pass


@accounts_group.command("list")
@click.option("--format", "fmt", type=click.Choice(["table", "json"]), default="table",
              help="Output format.")
@click.option("--type", "account_type", default=None,
              help="Filter by account type (ASSET, BANK, CASH, EXPENSE, INCOME, LIABILITY, EQUITY, CREDIT).")
@click.pass_context
def list_accounts(ctx, fmt, account_type):
    """List all accounts in the book."""
    book_path = resolve_book_path(ctx.obj.get("book"), ctx.obj["config"])

    try:
        if fmt == "json":
            result = service_list_accounts(book_path, account_type)
            output_result(result, fmt="json")
        else:
            with safe_open_book(book_path, readonly=True) as book:
                print_account_tree(book, type_filter=account_type.upper() if account_type else None)
    except GCashError as e:
        error(f"Failed to list accounts: {e}")
        raise SystemExit(1)


@accounts_group.command("create")
@click.option("--name", required=True, help="Account name.")
@click.option("--type", "account_type", required=True,
              type=click.Choice(["ASSET", "BANK", "CASH", "CREDIT", "LIABILITY",
                                 "INCOME", "EXPENSE", "EQUITY", "RECEIVABLE", "PAYABLE",
                                 "MUTUAL", "STOCK", "TRADING"],
                                case_sensitive=False),
              help="Account type.")
@click.option("--parent", "parent_fullname", default=None,
              help="Parent account fullname (e.g. 'Expenses'). Defaults to root account.")
@click.option("--parent-id", "parent_account_id", default=None,
              help="Stable parent account id returned by 'accounts list --format json'.")
@click.option("--currency", default=None,
              help="Currency for this account (ISO code). Defaults to config default_currency.")
@click.option("--placeholder", is_flag=True, default=False,
              help="Mark as placeholder (cannot hold transactions directly).")
@click.option("--description", default="", help="Account description.")
@click.option("--format", "fmt", type=click.Choice(["table", "json"]), default="table",
              help="Output format.")
@click.option("--unsafe-no-auto-backup", "unsafe_no_auto_backup", is_flag=True,
              help="Disable automatic safety backup. Requires allow_unsafe_no_auto_backup: true.")
@click.option("--no-auto-backup", "legacy_no_auto_backup", is_flag=True, hidden=True)
@click.pass_context
def create_account(ctx, name, account_type, parent_fullname, parent_account_id, currency, placeholder, description, fmt, unsafe_no_auto_backup, legacy_no_auto_backup):
    """Create a new account."""
    config = ctx.obj["config"]
    book_path = resolve_book_path(ctx.obj.get("book"), config)
    no_auto_backup = resolve_no_auto_backup(config, unsafe_no_auto_backup or legacy_no_auto_backup)

    try:
        result = service_create_account(
            book_path=book_path,
            name=name,
            account_type=account_type,
            parent_fullname=parent_fullname,
            parent_account_id=parent_account_id,
            currency_code=currency,
            placeholder=placeholder,
            description=description,
            config=config,
            no_auto_backup=no_auto_backup
        )

        if fmt == "json":
            output_result(result, fmt="json")
        else:
            acc = result["account"]
            success(f"Created account: {acc['fullname']} [{acc['type']}] ({acc['currency']})")

    except GCashError as e:
        error(f"Failed to create account: {e}")
        raise SystemExit(1)
