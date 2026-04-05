"""Database and Backup commands."""

import logging
import os
import glob
import subprocess
from datetime import datetime

import click

from gnucash_cli.config import resolve_book_path
from gnucash_cli.utils import console, error, success, logger

@click.group("db")
def db_group():
    """Database administration and backup/restore."""
    pass

def _get_backup_dir():
    dir_path = os.path.join(os.getcwd(), ".backups")
    os.makedirs(dir_path, exist_ok=True)
    return dir_path

def execute_backup(book_path: str, action_name: str = "manual"):
    """Execute a backup depending on the database backend.
    
    Supports PostgreSQL via pg_dump and standard SQLite copy.
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = _get_backup_dir()
    
    if book_path.startswith("postgresql://") or book_path.startswith("postgres://"):
        backup_file = os.path.join(backup_dir, f"pg_backup_{action_name}_{timestamp}.sql")
        # --clean drops objects before recreating them, ideal for full restore
        # -F p is plain text sql
        cmd = ["pg_dump", book_path, "--clean", "--if-exists", "-F", "p", "-f", backup_file]
        logger.info("Executing PostgreSQL backup: %s", backup_file)
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                logger.error("PostgreSQL backup failed (exit code %d): %s", result.returncode, result.stderr)
                error(f"PostgreSQL backup failed: {result.stderr}")
                return None
            logger.info("PostgreSQL backup completed: %s", backup_file)
            return backup_file
        except FileNotFoundError:
            logger.error("pg_dump not found in PATH")
            error("pg_dump not found! Ensure postgresql-client is installed in your Docker image.")
            return None
    elif book_path.endswith(".gnucash") or book_path.endswith(".sqlite") or "://" not in book_path:
        # SQLite fallback fallback for local testing
        import shutil
        backup_file = os.path.join(backup_dir, f"sqlite_backup_{action_name}_{timestamp}.gnucash")
        logger.info("Executing SQLite backup: %s -> %s", book_path, backup_file)
        try:
            shutil.copy2(book_path, backup_file)
            logger.info("SQLite backup completed: %s", backup_file)
            return backup_file
        except Exception as e:
            logger.error("SQLite backup failed: %s", e)
            error(f"SQLite backup failed: {e}")
            return None
    else:
        logger.error("Unsupported database format for automatic backup: %s", book_path)
        error(f"Unsupported database format for automatic backup: {book_path}")
        return None

def auto_backup_if_needed(book_path: str, no_auto_backup: bool, action_name: str):
    """Automatically backup databases before destructive actions.
    
    Supports both PostgreSQL and SQLite (.gnucash) backends.
    """
    if no_auto_backup:
        return
    
    is_postgres = book_path.startswith("postgresql://") or book_path.startswith("postgres://")
    is_sqlite = book_path.endswith(".gnucash") or book_path.endswith(".sqlite") or "://" not in book_path
    
    if is_postgres or is_sqlite:
        backup_file = execute_backup(book_path, action_name=action_name)
        if not backup_file:
            error(f"Auto-backup ({action_name}) failed! Aborting to ensure safety.")
            raise SystemExit(1)

def execute_restore(book_path: str, backup_file: str):
    """Restore from a backup file."""
    if not os.path.exists(backup_file):
        logger.error("Backup file not found: %s", backup_file)
        error(f"Backup file not found: {backup_file}")
        return False
        
    logger.warning("Restoring database from: %s -> %s", backup_file, book_path)
    
    if book_path.startswith("postgresql://") or book_path.startswith("postgres://"):
        cmd = ["psql", book_path, "-f", backup_file]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                logger.error("PostgreSQL restore failed: %s", result.stderr)
                error(f"PostgreSQL restore failed: {result.stderr}")
                return False
            logger.info("PostgreSQL restore completed from: %s", backup_file)
            return True
        except FileNotFoundError:
            logger.error("psql not found in PATH")
            error("psql not found! Ensure postgresql-client is installed.")
            return False
    else:
        # SQLite restore
        import shutil
        try:
            shutil.copy2(backup_file, book_path)
            logger.info("SQLite restore completed from: %s", backup_file)
            return True
        except Exception as e:
            logger.error("SQLite restore failed: %s", e)
            error(f"SQLite restore failed: {e}")
            return False

@db_group.command("backup")
@click.pass_context
def backup(ctx):
    """Manually trigger a snapshot backup of the current database."""
    config = ctx.obj["config"]
    book_path = resolve_book_path(ctx.obj.get("book"), config)
    
    console.print(f"Creating backup for: [cyan]{book_path}[/cyan]...")
    result_path = execute_backup(book_path, action_name="manual")
    
    if result_path:
        success(f"Backup created successfully: {result_path}")
    else:
        raise SystemExit(1)

def get_backups_list():
    """Return a detailed list of available backups."""
    backup_dir = _get_backup_dir()
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

@db_group.command("list-backups")
def list_backups():
    """List available backups in the .backups directory."""
    backups = get_backups_list()
    
    if not backups:
        console.print("[dim]No backups found in .backups/[/dim]")
        return
        
    from rich.table import Table
    table = Table(title="Available Backups")
    table.add_column("Filename", style="cyan")
    table.add_column("Size (Bytes)", style="dim")
    table.add_column("Time", style="white")
    
    for b in backups:
        table.add_row(b["filename"], f"{b['size']:,}", b["time"])
        
    console.print(table)
    console.print("\nTo restore, run: [bold yellow]gcash db restore --file .backups/<filename>[/bold yellow]")

@db_group.command("restore")
@click.option("--file", "backup_file", required=True, type=click.Path(exists=True),
              help="Path to the backup file to restore from.")
@click.option("--yes", is_flag=True, help="Skip confirmation prompt.")
@click.pass_context
def restore(ctx, backup_file, yes):
    """Restore the database from a backup, overwriting current data.
    
    WARNING: For PostgreSQL, this will drop and recreate tables based on the backup!
    """
    config = ctx.obj["config"]
    book_path = resolve_book_path(ctx.obj.get("book"), config)
    
    if not yes:
        click.confirm(f"WARNING: This will completely overwrite '{book_path}' with data from '{backup_file}'. Continue?", abort=True)
        
    console.print(f"Restoring database from [cyan]{backup_file}[/cyan]...")
    if execute_restore(book_path, backup_file):
        success("Database successfully restored!")
    else:
        raise SystemExit(1)
