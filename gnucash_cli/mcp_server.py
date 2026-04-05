import os
import json
import asyncio
from typing import Any
import warnings

import click

from gnucash_cli.service import add_transaction, list_accounts, create_account
from gnucash_cli.config import load_config

def call_gcash_cli(args: list[str]) -> str:
    """Helper to call the gcash CLI securely and grab JSON output.
    
    .. deprecated:: 0.2.0
       This function is no longer used by the MCP server and is kept for backwards compatibility only.
    """
    warnings.warn("call_gcash_cli is deprecated and will be removed in a future release.", DeprecationWarning)
    import subprocess
    book_path = os.environ.get("GNUCASH_BOOK")
    if not book_path:
        return json.dumps({"status": "error", "message": "GNUCASH_BOOK context missing. Server not configured properly."})
        
    cmd = ["gcash", "-b", book_path] + args + ["--format", "json"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
        if result.returncode != 0:
            return json.dumps({
                "status": "error",
                "message": "CLI execution failed",
                "stderr": result.stderr,
                "stdout": result.stdout
            })
        return result.stdout
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)})

def start_mcp_stdio_server():
    """Starts the MCP server using standard input/output."""
    try:
        from mcp.server import Server
        from mcp.server.stdio import stdio_server
        from mcp.types import Tool, TextContent, CallToolResult
    except ImportError:
        import sys
        print("Error: mcp library not found. Install with `pip install mcp`.", file=sys.stderr)
        sys.exit(1)

    app = Server("gnucash-mcp-agent")
    
    # Load config once for the server
    config = load_config()

    @app.list_tools()
    async def handle_list_tools() -> list[Tool]:
        return [
            Tool(
                name="gnucash_add_transaction",
                description="Add a new transaction to the GnuCash book. Requires balanced debit and credit splits. Automatically backs up the database before modification.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "description": {"type": "string", "description": "Transaction description (e.g. Lunch)"},
                        "date": {"type": "string", "description": "Date in YYYY-MM-DD format"},
                        "debits": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of debit splits. Format: 'Account:Name amount [CURRENCY [quantity]]'. e.g. 'Expenses:Food 150'"
                        },
                        "credits": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of credit splits. Format: 'Account:Name amount [CURRENCY [quantity]]'. e.g. 'Assets:Cash 150'"
                        },
                        "notes": {"type": "string", "description": "Optional notes/memo"}
                    },
                    "required": ["description", "debits", "credits"]
                }
            ),
            Tool(
                name="gnucash_list_accounts",
                description="List all accounts in the GnuCash book. Returns a tree structure.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "type": {"type": "string", "description": "Filter by account type (e.g. ASSET, EQUITY, EXPENSE)"}
                    }
                }
            ),
            Tool(
                name="gnucash_create_account",
                description="Create a new account in the GnuCash book. Automatically backs up the database before modification.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Name of the new account"},
                        "type": {"type": "string", "description": "Account type (e.g. EXPENSE, BANK, ROOT)"},
                        "parent": {"type": "string", "description": "Full name of the parent account (e.g. Expenses)"},
                        "currency": {"type": "string", "description": "ISO 4217 currency code (e.g. TWD, USD)"},
                        "description": {"type": "string", "description": "Description for the account"}
                    },
                    "required": ["name", "type", "parent"]
                }
            )
        ]

    @app.call_tool()
    async def handle_call_tool(name: str, arguments: dict[str, Any] | None) -> CallToolResult:
        book_path = os.environ.get("GNUCASH_BOOK") or config.get("default_book")
        if not book_path:
            return CallToolResult(
                isError=True,
                content=[TextContent(type="text", text=json.dumps({"status": "error", "message": "GNUCASH_BOOK context missing. Server not configured properly."}))]
            )

        args = arguments or {}
        try:
            if name == "gnucash_add_transaction":
                result = add_transaction(
                    book_path=book_path,
                    description=args["description"],
                    debits=args["debits"],
                    credits_=args["credits"],
                    tx_date=args.get("date"),
                    tx_currency=None,
                    notes=args.get("notes", ""),
                    config=config
                )
                return CallToolResult(content=[TextContent(type="text", text=json.dumps(result))])
                
            elif name == "gnucash_list_accounts":
                result = list_accounts(
                    book_path=book_path,
                    account_type=args.get("type")
                )
                return CallToolResult(content=[TextContent(type="text", text=json.dumps(result))])
                
            elif name == "gnucash_create_account":
                result = create_account(
                    book_path=book_path,
                    name=args["name"],
                    account_type=args["type"],
                    parent_fullname=args["parent"],
                    currency_code=args.get("currency"),
                    placeholder=False,
                    description=args.get("description", ""),
                    config=config
                )
                return CallToolResult(content=[TextContent(type="text", text=json.dumps(result))])
                
            else:
                return CallToolResult(
                    isError=True,
                    content=[TextContent(type="text", text=f"Unknown Tool: {name}")]
                )
        except Exception as e:
            return CallToolResult(
                isError=True,
                content=[TextContent(type="text", text=json.dumps({"status": "error", "message": str(e)}))]
            )

    async def run():
        async with stdio_server() as (read_stream, write_stream):
            await app.run(read_stream, write_stream, app.create_initialization_options())

    asyncio.run(run())
