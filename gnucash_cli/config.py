"""Configuration management for gcash CLI."""

import os
from pathlib import Path
from typing import Optional

import yaml


DEFAULT_CONFIG_DIR = Path.home() / ".gnucash-cli"
DEFAULT_CONFIG_FILE = DEFAULT_CONFIG_DIR / "config.yaml"

_DEFAULTS = {
    "default_currency": "TWD",
    "default_book": None,
    "api_key": None,
}


def load_config(config_path: Optional[str] = None) -> dict:
    """Load configuration from YAML file.

    Priority: explicit config_path > ~/.gnucash-cli/config.yaml > defaults
    """
    config = dict(_DEFAULTS)

    path = Path(config_path) if config_path else DEFAULT_CONFIG_FILE

    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            user_config = yaml.safe_load(f) or {}
            config.update(user_config)

    return config


def resolve_book_path(
    cli_book: Optional[str],
    config: dict,
) -> str:
    """Resolve the GnuCash book path.

    Priority: CLI --book arg > GNUCASH_BOOK env var > config default_book
    """
    if cli_book:
        return _expand_path(cli_book)

    env_book = os.environ.get("GNUCASH_BOOK")
    if env_book:
        return _expand_path(env_book)

    config_book = config.get("default_book")
    if config_book:
        return _expand_path(config_book)

    raise click_missing_book_error()


def click_missing_book_error():
    """Return a clear error when no book path is specified."""
    import click

    return click.UsageError(
        "No GnuCash book specified. Use one of:\n"
        "  1. --book <path>  (CLI argument)\n"
        "  2. GNUCASH_BOOK=<path>  (environment variable)\n"
        "  3. default_book: <path>  (in ~/.gnucash-cli/config.yaml)"
    )


def _expand_path(path: str) -> str:
    """Expand ~ and return absolute path."""
    return str(Path(path).expanduser().resolve())
