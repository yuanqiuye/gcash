"""Transaction domain operations."""

from datetime import date, datetime
from decimal import Decimal

import piecash

from gnucash_cli.book_ops import writable_book
from gnucash_cli.exceptions import ValidationError
from gnucash_cli.logging_config import logger
from gnucash_cli.transaction_input import (
    SplitInput,
    TransactionInput,
    build_transaction_input,
    coerce_split_input,
    parse_split_spec,
)


def build_split(book, spec: SplitInput | dict | str, is_debit: bool, tx_commodity) -> dict:
    """Build a split dict from a parsed spec."""
    split_input = coerce_split_input(spec)
    try:
        account = book.accounts(fullname=split_input.account_fullname)
    except Exception:
        raise ValidationError(f"Account '{split_input.account_fullname}' not found.")

    value = abs(split_input.value) if is_debit else -abs(split_input.value)
    quantity = split_input.quantity
    if quantity is not None:
        quantity = abs(quantity) if is_debit else -abs(quantity)

    account_currency = account.commodity.mnemonic if account.commodity else None
    tx_currency = tx_commodity.mnemonic
    spec_currency = split_input.currency

    if account_currency and spec_currency and spec_currency != account_currency:
        raise ValidationError(
            f"Split currency '{spec_currency}' for '{split_input.account_fullname}' "
            f"does not match account currency '{account_currency}'."
        )

    if account_currency and account_currency != tx_currency and quantity is None:
        raise ValidationError(
            f"Multi-currency split for '{split_input.account_fullname}' "
            f"(account={account_currency}, transaction={tx_currency}): "
            f"please specify quantity. "
            f"Format: \"Account value CURRENCY quantity\" "
            f"(e.g. \"Assets:USD 930 USD 30\" means value=930 {tx_currency}, quantity=30 USD)"
        )

    return {
        "account": account,
        "value": value,
        "quantity": quantity,
    }


def add_transaction_input(
    book_path: str,
    tx_input: TransactionInput,
    config: dict,
    no_auto_backup: bool = False,
) -> dict:
    default_currency = tx_input.currency or config.get("default_currency", "TWD")
    post_date = tx_input.post_date
    debit_specs = tx_input.debits
    credit_specs = tx_input.credits

    logger.info(
        "Adding transaction: '%s' on %s (%d debits, %d credits, currency=%s)",
        tx_input.description, post_date, len(debit_specs), len(credit_specs), default_currency,
    )

    with writable_book(
        book_path,
        config,
        action_name="pre_tx",
        no_auto_backup=no_auto_backup,
    ) as book:
        try:
            tx_commodity = book.commodities.get(mnemonic=default_currency)
        except Exception:
            raise ValidationError(f"Transaction currency '{default_currency}' not found in book.")

        splits = []
        for spec in debit_specs:
            splits.append(build_split(book, spec, is_debit=True, tx_commodity=tx_commodity))
        for spec in credit_specs:
            splits.append(build_split(book, spec, is_debit=False, tx_commodity=tx_commodity))

        total_value = sum(s["value"] for s in splits)
        if total_value != Decimal("0"):
            logger.warning("Transaction unbalanced: '%s' total=%s", tx_input.description, total_value)
            raise ValidationError(
                f"Transaction is not balanced. Total value: {total_value} (should be 0).\n"
                "Debit values should be positive, credit values should be negative."
            )

        piecash_splits = []
        for split in splits:
            split_kwargs = {"account": split["account"], "value": split["value"]}
            if split["quantity"] is not None:
                split_kwargs["quantity"] = split["quantity"]
            piecash_splits.append(piecash.Split(**split_kwargs))

        transaction = piecash.Transaction(
            currency=tx_commodity,
            description=tx_input.description,
            post_date=post_date,
            enter_date=datetime.now(),
            splits=piecash_splits,
        )

        if tx_input.notes:
            transaction.notes = tx_input.notes

        book.save()
        logger.info("Transaction saved: '%s' (%d splits)", tx_input.description, len(splits))

        return {
            "status": "success",
            "transaction": {
                "date": post_date.isoformat(),
                "description": tx_input.description,
                "currency": default_currency,
                "splits": [
                    {
                        "account": split["account"].fullname,
                        "value": str(split["value"]),
                        "quantity": str(split["quantity"]) if split["quantity"] is not None else str(split["value"]),
                        "currency": split["account"].commodity.mnemonic if split["account"].commodity else default_currency,
                    }
                    for split in splits
                ],
            },
        }


def add_transaction(
    book_path: str,
    description: str,
    debits: list[object],
    credits_: list[object],
    tx_date: str | date | None,
    tx_currency: str | None,
    notes: str,
    config: dict,
    no_auto_backup: bool = False,
) -> dict:
    tx_input = build_transaction_input(
        description=description,
        debits=debits,
        credits=credits_,
        tx_date=tx_date,
        tx_currency=tx_currency,
        notes=notes,
    )
    return add_transaction_input(
        book_path=book_path,
        tx_input=tx_input,
        config=config,
        no_auto_backup=no_auto_backup,
    )


__all__ = [
    "add_transaction",
    "add_transaction_input",
    "build_split",
    "parse_split_spec",
]
