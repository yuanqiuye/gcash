"""Backward-compatible facade for domain services."""

from gnucash_cli.services.accounts import (
    VALID_ACCOUNT_TYPES,
    create_account,
    list_accounts,
    validate_account_input,
)
from gnucash_cli.services.currencies import (
    add_currency,
    fetch_exchange_rates,
    list_currencies,
    update_prices,
)
from gnucash_cli.services.transactions import (
    add_transaction,
    add_transaction_input,
    build_split,
    edit_transaction,
    list_account_transactions,
    parse_split_spec,
)

_validate_account_input = validate_account_input


__all__ = [
    "VALID_ACCOUNT_TYPES",
    "_validate_account_input",
    "add_currency",
    "add_transaction",
    "add_transaction_input",
    "build_split",
    "create_account",
    "edit_transaction",
    "fetch_exchange_rates",
    "list_account_transactions",
    "list_accounts",
    "list_currencies",
    "parse_split_spec",
    "update_prices",
    "validate_account_input",
]
