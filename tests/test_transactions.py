import pytest
from decimal import Decimal
from unittest.mock import MagicMock, patch

from gnucash_cli.service import build_split, add_transaction

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

@patch('gnucash_cli.service.safe_open_book')
@patch('gnucash_cli.service.auto_backup_if_needed')
def test_add_transaction_balance_validation(mock_backup, mock_open, mock_book):
    """Test add_transaction raises ValueError on unbalanced splits."""
    
    # Setup context manager mock
    mock_context = MagicMock()
    mock_context.__enter__.return_value = mock_book
    mock_open.return_value = mock_context
    
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

@patch('gnucash_cli.service.safe_open_book')
@patch('gnucash_cli.service.auto_backup_if_needed')
@patch('gnucash_cli.service.piecash')
def test_add_transaction_balanced(mock_piecash, mock_backup, mock_open, mock_book):
    """Test add_transaction succeeds with balanced splits."""
    
    # Setup context manager mock
    mock_context = MagicMock()
    mock_context.__enter__.return_value = mock_book
    mock_open.return_value = mock_context
    
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
    mock_book.save.assert_called_once()
