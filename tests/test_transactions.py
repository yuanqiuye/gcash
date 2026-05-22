import warnings
from decimal import Decimal
from unittest.mock import MagicMock, patch

import piecash
import pytest

from gnucash_cli.service import add_transaction, build_split, create_account


def _create_minimal_book(book_path):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        book = piecash.create_book(str(book_path), currency="TWD", overwrite=True)
        twd = book.commodities.get(mnemonic="TWD")
        root = book.root_account
        assets = piecash.Account("Assets", "ASSET", twd, parent=root)
        piecash.Account("Cash", "ASSET", twd, parent=assets)
        expenses = piecash.Account("Expenses", "EXPENSE", twd, parent=root)
        piecash.Account("Dining", "EXPENSE", twd, parent=expenses)
        book.save()
        book.close()

def test_build_split_debit_credit_signs(mock_book):
    """Test build_split correctly handles positive/negative signs for debit/credit."""
    
    spec = {
        "account_fullname": "Assets:Cash",
        "value": Decimal("100"),
        "quantity": None,
        "currency": None
    }
    
    tx_commodity = mock_book.commodities.get(mnemonic="TWD")
    
    # Test debit
    debit_split = build_split(mock_book, spec, is_debit=True, tx_commodity=tx_commodity)
    assert debit_split["value"] == Decimal("100")
    
    # Test credit
    credit_split = build_split(mock_book, spec, is_debit=False, tx_commodity=tx_commodity)
    assert credit_split["value"] == Decimal("-100")
    
def test_build_split_with_quantity(mock_book):
    """Test build_split handles quantity signs."""
    
    spec = {
        "account_fullname": "Assets:Cash",
        "value": Decimal("100"),
        "quantity": Decimal("30"),
        "currency": None
    }
    
    tx_commodity = mock_book.commodities.get(mnemonic="TWD")
    
    debit_split = build_split(mock_book, spec, is_debit=True, tx_commodity=tx_commodity)
    assert debit_split["value"] == Decimal("100")
    assert debit_split["quantity"] == Decimal("30")
    
    credit_split = build_split(mock_book, spec, is_debit=False, tx_commodity=tx_commodity)
    assert credit_split["value"] == Decimal("-100")
    assert credit_split["quantity"] == Decimal("-30")


def test_build_split_rejects_currency_mismatch(mock_book):
    """A split currency token must describe the account currency."""

    spec = {
        "account_fullname": "Assets:Cash",
        "value": Decimal("100"),
        "quantity": None,
        "currency": "USD",
    }

    tx_commodity = mock_book.commodities.get(mnemonic="TWD")

    with pytest.raises(ValueError, match="does not match account currency"):
        build_split(mock_book, spec, is_debit=True, tx_commodity=tx_commodity)


def test_build_split_requires_quantity_for_multicurrency_account(mock_book):
    """Cross-currency account splits need an explicit account-currency quantity."""

    spec = {
        "account_fullname": "Assets:USD",
        "value": Decimal("930"),
        "quantity": None,
        "currency": "USD",
    }

    tx_commodity = mock_book.commodities.get(mnemonic="TWD")

    with pytest.raises(ValueError, match="please specify quantity"):
        build_split(mock_book, spec, is_debit=False, tx_commodity=tx_commodity)

@patch("gnucash_cli.services.transactions.writable_book")
def test_add_transaction_balance_validation(mock_writable_book, mock_book):
    """Test add_transaction raises ValueError on unbalanced splits."""
    
    # Setup context manager mock
    mock_context = MagicMock()
    mock_context.__enter__.return_value = mock_book
    mock_writable_book.return_value = mock_context
    
    # Run with unbalanced debits/credits: debit 100, credit 50
    with pytest.raises(ValueError, match="Transaction is not balanced"):
        add_transaction(
            book_path="/path/to/book.gnucash",
            description="Test",
            debits=["Assets:Cash 100"],
            credits_=["Assets:Cash 50"],
            tx_date=None,
            tx_currency=None,
            notes="",
            config={"default_currency": "TWD"},
            no_auto_backup=True
        )


def test_add_transaction_rejects_empty_splits():
    """The service layer must reject empty transactions, regardless of adapter."""

    with pytest.raises(ValueError, match="debits"):
        add_transaction(
            book_path="/path/to/book.gnucash",
            description="Empty",
            debits=[],
            credits_=[],
            tx_date=None,
            tx_currency=None,
            notes="",
            config={"default_currency": "TWD"},
            no_auto_backup=True,
        )


@patch("gnucash_cli.services.transactions.writable_book")
def test_add_transaction_rejects_negative_structured_amount_before_opening_book(mock_writable_book):
    with pytest.raises(ValueError, match="greater than 0"):
        add_transaction(
            book_path="/path/to/book.gnucash",
            description="Negative",
            debits=[{"account": "Assets:Cash", "value": "-10"}],
            credits_=[{"account": "Assets:Cash", "value": "10"}],
            tx_date=None,
            tx_currency=None,
            notes="",
            config={"default_currency": "TWD"},
            no_auto_backup=True,
        )

    mock_writable_book.assert_not_called()


@patch("gnucash_cli.services.transactions.writable_book")
def test_add_transaction_rejects_float_structured_amount_before_opening_book(mock_writable_book):
    with pytest.raises(ValueError, match="JSON floats are not accepted"):
        add_transaction(
            book_path="/path/to/book.gnucash",
            description="Float",
            debits=[{"account": "Assets:Cash", "value": 0.1}],
            credits_=[{"account": "Assets:Cash", "value": "0.10"}],
            tx_date=None,
            tx_currency=None,
            notes="",
            config={"default_currency": "TWD"},
            no_auto_backup=True,
        )

    mock_writable_book.assert_not_called()


def test_create_account_rejects_invalid_type_before_opening_book():
    with pytest.raises(ValueError, match="Invalid account type"):
        create_account(
            book_path="/path/to/book.gnucash",
            name="Invalid",
            account_type="ROOT",
            parent_fullname=None,
            currency_code=None,
            placeholder=False,
            description="",
            config={"default_currency": "TWD"},
            no_auto_backup=True,
        )

@patch("gnucash_cli.services.transactions.writable_book")
@patch("gnucash_cli.services.transactions.piecash")
def test_add_transaction_balanced(mock_piecash, mock_writable_book, mock_book):
    """Test add_transaction succeeds with balanced splits."""
    
    # Setup context manager mock
    mock_context = MagicMock()
    mock_context.__enter__.return_value = mock_book
    mock_writable_book.return_value = mock_context
    
    result = add_transaction(
        book_path="/path/to/book.gnucash",
        description="Test",
        debits=["Assets:Cash 100"],
        credits_=["Assets:Cash 100"],
        tx_date=None,
        tx_currency=None,
        notes="",
        config={"default_currency": "TWD"},
        no_auto_backup=True
    )
    
    assert result["status"] == "success"
    assert result["transaction"]["splits"][0]["value"] == "100"
    assert result["transaction"]["splits"][0]["quantity"] == "100"
    mock_book.save.assert_called_once()


@patch("gnucash_cli.services.transactions.writable_book")
@patch("gnucash_cli.services.transactions.piecash")
def test_add_transaction_accepts_structured_split_inputs(mock_piecash, mock_writable_book, mock_book):
    mock_context = MagicMock()
    mock_context.__enter__.return_value = mock_book
    mock_writable_book.return_value = mock_context

    result = add_transaction(
        book_path="/path/to/book.gnucash",
        description="Structured",
        debits=[{"account": "Assets:Cash", "value": "100.50"}],
        credits_=[{"account_fullname": "Assets:Cash", "value": Decimal("100.50")}],
        tx_date="2026-05-11",
        tx_currency="twd",
        notes=None,
        config={"default_currency": "TWD"},
        no_auto_backup=True,
    )

    assert result["status"] == "success"
    assert result["transaction"]["date"] == "2026-05-11"
    assert result["transaction"]["currency"] == "TWD"
    assert result["transaction"]["splits"][0]["value"] == "100.50"
    assert result["transaction"]["splits"][1]["value"] == "-100.50"


def test_add_transaction_writes_real_piecash_book(tmp_path, monkeypatch):
    """Integration: service writes a real SQLite GnuCash book via piecash."""

    monkeypatch.chdir(tmp_path)
    book_path = tmp_path / "integration.gnucash"
    _create_minimal_book(book_path)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        result = add_transaction(
            book_path=str(book_path),
            description="Lunch",
            debits=[{"account": "Expenses:Dining", "value": "150"}],
            credits_=[{"account": "Assets:Cash", "value": "150"}],
            tx_date="2026-05-11",
            tx_currency="TWD",
            notes="integration note",
            config={"default_currency": "TWD"},
            no_auto_backup=True,
        )

        book = piecash.open_book(str(book_path), readonly=True, open_if_lock=True, do_backup=False)
        try:
            transactions = list(book.transactions)
            tx = transactions[0]
            tx_description = tx.description
            tx_post_date = tx.post_date.isoformat()
            tx_notes = tx.notes
            splits = {
                split.account.fullname: {
                    "value": split.value,
                    "quantity": split.quantity,
                }
                for split in tx.splits
            }
        finally:
            book.close()

    assert result["status"] == "success"
    assert len(transactions) == 1
    assert tx_description == "Lunch"
    assert tx_post_date == "2026-05-11"
    assert tx_notes == "integration note"
    assert splits["Expenses:Dining"]["value"] == Decimal("150")
    assert splits["Assets:Cash"]["value"] == Decimal("-150")
