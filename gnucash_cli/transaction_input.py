"""Shared transaction input models.

The CLI, FastAPI API, MCP server, and service layer all accept the same
transaction shape. Legacy string split specs are still supported for existing
scripts, while structured split objects give adapters a stable schema.
"""

from __future__ import annotations

import re
from datetime import date as Date
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic import ValidationError as PydanticValidationError

from gnucash_cli.exceptions import ValidationError


def parse_split_spec(spec: str) -> dict[str, Any]:
    """Parse a legacy split specification string."""
    if not spec or not spec.strip():
        raise ValidationError("Split spec is required.")

    if len(spec.rsplit(maxsplit=3)) < 2:
        raise ValidationError(
            f"Invalid split spec: '{spec}'. Expected: 'AccountName amount [currency [quantity]]'"
        )

    match = re.match(r"^(.+?)\s+(-?[\d,]+\.?\d*)\s+([A-Z]{3})\s+(-?[\d,]+\.?\d*)$", spec)
    if match:
        return {
            "account_fullname": match.group(1).strip(),
            "value": Decimal(match.group(2).replace(",", "")),
            "currency": match.group(3),
            "quantity": Decimal(match.group(4).replace(",", "")),
        }

    match = re.match(r"^(.+?)\s+(-?[\d,]+\.?\d*)\s+([A-Z]{3})$", spec)
    if match:
        return {
            "account_fullname": match.group(1).strip(),
            "value": Decimal(match.group(2).replace(",", "")),
            "currency": match.group(3),
            "quantity": None,
        }

    match = re.match(r"^(.+?)\s+(-?[\d,]+\.?\d*)$", spec)
    if match:
        return {
            "account_fullname": match.group(1).strip(),
            "value": Decimal(match.group(2).replace(",", "")),
            "currency": None,
            "quantity": None,
        }

    raise ValidationError(f"Cannot parse split spec: '{spec}'")


class SplitInput(BaseModel):
    """A single debit or credit split before sign normalization."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    account_fullname: str = Field(alias="account", min_length=1)
    value: Decimal = Field(gt=Decimal("0"))
    currency: str | None = None
    quantity: Decimal | None = Field(default=None, gt=Decimal("0"))

    @model_validator(mode="before")
    @classmethod
    def parse_legacy_string(cls, value: Any) -> Any:
        if isinstance(value, str):
            return parse_split_spec(value)
        return value

    @field_validator("value", "quantity", mode="before")
    @classmethod
    def reject_float_amounts(cls, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, bool):
            raise ValueError("Amounts must be decimal strings, not booleans.")
        if isinstance(value, float):
            raise ValueError("Amounts must be decimal strings; JSON floats are not accepted.")
        return value

    @field_validator("account_fullname")
    @classmethod
    def normalize_account(cls, value: str) -> str:
        account = value.strip()
        if not account:
            raise ValueError("Split account is required.")
        return account

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str | None) -> str | None:
        if value is None:
            return None
        currency = value.strip().upper()
        if not re.fullmatch(r"[A-Z]{3}", currency):
            raise ValueError("Split currency must be a 3-letter ISO code.")
        return currency


class TransactionInput(BaseModel):
    """Normalized transaction request used by all adapters."""

    model_config = ConfigDict(extra="forbid")

    description: str = Field(min_length=1)
    debits: list[SplitInput] = Field(min_length=1)
    credits: list[SplitInput] = Field(min_length=1)
    date: Date | None = None
    notes: str = ""
    currency: str | None = None

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str) -> str:
        description = value.strip()
        if not description:
            raise ValueError("Transaction description is required.")
        return description

    @field_validator("notes", mode="before")
    @classmethod
    def normalize_notes(cls, value: Any) -> str:
        if value is None:
            return ""
        return str(value)

    @field_validator("currency")
    @classmethod
    def normalize_transaction_currency(cls, value: str | None) -> str | None:
        if value is None:
            return None
        currency = value.strip().upper()
        if not re.fullmatch(r"[A-Z]{3}", currency):
            raise ValueError("Transaction currency must be a 3-letter ISO code.")
        return currency

    @field_validator("date", mode="before")
    @classmethod
    def normalize_empty_date(cls, value: Any) -> Any:
        if value == "":
            return None
        return value

    @property
    def post_date(self) -> Date:
        return self.date or Date.today()


def _format_pydantic_error(exc: PydanticValidationError) -> str:
    first = exc.errors()[0]
    loc = ".".join(str(part) for part in first.get("loc", ())) or "input"
    return f"Invalid transaction input at {loc}: {first.get('msg', 'invalid value')}"


def coerce_split_input(value: Any) -> SplitInput:
    try:
        if isinstance(value, SplitInput):
            return value
        return SplitInput.model_validate(value)
    except PydanticValidationError as exc:
        raise ValidationError(_format_pydantic_error(exc)) from exc


def build_transaction_input(
    *,
    description: str,
    debits: list[Any],
    credits: list[Any],
    tx_date: str | Date | None,
    tx_currency: str | None,
    notes: str | None,
) -> TransactionInput:
    try:
        return TransactionInput(
            description=description,
            debits=debits,
            credits=credits,
            date=tx_date,
            currency=tx_currency,
            notes=notes,
        )
    except PydanticValidationError as exc:
        raise ValidationError(_format_pydantic_error(exc)) from exc
