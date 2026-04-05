import pytest
import os
from unittest.mock import MagicMock
from pathlib import Path

@pytest.fixture
def sample_config():
    """A sample configuration dictionary."""
    return {
        "default_currency": "TWD",
        "default_book": "/path/to/default.gnucash"
    }

@pytest.fixture
def tmp_book_path(tmp_path):
    """A temporary path for a GnuCash book."""
    return str(tmp_path / "test.gnucash")

@pytest.fixture
def mock_book():
    """A mocked piecash book."""
    book = MagicMock()
    
    # Setup some mock commodities
    mock_twd = MagicMock()
    mock_twd.mnemonic = "TWD"
    mock_usd = MagicMock()
    mock_usd.mnemonic = "USD"
    
    book.commodities.get.side_effect = lambda mnemonic, **kwargs: mock_twd if mnemonic == "TWD" else mock_usd

    # Setup some mock accounts
    mock_account = MagicMock()
    mock_account.fullname = "Assets:Cash"
    mock_account.commodity = mock_twd
    
    mock_usd_account = MagicMock()
    mock_usd_account.fullname = "Assets:USD"
    mock_usd_account.commodity = mock_usd
    
    def get_account(fullname):
        if fullname == "Assets:Cash":
            return mock_account
        elif fullname == "Assets:USD":
            return mock_usd_account
        else:
            raise Exception(f"Account not found: {fullname}")
            
    book.accounts = MagicMock(side_effect=get_account)
    
    return book
