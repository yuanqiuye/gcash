from unittest.mock import MagicMock

import pytest


@pytest.fixture(autouse=True)
def isolated_runtime_dirs(tmp_path, monkeypatch):
    """Keep lock and backup runtime files out of the user's home/workspace."""
    monkeypatch.setenv("GNUCASH_LOCK_DIR", str(tmp_path / "locks"))
    monkeypatch.setenv("GNUCASH_BACKUP_DIR", str(tmp_path / "backups"))


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
    mock_account.guid = "cash-guid"
    mock_account.fullname = "Assets:Cash"
    mock_account.name = "Cash"
    mock_account.placeholder = False
    mock_account.children = []
    mock_account.commodity = mock_twd
    
    mock_usd_account = MagicMock()
    mock_usd_account.guid = "usd-guid"
    mock_usd_account.fullname = "Assets:USD"
    mock_usd_account.name = "USD"
    mock_usd_account.placeholder = False
    mock_usd_account.children = []
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
