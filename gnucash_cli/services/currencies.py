"""Currency domain operations."""

from datetime import date
from decimal import Decimal
from typing import Callable

import piecash
import requests
from piecash.core.commodity import Price as PiecashPrice

from gnucash_cli.book_ops import readonly_book, writable_book
from gnucash_cli.exceptions import ValidationError
from gnucash_cli.logging_config import logger

RateFetcher = Callable[[str], dict]


def list_currencies(book_path: str) -> dict:
    with readonly_book(book_path) as book:
        currencies = [
            commodity for commodity in book.commodities
            if commodity.namespace == "CURRENCY"
        ]
        return {
            "currencies": [
                {
                    "mnemonic": commodity.mnemonic,
                    "fullname": commodity.fullname or commodity.mnemonic,
                    "fraction": commodity.fraction,
                }
                for commodity in currencies
            ]
        }


def add_currency(
    book_path: str,
    code: str,
    config: dict,
    no_auto_backup: bool = False,
) -> dict:
    normalized_code = _normalize_currency_code(code)

    with writable_book(
        book_path,
        config,
        action_name="pre_currency_add",
        no_auto_backup=no_auto_backup,
    ) as book:
        existing = [
            commodity for commodity in book.commodities
            if commodity.namespace == "CURRENCY" and commodity.mnemonic == normalized_code
        ]
        if existing:
            raise ValidationError(f"Currency '{normalized_code}' already exists in the book.")

        commodity = piecash.factories.create_currency_from_ISO(normalized_code)
        book.add(commodity)
        book.save()

        return {
            "status": "success",
            "currency": {
                "mnemonic": normalized_code,
                "fullname": commodity.fullname or normalized_code,
                "fraction": commodity.fraction,
            },
        }


def update_prices(
    book_path: str,
    base_currency: str,
    config: dict,
    no_auto_backup: bool = False,
    rate_fetcher: RateFetcher | None = None,
) -> dict:
    base_currency = _normalize_currency_code(base_currency)
    fetcher = rate_fetcher or fetch_exchange_rates
    rate_data = fetcher(base_currency)

    if rate_data.get("result") != "success":
        raise ValidationError(f"API error: {rate_data.get('error-type', 'unknown error')}")

    all_rates = rate_data.get("rates", {})

    with writable_book(
        book_path,
        config,
        action_name="pre_update_prices",
        no_auto_backup=no_auto_backup,
    ) as book:
        currencies = [
            commodity for commodity in book.commodities
            if commodity.namespace == "CURRENCY" and commodity.mnemonic != base_currency
        ]

        if not currencies:
            return {
                "status": "success",
                "base": base_currency,
                "date": date.today().isoformat(),
                "prices": [],
            }

        try:
            base_commodity = book.commodities.get(mnemonic=base_currency)
        except Exception:
            raise ValidationError(f"Base currency '{base_currency}' not found in book.")

        results = []
        today = date.today()

        for target_commodity in currencies:
            target_code = target_commodity.mnemonic
            rate = all_rates.get(target_code)
            if rate is None or rate == 0:
                logger.warning("No exchange rate available for %s; skipping", target_code)
                continue

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
                "rate": str(price_value),
                "meaning": f"1 {target_code} = {price_value} {base_currency}",
            })

        book.save()
        logger.info("Updated %d exchange rates (base=%s)", len(results), base_currency)

        return {
            "status": "success",
            "base": base_currency,
            "date": today.isoformat(),
            "prices": results,
        }


def fetch_exchange_rates(base_currency: str) -> dict:
    logger.info("Fetching exchange rates from open.er-api.com (base=%s)", base_currency)
    try:
        response = requests.get(
            f"https://open.er-api.com/v6/latest/{base_currency}",
            timeout=15,
        )
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        logger.error("Failed to fetch exchange rates: %s", e)
        raise ValidationError(f"Failed to fetch exchange rates: {e}") from e


def _normalize_currency_code(code: str) -> str:
    normalized = (code or "").strip().upper()
    if len(normalized) != 3 or not normalized.isalpha():
        raise ValidationError("Currency code must be a 3-letter ISO code.")
    return normalized


__all__ = [
    "add_currency",
    "fetch_exchange_rates",
    "list_currencies",
    "update_prices",
]
