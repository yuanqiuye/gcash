"""gcash CLI - GnuCash bookkeeping tool for AI agent automation."""

import os
import sys
import warnings

# Fix: click 8.x on Windows hangs with non-UTF-8 console encoding when
# processing CJK characters. Force UTF-8 on stdout/stderr/stdin.
if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stdin, "reconfigure"):
        sys.stdin.reconfigure(encoding="utf-8", errors="replace")

# Suppress noisy SQLAlchemy warnings from piecash
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", message=".*SAWarning.*")
warnings.filterwarnings("ignore", message=".*TypeDecorator.*")

import click

from gnucash_cli.config import load_config
from gnucash_cli.commands.accounts import accounts_group
from gnucash_cli.commands.transactions import transactions_group
from gnucash_cli.commands.currencies import currencies_group
from gnucash_cli.commands.db import db_group
from gnucash_cli.utils import setup_logging


@click.group()
@click.option("--book", "-b", default=None, envvar="GNUCASH_BOOK",
              help="Path to GnuCash book file. Can also be set via GNUCASH_BOOK env var or config.yaml.")
@click.option("--config", "config_path", default=None,
              help="Path to config file. Defaults to ~/.gnucash-cli/config.yaml.")
@click.option("-v", "--verbose", is_flag=True,
              help="Enable verbose logging output.")
@click.version_option(package_name="gnucash-cli")
@click.pass_context
def cli(ctx, book, config_path, verbose):
    """gcash - GnuCash CLI for automated bookkeeping.

    A command-line tool for managing GnuCash books, designed for AI agent integration.
    Supports account management, transaction recording (with multi-currency),
    and exchange rate updates.

    \b
    Configuration priority:
      1. CLI arguments (--book, --config)
      2. Environment variables (GNUCASH_BOOK)
      3. Config file (~/.gnucash-cli/config.yaml)
    """
    setup_logging(level="DEBUG" if verbose else "WARNING")
    ctx.ensure_object(dict)
    ctx.obj["config"] = load_config(config_path)
    ctx.obj["book"] = book


cli.add_command(accounts_group)
cli.add_command(transactions_group)
cli.add_command(currencies_group)
cli.add_command(db_group)

@cli.command("serve")
@click.option("--host", default="127.0.0.1", help="Host to bind the server to.")
@click.option("--port", default=8000, type=int, help="Port to bind the server to.")
@click.pass_context
def serve(ctx, host, port):
    """Start local API server to receive Agent requests (Option B)."""
    import uvicorn
    from gnucash_cli.config import resolve_book_path
    from gnucash_cli.utils import console
    
    # Export book to env for the server to pick up
    book_path = resolve_book_path(ctx.obj.get("book"), ctx.obj["config"])
    os.environ["GNUCASH_BOOK"] = book_path
    
    console.print(f"[green]Starting Agent API server on http://{host}:{port}[/green]")
    console.print(f"[dim]Serving book: {book_path}[/dim]")
    console.print("[yellow]Press Ctrl+C to stop the server[/yellow]")
    
    uvicorn.run("gnucash_cli.server:app", host=host, port=port, log_level="info")

@cli.command("mcp")
@click.pass_context
def mcp(ctx):
    """Start the MCP standard I/O server for Agent integration."""
    from gnucash_cli.config import resolve_book_path
    from gnucash_cli.mcp_server import start_mcp_stdio_server
    
    # Export book for the subprocesses called by the MCP tools
    book_path = resolve_book_path(ctx.obj.get("book"), ctx.obj["config"])
    os.environ["GNUCASH_BOOK"] = book_path
    
    start_mcp_stdio_server()

def main():
    """Entry point that ensures proper encoding on Windows."""
    # Fix: click 8.x on Windows hangs with non-UTF-8 console encoding when
    # processing CJK characters. We must spawn a new process with PYTHONUTF8=1
    # because setting it inside the script is too late for the executable wrapper.
    if sys.platform == "win32" and os.environ.get("PYTHONUTF8") != "1":
        import subprocess
        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"
        # Instead of calling sys.argv (which is the gcash.exe wrapper that hangs
        # on Chinese arguments over pipes), invoke python directly.
        cmd = [sys.executable, "-m", "gnucash_cli.cli"] + sys.argv[1:]
        sys.exit(subprocess.run(cmd, env=env).returncode)

    cli(standalone_mode=True)


if __name__ == "__main__":
    main()
