"""Database and Backup commands."""

import click

from gnucash_cli.backup import execute_backup, execute_restore, get_backups_list
from gnucash_cli.config import resolve_book_path
from gnucash_cli.exceptions import GCashError
from gnucash_cli.presentation import console, error, success


@click.group("db")
def db_group():
    """Database administration and backup/restore."""
    pass

@db_group.command("backup")
@click.pass_context
def backup(ctx):
    """Manually trigger a snapshot backup of the current database."""
    config = ctx.obj["config"]
    book_path = resolve_book_path(ctx.obj.get("book"), config)
    
    console.print(f"Creating backup for: [cyan]{book_path}[/cyan]...")
    try:
        result_path = execute_backup(book_path, action_name="manual", config=config)
    except GCashError as e:
        error(f"Backup failed: {e}")
        raise SystemExit(1)
    
    if result_path:
        success(f"Backup created successfully: {result_path}")
    else:
        raise SystemExit(1)

@db_group.command("list-backups")
@click.pass_context
def list_backups(ctx):
    """List available backups for the current book."""
    config = ctx.obj["config"]
    book_path = resolve_book_path(ctx.obj.get("book"), config)
    backups = get_backups_list(book_path=book_path, config=config)
    
    if not backups:
        console.print("[dim]No backups found.[/dim]")
        return
        
    from rich.table import Table
    table = Table(title="Available Backups")
    table.add_column("Filename", style="cyan")
    table.add_column("Size (Bytes)", style="dim")
    table.add_column("Time", style="white")
    
    for b in backups:
        table.add_row(b["filename"], f"{b['size']:,}", b["time"])
        
    console.print(table)
    console.print("\nTo restore, run: [bold yellow]gcash db restore --file <backup-file>[/bold yellow]")

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
    try:
        restored = execute_restore(book_path, backup_file, config=config)
    except GCashError as e:
        error(f"Restore failed: {e}")
        raise SystemExit(1)

    if restored:
        success("Database successfully restored!")
    else:
        raise SystemExit(1)
