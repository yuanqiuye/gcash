"""Transaction domain operations."""

from datetime import date, datetime
from decimal import Decimal

import piecash

from gnucash_cli.account_lookup import account_id, resolve_account
from gnucash_cli.book_ops import readonly_book, writable_book
from gnucash_cli.exceptions import ValidationError
from gnucash_cli.logging_config import logger
from gnucash_cli.transaction_input import (
    SplitInput,
    TransactionInput,
    build_transaction_input,
    coerce_split_input,
    parse_split_spec,
)


def _object_id(value) -> str | None:
    identifier = getattr(value, "guid", None)
    if identifier is None:
        return None
    text = str(identifier).strip()
    return text or None


def _transaction_id(transaction) -> str | None:
    return _object_id(transaction)


def _split_id(split) -> str | None:
    return _object_id(split)


def _parse_transaction_date(value: str | date | datetime | None) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise ValidationError(f"Invalid transaction date '{value}'. Expected YYYY-MM-DD.") from exc
    raise ValidationError("Transaction date must be a YYYY-MM-DD string or date object.")


def _iter_transactions(book) -> list:
    try:
        return list(book.transactions)
    except TypeError:
        return []


def _serialize_split(split, default_currency: str | None) -> dict:
    account = split.account
    identifier = _split_id(split)
    return {
        "split_id": identifier,
        "id": identifier,
        "account_id": account_id(account),
        "account": account.fullname,
        "value": str(split.value),
        "quantity": str(split.quantity),
        "currency": account.commodity.mnemonic if account.commodity else default_currency,
        "memo": getattr(split, "memo", "") or "",
        "action": getattr(split, "action", "") or "",
    }


def _serialize_transaction(transaction) -> dict:
    default_currency = transaction.currency.mnemonic if transaction.currency else None
    identifier = _transaction_id(transaction)
    return {
        "transaction_id": identifier,
        "id": identifier,
        "guid": identifier,
        "date": transaction.post_date.isoformat(),
        "description": transaction.description or "",
        "notes": getattr(transaction, "notes", "") or "",
        "currency": default_currency,
        "splits": [_serialize_split(split, default_currency) for split in transaction.splits],
    }


def _resolve_transaction(book, transaction_id: str):
    target = str(transaction_id).strip()
    if not target:
        raise ValidationError("transaction_id is required.")

    for transaction in _iter_transactions(book):
        if _transaction_id(transaction) == target:
            return transaction

    raise ValidationError(f"Transaction id '{target}' not found.")


def _build_signed_splits(book, debit_specs: list[object], credit_specs: list[object], tx_commodity) -> list[dict]:
    if not debit_specs:
        raise ValidationError("Transaction must include at least one debit split.")
    if not credit_specs:
        raise ValidationError("Transaction must include at least one credit split.")

    splits = []
    for spec in debit_specs:
        splits.append(build_split(book, spec, is_debit=True, tx_commodity=tx_commodity))
    for spec in credit_specs:
        splits.append(build_split(book, spec, is_debit=False, tx_commodity=tx_commodity))

    total_value = sum(split["value"] for split in splits)
    if total_value != Decimal("0"):
        raise ValidationError(
            f"Transaction is not balanced. Total value: {total_value} (should be 0).\n"
            "Debit values should be positive, credit values should be negative."
        )
    return splits


def _make_piecash_splits(splits: list[dict]) -> list:
    piecash_splits = []
    for split in splits:
        split_kwargs = {"account": split["account"], "value": split["value"]}
        if split["quantity"] is not None:
            split_kwargs["quantity"] = split["quantity"]
        piecash_splits.append(piecash.Split(**split_kwargs))
    return piecash_splits


def build_split(book, spec: SplitInput | dict | str, is_debit: bool, tx_commodity) -> dict:
    """Build a split dict from a parsed spec."""
    split_input = coerce_split_input(spec)
    account = resolve_account(
        book,
        account_id_value=split_input.account_id,
        account_fullname=split_input.account_fullname,
        require_postable=True,
    )

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

        try:
            splits = _build_signed_splits(book, debit_specs, credit_specs, tx_commodity)
        except ValidationError as exc:
            logger.warning("Transaction rejected: '%s' %s", tx_input.description, exc)
            raise

        piecash_splits = _make_piecash_splits(splits)

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
                "transaction_id": _transaction_id(transaction),
                "id": _transaction_id(transaction),
                "guid": _transaction_id(transaction),
                "date": post_date.isoformat(),
                "description": tx_input.description,
                "currency": default_currency,
                "splits": [
                    {
                        "account_id": account_id(split["account"]),
                        "account": split["account"].fullname,
                        "value": str(split["value"]),
                        "quantity": str(split["quantity"]) if split["quantity"] is not None else str(split["value"]),
                        "currency": split["account"].commodity.mnemonic if split["account"].commodity else default_currency,
                    }
                    for split in splits
                ],
            },
        }


def list_account_transactions(
    book_path: str,
    account_id_value: str | None,
    account_fullname: str | None,
    limit: int,
) -> dict:
    try:
        effective_limit = int(limit)
    except (TypeError, ValueError) as exc:
        raise ValidationError("limit must be an integer.") from exc

    if effective_limit < 1 or effective_limit > 100:
        raise ValidationError("limit must be between 1 and 100.")

    with readonly_book(book_path) as book:
        account = resolve_account(
            book,
            account_id_value=account_id_value,
            account_fullname=account_fullname,
            require_postable=False,
        )
        target_id = account_id(account)

        transactions = [
            transaction
            for transaction in _iter_transactions(book)
            if any(account_id(split.account) == target_id for split in transaction.splits)
        ]
        transactions.sort(
            key=lambda transaction: (
                transaction.post_date or date.min,
                getattr(transaction, "enter_date", None) or datetime.min,
                _transaction_id(transaction) or "",
            ),
            reverse=True,
        )
        selected = transactions[:effective_limit]

        return {
            "account": {
                "id": target_id,
                "guid": target_id,
                "fullname": account.fullname,
                "name": account.name,
            },
            "transactions": [_serialize_transaction(transaction) for transaction in selected],
            "count": len(selected),
        }


def edit_transaction(
    book_path: str,
    transaction_id: str,
    description: str | None,
    tx_date: str | date | None,
    notes: str | None,
    debits: list[object] | None,
    credits_: list[object] | None,
    config: dict,
    no_auto_backup: bool = False,
) -> dict:
    replace_splits = debits is not None or credits_ is not None
    post_date = _parse_transaction_date(tx_date)

    if description is None and post_date is None and notes is None and not replace_splits:
        raise ValidationError("No transaction updates provided.")

    if replace_splits and (debits is None or credits_ is None):
        raise ValidationError("Replacing splits requires both debits and credits.")

    if description is not None:
        description = str(description).strip()
        if not description:
            raise ValidationError("Transaction description cannot be empty.")

    with writable_book(
        book_path,
        config,
        action_name="pre_edit_tx",
        no_auto_backup=no_auto_backup,
    ) as book:
        transaction = _resolve_transaction(book, transaction_id)

        if description is not None:
            transaction.description = description
        if post_date is not None:
            transaction.post_date = post_date
        if notes is not None:
            transaction.notes = str(notes)

        if replace_splits:
            splits = _build_signed_splits(book, debits, credits_, transaction.currency)
            transaction.splits[:] = _make_piecash_splits(splits)

        book.save()
        logger.info("Transaction edited: '%s'", transaction_id)

        return {
            "status": "success",
            "transaction": _serialize_transaction(transaction),
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
    "edit_transaction",
    "list_account_transactions",
    "parse_split_spec",
]
