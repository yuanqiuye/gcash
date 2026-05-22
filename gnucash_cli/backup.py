"""Backup and restore operations for GnuCash books."""

import glob
import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from gnucash_cli.book_access import ensure_book_unlocked, ensure_book_unlocked_for_write
from gnucash_cli.book_backend import is_postgres_book, is_sqlite_book, postgres_env
from gnucash_cli.config import DEFAULT_CONFIG_DIR, load_config
from gnucash_cli.exceptions import BackupError
from gnucash_cli.locks import book_mutation_lock
from gnucash_cli.logging_config import logger


def _get_backup_dir(book_path: str | None = None, config: dict | None = None) -> str:
    effective_config = config if config is not None else load_config()
    configured_dir = os.environ.get("GNUCASH_BACKUP_DIR") or effective_config.get("backup_dir")

    if configured_dir:
        backup_dir = Path(configured_dir).expanduser()
    elif book_path and is_sqlite_book(book_path):
        backup_dir = Path(book_path).expanduser().resolve().parent / ".backups"
    else:
        backup_dir = DEFAULT_CONFIG_DIR / "backups"

    backup_dir.mkdir(parents=True, exist_ok=True)
    return str(backup_dir.resolve())


def resolve_backup_file(filename: str, book_path: str | None = None, config: dict | None = None) -> str:
    """Resolve a user-provided backup filename within the configured backup directory."""
    safe_filename = os.path.basename(filename)
    return os.path.join(_get_backup_dir(book_path=book_path, config=config), safe_filename)


def _execute_backup_unlocked(book_path: str, action_name: str = "manual", config: dict | None = None):
    """Execute a backup while the caller already owns the mutation lock."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    backup_dir = _get_backup_dir(book_path=book_path, config=config)

    if is_postgres_book(book_path):
        backup_file = os.path.join(backup_dir, f"pg_backup_{action_name}_{timestamp}.sql")
        cmd = [
            "pg_dump",
            "--clean",
            "--if-exists",
            "--single-transaction",
            "-F",
            "p",
            "-f",
            backup_file,
        ]
        logger.info("Executing PostgreSQL backup: %s", backup_file)

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, env=postgres_env(book_path))
        except FileNotFoundError as e:
            logger.error("pg_dump not found in PATH")
            raise BackupError("pg_dump not found. Ensure postgresql-client is installed.") from e

        if result.returncode != 0:
            logger.error("PostgreSQL backup failed (exit code %d): %s", result.returncode, result.stderr)
            raise BackupError(f"PostgreSQL backup failed: {result.stderr}")

        logger.info("PostgreSQL backup completed: %s", backup_file)
        return backup_file

    if is_sqlite_book(book_path):
        ensure_book_unlocked(book_path)
        backup_file = os.path.join(backup_dir, f"sqlite_backup_{action_name}_{timestamp}.gnucash")
        tmp_backup_file = f"{backup_file}.tmp"
        logger.info("Executing SQLite backup: %s -> %s", book_path, backup_file)
        try:
            shutil.copy2(book_path, tmp_backup_file)
            os.replace(tmp_backup_file, backup_file)
        except Exception as e:
            if os.path.exists(tmp_backup_file):
                os.remove(tmp_backup_file)
            logger.error("SQLite backup failed: %s", e)
            raise BackupError(f"SQLite backup failed: {e}") from e

        logger.info("SQLite backup completed: %s", backup_file)
        return backup_file

    logger.error("Unsupported database format for automatic backup: %s", book_path)
    raise BackupError(f"Unsupported database format for automatic backup: {book_path}")


def execute_backup(book_path: str, action_name: str = "manual", config: dict | None = None):
    """Execute a serialized backup depending on the database backend."""
    with book_mutation_lock(book_path, config=config):
        return _execute_backup_unlocked(book_path, action_name=action_name, config=config)


def auto_backup_if_needed(
    book_path: str,
    no_auto_backup: bool,
    action_name: str,
    config: dict | None = None,
):
    """Backup before destructive actions while the caller owns the mutation lock."""
    ensure_book_unlocked_for_write(book_path)
    if no_auto_backup:
        return
    _execute_backup_unlocked(book_path, action_name=action_name, config=config)


def execute_restore(book_path: str, backup_file: str, config: dict | None = None):
    """Restore from a backup file."""
    if not os.path.exists(backup_file):
        logger.error("Backup file not found: %s", backup_file)
        raise BackupError(f"Backup file not found: {backup_file}")

    ensure_book_unlocked_for_write(book_path)
    logger.warning("Restoring database from: %s -> %s", backup_file, book_path)

    with book_mutation_lock(book_path, config=config):
        if is_postgres_book(book_path):
            cmd = ["psql", "-f", backup_file]
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, env=postgres_env(book_path))
            except FileNotFoundError as e:
                logger.error("psql not found in PATH")
                raise BackupError("psql not found. Ensure postgresql-client is installed.") from e

            if result.returncode != 0:
                logger.error("PostgreSQL restore failed: %s", result.stderr)
                raise BackupError(f"PostgreSQL restore failed: {result.stderr}")

            logger.info("PostgreSQL restore completed from: %s", backup_file)
            return True

        if is_sqlite_book(book_path):
            ensure_book_unlocked(book_path)
            tmp_restore_file = f"{book_path}.restore_tmp"
            try:
                shutil.copy2(backup_file, tmp_restore_file)
                os.replace(tmp_restore_file, book_path)
            except Exception as e:
                if os.path.exists(tmp_restore_file):
                    os.remove(tmp_restore_file)
                logger.error("SQLite restore failed: %s", e)
                raise BackupError(f"SQLite restore failed: {e}") from e

            logger.info("SQLite restore completed from: %s", backup_file)
            return True

        raise BackupError(f"Unsupported database format for restore: {book_path}")


def get_backups_list(book_path: str | None = None, config: dict | None = None):
    """Return a detailed list of available backups."""
    backup_dir = _get_backup_dir(book_path=book_path, config=config)
    files = sorted(glob.glob(os.path.join(backup_dir, "*")), reverse=True)

    results = []
    for f in files:
        name = os.path.basename(f)
        size = os.path.getsize(f)
        mtime = datetime.fromtimestamp(os.path.getmtime(f)).strftime("%Y-%m-%d %H:%M:%S")
        results.append({
            "filename": name,
            "path": f,
            "size": size,
            "time": mtime,
        })
    return results
