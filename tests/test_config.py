import os
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from gnucash_cli.config import _expand_path, load_config, resolve_book_path


def test_load_config_defaults(tmp_path):
    """Test load_config returns defaults when no config file exists."""
    config_file = tmp_path / "non_existent.yaml"
    config = load_config(str(config_file))
    
    assert config["default_currency"] == "TWD"
    assert config["default_book"] is None
    assert config["mcp_allow_create_account"] is False

def test_load_config_override_from_yaml(tmp_path):
    """Test load_config overrides defaults with yaml values."""
    config_file = tmp_path / "config.yaml"
    with open(config_file, "w") as f:
        yaml.dump({"default_currency": "USD", "default_book": "/path/to/book.gnucash"}, f)
        
    config = load_config(str(config_file))
    
    assert config["default_currency"] == "USD"
    assert config["default_book"] == "/path/to/book.gnucash"


def test_load_config_uses_env_config_path(tmp_path):
    """Long-running adapters can inherit the explicit CLI config path."""
    config_file = tmp_path / "config.yaml"
    with open(config_file, "w") as f:
        yaml.dump({"default_currency": "JPY"}, f)

    with patch.dict(os.environ, {"GNUCASH_CONFIG": str(config_file)}):
        config = load_config()

    assert config["default_currency"] == "JPY"

@patch.dict(os.environ, {}, clear=True)
def test_resolve_book_path_priority(sample_config):
    """Test resolve_book_path priority: CLI > env > config"""
    
    # 1. CLI has highest priority
    with patch.dict(os.environ, {"GNUCASH_BOOK": "/env/book.gnucash"}):
        path = resolve_book_path("/cli/book.gnucash", sample_config)
        assert path.endswith("book.gnucash")
        assert "cli" in path
        
    # 2. Env has second priority
    with patch.dict(os.environ, {"GNUCASH_BOOK": "/env/book.gnucash"}):
        path = resolve_book_path(None, sample_config)
        assert path.endswith("book.gnucash")
        assert "env" in path
        
    # 3. Config has third priority
    path = resolve_book_path(None, sample_config)
    assert path.endswith("default.gnucash")
    assert "default.gnucash" in path

def test_resolve_book_path_missing(sample_config):
    """Test resolve_book_path raises error when no path is provided."""
    empty_config = {"default_currency": "TWD"}
    
    # Import click here because click_missing_book_error returns click.UsageError
    import click
    with pytest.raises(click.UsageError):
        resolve_book_path(None, empty_config)

def test_expand_path():
    """Test _expand_path expands ~ and returns absolute path."""
    home = str(Path.home())
    expanded = _expand_path("~/test.gnucash")
    assert expanded.startswith(home)
    assert "test.gnucash" in expanded
    
    # Test relative path
    rel_expanded = _expand_path("relative.gnucash")
    assert rel_expanded == str(Path("relative.gnucash").resolve())


def test_expand_path_preserves_database_urls():
    """Database URLs must not be resolved as local file paths."""
    url = "postgresql://gnucash:<redacted>@gnucash-db:5432/gnucash_data"

    assert _expand_path(url) == url


def test_resolve_book_path_preserves_env_database_url():
    """Container deployments pass the SQL book through GNUCASH_BOOK."""
    url = "postgresql://gnucash:<redacted>@gnucash-db:5432/gnucash_data"

    with patch.dict(os.environ, {"GNUCASH_BOOK": url}):
        assert resolve_book_path(None, {}) == url
