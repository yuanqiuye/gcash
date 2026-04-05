import re
import logging
from datetime import date, datetime
from decimal import Decimal

import piecash

from gnucash_cli.utils import safe_open_book, logger
from gnucash_cli.commands.db import auto_backup_if_needed
from gnucash_cli.utils import build_account_tree_data


def parse_split_spec(spec: str) -> dict:
    """Parse a split specification string."""
    parts = spec.rsplit(maxsplit=3)
    if len(parts) < 2:
        raise ValueError(f"Invalid split spec: '{spec}'. Expected: 'AccountName amount [currency [quantity]]'")

    match = re.match(r'^(.+?)\s+(-?[\d,]+\.?\d*)\s+([A-Z]{3})\s+(-?[\d,]+\.?\d*)$', spec)
    if match:
        return {
            "account_fullname": match.group(1).strip(),
            "value": Decimal(match.group(2).replace(",", "")),
            "currency": match.group(3),
            "quantity": Decimal(match.group(4).replace(",", "")),
        }

    match = re.match(r'^(.+?)\s+(-?[\d,]+\.?\d*)\s+([A-Z]{3})$', spec)
    if match:
        val = Decimal(match.group(2).replace(",", ""))
        return {
            "account_fullname": match.group(1).strip(),
            "value": val,
            "currency": match.group(3),
            "quantity": None,
        }

    match = re.match(r'^(.+?)\s+(-?[\d,]+\.?\d*)$', spec)
    if match:
        val = Decimal(match.group(2).replace(",", ""))
        return {
            "account_fullname": match.group(1).strip(),
            "value": val,
            "currency": None,
            "quantity": None,
        }

    raise ValueError(f"Cannot parse split spec: '{spec}'")


def build_split(book, spec: dict, is_debit: bool, tx_commodity) -> dict:
    """Build a split dict from a parsed spec."""
    try:
        account = book.accounts(fullname=spec["account_fullname"])
    except Exception:
        raise ValueError(f"Account '{spec['account_fullname']}' not found.")

    value = spec["value"]
    if not is_debit:
        value = -abs(value)
    else:
        value = abs(value)

    quantity = spec.get("quantity")
    if quantity is not None:
        if not is_debit:
            quantity = -abs(quantity)
        else:
            quantity = abs(quantity)

    account_currency = account.commodity.mnemonic if account.commodity else None
    tx_currency = tx_commodity.mnemonic

    if account_currency and account_currency != tx_currency and quantity is None:
        if spec.get("currency") and spec["currency"] == account_currency:
            raise ValueError(
                f"Multi-currency split for '{spec['account_fullname']}' "
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


def add_transaction(book_path: str, description: str, debits: list[str], credits_: list[str], tx_date: str | None, tx_currency: str | None, notes: str, config: dict, no_auto_backup: bool = False) -> dict:
    default_currency = tx_currency or config.get("default_currency", "TWD")

    if tx_date:
        try:
            post_date = datetime.strptime(tx_date, "%Y-%m-%d").date()
        except ValueError:
            raise ValueError(f"Invalid date format: '{tx_date}'. Use YYYY-MM-DD.")
    else:
        post_date = date.today()

    debit_specs = [parse_split_spec(d) for d in debits]
    credit_specs = [parse_split_spec(c) for c in credits_]
    
    logger.info(
        "Adding transaction: '%s' on %s (%d debits, %d credits, currency=%s)",
        description, post_date, len(debit_specs), len(credit_specs), default_currency,
    )

    auto_backup_if_needed(book_path, no_auto_backup, action_name="pre_tx")

    with safe_open_book(book_path, readonly=False, open_if_lock=True, do_backup=False) as book:
        try:
            tx_commodity = book.commodities.get(mnemonic=default_currency)
        except Exception:
            raise ValueError(f"Transaction currency '{default_currency}' not found in book.")

        splits = []
        for spec in debit_specs:
            splits.append(build_split(book, spec, is_debit=True, tx_commodity=tx_commodity))
        for spec in credit_specs:
            splits.append(build_split(book, spec, is_debit=False, tx_commodity=tx_commodity))

        total_value = sum(s["value"] for s in splits)
        if total_value != Decimal("0"):
            logger.warning("Transaction unbalanced: '%s' total=%s", description, total_value)
            raise ValueError(f"Transaction is not balanced. Total value: {total_value} (should be 0).\nDebit values should be positive, credit values should be negative.")

        piecash_splits = []
        for s in splits:
            split_kwargs = {"account": s["account"], "value": s["value"]}
            if s["quantity"] is not None:
                split_kwargs["quantity"] = s["quantity"]
            piecash_splits.append(piecash.Split(**split_kwargs))

        tr = piecash.Transaction(
            currency=tx_commodity,
            description=description,
            post_date=post_date,
            enter_date=datetime.now(),
            splits=piecash_splits,
        )

        if notes:
            tr.notes = notes

        book.save()
        logger.info("Transaction saved: '%s' (%d splits)", description, len(splits))

        result = {
            "status": "success",
            "transaction": {
                "date": post_date.isoformat(),
                "description": description,
                "currency": default_currency,
                "splits": [
                    {
                        "account": s["account"].fullname,
                        "value": float(s["value"]),
                        "quantity": float(s["quantity"]) if s["quantity"] else float(s["value"]),
                        "currency": s["account"].commodity.mnemonic if s["account"].commodity else default_currency,
                    }
                    for s in splits
                ],
            },
        }

    return result


def list_accounts(book_path: str, account_type: str | None = None) -> dict:
    with safe_open_book(book_path, readonly=True, open_if_lock=True) as book:
        data = build_account_tree_data(book)
        if account_type:
            data = [a for a in data if a["type"] == account_type.upper()]
        return {"accounts": data}


def create_account(book_path: str, name: str, account_type: str, parent_fullname: str | None, currency_code: str | None, placeholder: bool, description: str, config: dict, no_auto_backup: bool = False) -> dict:
    currency_code = currency_code or config.get("default_currency", "TWD")

    logger.info("Creating account: '%s' (type=%s, parent=%s, currency=%s)", name, account_type, parent_fullname, currency_code)

    auto_backup_if_needed(book_path, no_auto_backup, action_name="pre_create_account")

    with safe_open_book(book_path, readonly=False, open_if_lock=True, do_backup=False) as book:
        if parent_fullname:
            try:
                parent = book.accounts(fullname=parent_fullname)
            except Exception:
                raise ValueError(f"Parent account '{parent_fullname}' not found.")
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
                raise ValueError(f"Currency '{currency_code}' not found and could not be created.")

        target_fullname = f"{parent.fullname}:{name}" if parent.fullname else name
        for acc in book.accounts:
            if acc.fullname == target_fullname:
                raise ValueError(f"Account '{target_fullname}' already exists.")

        new_account = piecash.Account(
            name=name,
            type=account_type.upper(),
            parent=parent,
            commodity=commodity,
            placeholder=placeholder,
            description=description,
        )
        book.save()
        logger.info("Account created: '%s'", target_fullname)

        result = {
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
    return result
