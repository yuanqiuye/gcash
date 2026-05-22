"""CLI-only safety helpers."""

import click


def resolve_no_auto_backup(config: dict, requested: bool) -> bool:
    """Gate backup bypasses behind an explicit unsafe config opt-in."""
    if not requested:
        return False

    if config.get("allow_unsafe_no_auto_backup") is True:
        return True

    raise click.UsageError(
        "Refusing to skip the automatic safety backup. "
        "Set allow_unsafe_no_auto_backup: true in config.yaml and use "
        "--unsafe-no-auto-backup if you really want this."
    )
