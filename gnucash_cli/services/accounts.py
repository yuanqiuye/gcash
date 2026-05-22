"""Account domain operations."""

import piecash

from gnucash_cli.book_data import build_account_tree_data
from gnucash_cli.book_ops import readonly_book, writable_book
from gnucash_cli.exceptions import ValidationError
from gnucash_cli.logging_config import logger

VALID_ACCOUNT_TYPES = {
    "ASSET",
    "BANK",
    "CASH",
    "CREDIT",
    "LIABILITY",
    "INCOME",
    "EXPENSE",
    "EQUITY",
    "RECEIVABLE",
    "PAYABLE",
    "MUTUAL",
    "STOCK",
    "TRADING",
}


def validate_account_input(name: str, account_type: str) -> str:
    if not name or not name.strip():
        raise ValidationError("Account name is required.")
    if not account_type:
        raise ValidationError("Account type is required.")

    normalized_type = account_type.upper()
    if normalized_type not in VALID_ACCOUNT_TYPES:
        allowed = ", ".join(sorted(VALID_ACCOUNT_TYPES))
        raise ValidationError(f"Invalid account type '{account_type}'. Expected one of: {allowed}.")
    return normalized_type


def list_accounts(book_path: str, account_type: str | None = None) -> dict:
    with readonly_book(book_path) as book:
        data = build_account_tree_data(book)
        if account_type:
            data = [a for a in data if a["type"] == account_type.upper()]
        return {"accounts": data}


def create_account(
    book_path: str,
    name: str,
    account_type: str,
    parent_fullname: str | None,
    currency_code: str | None,
    placeholder: bool,
    description: str,
    config: dict,
    no_auto_backup: bool = False,
) -> dict:
    account_type = validate_account_input(name, account_type)
    currency_code = currency_code or config.get("default_currency", "TWD")

    logger.info("Creating account: '%s' (type=%s, parent=%s, currency=%s)", name, account_type, parent_fullname, currency_code)

    with writable_book(
        book_path,
        config,
        action_name="pre_create_account",
        no_auto_backup=no_auto_backup,
    ) as book:
        if parent_fullname:
            try:
                parent = book.accounts(fullname=parent_fullname)
            except Exception:
                raise ValidationError(f"Parent account '{parent_fullname}' not found.")
        else:
            parent = book.root_account

        try:
            commodity = book.commodities.get(mnemonic=currency_code)
        except Exception:
            try:
                commodity = piecash.factories.create_currency_from_ISO(currency_code)
                book.add(commodity)
                book.flush()
            except Exception:
                raise ValidationError(f"Currency '{currency_code}' not found and could not be created.")

        target_fullname = f"{parent.fullname}:{name}" if parent.fullname else name
        for account in book.accounts:
            if account.fullname == target_fullname:
                raise ValidationError(f"Account '{target_fullname}' already exists.")

        new_account = piecash.Account(
            name=name,
            type=account_type,
            parent=parent,
            commodity=commodity,
            placeholder=placeholder,
            description=description,
        )
        book.save()
        logger.info("Account created: '%s'", target_fullname)

        return {
            "status": "success",
            "account": {
                "fullname": new_account.fullname,
                "name": new_account.name,
                "type": new_account.type,
                "currency": currency_code,
                "placeholder": placeholder,
                "description": description,
            },
        }


__all__ = [
    "VALID_ACCOUNT_TYPES",
    "create_account",
    "list_accounts",
    "validate_account_input",
]
