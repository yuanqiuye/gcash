import asyncio
import contextlib
import json
import os
from dataclasses import dataclass
from typing import Any, Callable

from gnucash_cli.auth import is_asgi_scope_authorized, resolve_mcp_http_api_key
from gnucash_cli.config import load_config
from gnucash_cli.services.accounts import create_account, list_accounts
from gnucash_cli.services.transactions import add_transaction_input, edit_transaction, list_account_transactions
from gnucash_cli.transaction_input import TransactionInput, build_transaction_input

ToolHandler = Callable[[str, dict[str, Any], dict[str, Any]], dict[str, Any]]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: Callable[[], dict[str, Any]]
    handler: ToolHandler
    mutates: bool = False

    def as_definition(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema(),
        }


def transaction_split_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "account_id": {
                "type": "string",
                "description": "Preferred stable account id returned by gnucash_list_accounts.",
            },
            "account": {
                "type": "string",
                "description": "Legacy account fullname or unique account name, e.g. Expenses:Food.",
            },
            "value": {"type": "string", "description": "Positive decimal value in transaction currency"},
            "currency": {"type": "string", "description": "Optional account currency, e.g. USD"},
            "quantity": {"type": "string", "description": "Optional positive account-currency quantity"},
        },
        "required": ["value"],
        "additionalProperties": False,
    }


def add_transaction_input_schema() -> dict[str, Any]:
    schema = TransactionInput.model_json_schema(by_alias=True)
    properties = schema.get("properties", {})
    properties["description"]["description"] = "Transaction description (e.g. Lunch)"
    properties["date"]["description"] = "Date in YYYY-MM-DD format"
    properties["debits"] = {
        **properties["debits"],
        "items": transaction_split_schema(),
        "description": "List of debit splits. Structured objects are preferred; legacy strings are still accepted.",
    }
    properties["credits"] = {
        **properties["credits"],
        "items": transaction_split_schema(),
        "description": "List of credit splits. Structured objects are preferred; legacy strings are still accepted.",
    }
    properties["notes"]["description"] = "Optional notes/memo"
    properties["currency"]["description"] = "Optional transaction currency, e.g. TWD"
    return {
        "type": "object",
        "properties": properties,
        "required": schema.get("required", []),
    }


def list_accounts_input_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "type": {"type": "string", "description": "Filter by account type (e.g. ASSET, EQUITY, EXPENSE)"}
        },
    }


def list_account_transactions_input_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "account_id": {
                "type": "string",
                "description": "Preferred stable account id returned by gnucash_list_accounts.",
            },
            "account": {"type": "string", "description": "Legacy account fullname or unique account name."},
            "limit": {
                "type": "integer",
                "minimum": 1,
                "maximum": 100,
                "default": 10,
                "description": "Maximum number of most recent transactions to return.",
            },
        },
        "additionalProperties": False,
    }


def create_account_input_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Name of the new account"},
            "type": {"type": "string", "description": "Account type (e.g. EXPENSE, BANK, ROOT)"},
            "parent_account_id": {
                "type": "string",
                "description": "Preferred stable parent account id returned by gnucash_list_accounts.",
            },
            "parent": {"type": "string", "description": "Legacy full name of the parent account (e.g. Expenses)"},
            "currency": {"type": "string", "description": "ISO 4217 currency code (e.g. TWD, USD)"},
            "description": {"type": "string", "description": "Description for the account"},
        },
        "required": ["name", "type"],
    }


def edit_transaction_input_schema() -> dict[str, Any]:
    split_items = transaction_split_schema()
    return {
        "type": "object",
        "properties": {
            "transaction_id": {
                "type": "string",
                "description": "Stable transaction id returned by gnucash_list_account_transactions.",
            },
            "description": {"type": "string", "description": "Optional replacement transaction description."},
            "date": {"type": "string", "description": "Optional replacement post date in YYYY-MM-DD format."},
            "notes": {"type": "string", "description": "Optional replacement notes. Use an empty string to clear."},
            "debits": {
                "type": "array",
                "items": split_items,
                "minItems": 1,
                "description": "Optional full replacement debit splits. Must be provided with credits.",
            },
            "credits": {
                "type": "array",
                "items": split_items,
                "minItems": 1,
                "description": "Optional full replacement credit splits. Must be provided with debits.",
            },
        },
        "required": ["transaction_id"],
        "additionalProperties": False,
    }


def mcp_tool_definitions(read_only: bool = False) -> list[dict[str, Any]]:
    return [spec.as_definition() for spec in iter_tool_specs(read_only=read_only)]


def iter_tool_specs(read_only: bool = False) -> list[ToolSpec]:
    if read_only:
        return [spec for spec in TOOL_SPECS if not spec.mutates]
    return list(TOOL_SPECS)


def _truthy(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def mcp_read_only_enabled(config: dict[str, Any]) -> bool:
    env_value = os.environ.get("GNUCASH_MCP_READ_ONLY")
    if env_value is not None:
        return _truthy(env_value)
    return _truthy(config.get("mcp_read_only", False))


def get_mcp_http_api_key(config: dict[str, Any]) -> str | None:
    return resolve_mcp_http_api_key(config)


def build_mcp_transaction_input(args: dict[str, Any]):
    return build_transaction_input(
        description=args["description"],
        debits=args["debits"],
        credits=args["credits"],
        tx_date=args.get("date"),
        tx_currency=args.get("currency"),
        notes=args.get("notes", ""),
    )


def _handle_add_transaction(book_path: str, config: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    tx_input = build_mcp_transaction_input(args)
    return add_transaction_input(
        book_path=book_path,
        tx_input=tx_input,
        config=config,
    )


def _handle_list_accounts(book_path: str, _config: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    return list_accounts(
        book_path=book_path,
        account_type=args.get("type"),
    )


def _handle_list_account_transactions(book_path: str, _config: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    return list_account_transactions(
        book_path=book_path,
        account_id_value=args.get("account_id"),
        account_fullname=args.get("account"),
        limit=args.get("limit", 10),
    )


def _handle_create_account(book_path: str, config: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    return create_account(
        book_path=book_path,
        name=args["name"],
        account_type=args["type"],
        parent_fullname=args.get("parent"),
        parent_account_id=args.get("parent_account_id"),
        currency_code=args.get("currency"),
        placeholder=False,
        description=args.get("description", ""),
        config=config,
    )


def _handle_edit_transaction(book_path: str, config: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    return edit_transaction(
        book_path=book_path,
        transaction_id=args["transaction_id"],
        description=args.get("description"),
        tx_date=args.get("date"),
        notes=args["notes"] if "notes" in args else None,
        debits=args.get("debits"),
        credits_=args.get("credits"),
        config=config,
    )


TOOL_SPECS = [
    ToolSpec(
        name="gnucash_add_transaction",
        description=(
            "Add a new transaction to the GnuCash book. Requires balanced debit and credit splits. "
            "Automatically backs up the database before modification."
        ),
        input_schema=add_transaction_input_schema,
        handler=_handle_add_transaction,
        mutates=True,
    ),
    ToolSpec(
        name="gnucash_list_accounts",
        description="List all accounts in the GnuCash book. Returns a tree structure.",
        input_schema=list_accounts_input_schema,
        handler=_handle_list_accounts,
    ),
    ToolSpec(
        name="gnucash_list_account_transactions",
        description=(
            "List the most recent transactions touching a specific account. "
            "Returns transaction_id values for later edits."
        ),
        input_schema=list_account_transactions_input_schema,
        handler=_handle_list_account_transactions,
    ),
    ToolSpec(
        name="gnucash_edit_transaction",
        description=(
            "Edit a specific transaction by transaction_id. Can update description, date, notes, "
            "or replace all splits with balanced debit/credit splits. Automatically backs up first."
        ),
        input_schema=edit_transaction_input_schema,
        handler=_handle_edit_transaction,
        mutates=True,
    ),
    ToolSpec(
        name="gnucash_create_account",
        description="Create a new account in the GnuCash book. Automatically backs up the database before modification.",
        input_schema=create_account_input_schema,
        handler=_handle_create_account,
        mutates=True,
    ),
]
TOOL_BY_NAME = {spec.name: spec for spec in TOOL_SPECS}
MUTATING_TOOLS = {spec.name for spec in TOOL_SPECS if spec.mutates}


def _mcp_json_text(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False)


def create_mcp_server(config: dict[str, Any] | None = None):
    from mcp.server import Server
    from mcp.types import CallToolResult, TextContent, Tool

    effective_config = config if config is not None else load_config()
    read_only = mcp_read_only_enabled(effective_config)
    app = Server("gnucash-mcp-agent")

    @app.list_tools()
    async def handle_list_tools() -> list[Tool]:
        return [Tool(**definition) for definition in mcp_tool_definitions(read_only=read_only)]

    @app.call_tool()
    async def handle_call_tool(name: str, arguments: dict[str, Any] | None) -> CallToolResult:
        spec = TOOL_BY_NAME.get(name)
        if spec is None:
            return _mcp_error_result(f"Unknown Tool: {name}")

        if read_only and spec.mutates:
            return _mcp_json_error_result("MCP server is running in read-only mode.")

        book_path = os.environ.get("GNUCASH_BOOK") or effective_config.get("default_book")
        if not book_path:
            return _mcp_json_error_result("GNUCASH_BOOK context missing. Server not configured properly.")

        try:
            result = spec.handler(book_path, effective_config, arguments or {})
            return CallToolResult(content=[TextContent(type="text", text=_mcp_json_text(result))])
        except Exception as e:
            return _mcp_json_error_result(str(e))

    return app


def _mcp_error_result(message: str):
    from mcp.types import CallToolResult, TextContent

    return CallToolResult(
        isError=True,
        content=[TextContent(type="text", text=message)],
    )


def _mcp_json_error_result(message: str):
    from mcp.types import CallToolResult, TextContent

    return CallToolResult(
        isError=True,
        content=[TextContent(type="text", text=_mcp_json_text({"status": "error", "message": message}))],
    )


def _exit_missing_dependency(package: str, extra: str):
    import sys

    print(
        f"Error: {package} library not found. Install dependencies with `uv sync --extra {extra}` or `uv sync`.",
        file=sys.stderr,
    )
    sys.exit(1)


def start_mcp_stdio_server():
    """Starts the MCP server using standard input/output."""
    try:
        from mcp.server.stdio import stdio_server
        app = create_mcp_server()
    except ImportError:
        _exit_missing_dependency("mcp", "mcp")

    async def run():
        async with stdio_server() as (read_stream, write_stream):
            await app.run(read_stream, write_stream, app.create_initialization_options())

    asyncio.run(run())


def _is_http_authorized(scope, expected_key: str | None) -> bool:
    return is_asgi_scope_authorized(scope, expected_key)


def create_mcp_http_app(config: dict[str, Any] | None = None, path: str = "/mcp"):
    try:
        from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
        from starlette.applications import Starlette
        from starlette.responses import PlainTextResponse
        from starlette.routing import Mount
    except ImportError:
        _exit_missing_dependency("mcp HTTP", "mcp")

    effective_config = config if config is not None else load_config()
    api_key = get_mcp_http_api_key(effective_config)
    mcp_app = create_mcp_server(config=effective_config)
    session_manager = StreamableHTTPSessionManager(mcp_app, stateless=True)
    backup_config = dict(effective_config)
    if api_key and not backup_config.get("api_key"):
        backup_config["api_key"] = api_key

    from gnucash_cli.server import create_app as create_backup_app

    backup_app = create_backup_app(
        config=backup_config,
        book_path=os.environ.get("GNUCASH_BOOK") or effective_config.get("default_book"),
    )

    class MCPHttpASGIApp:
        async def __call__(self, scope, receive, send):
            if not _is_http_authorized(scope, api_key):
                response = PlainTextResponse("Invalid or missing API key", status_code=401)
                await response(scope, receive, send)
                return
            await session_manager.handle_request(scope, receive, send)

    @contextlib.asynccontextmanager
    async def lifespan(_app):
        async with session_manager.run():
            yield

    mount_path = path if path.startswith("/") else f"/{path}"
    return Starlette(
        routes=[
            Mount(mount_path, app=MCPHttpASGIApp()),
            Mount("/", app=backup_app),
        ],
        lifespan=lifespan,
    )


def start_mcp_http_server(host: str = "127.0.0.1", port: int = 8765, path: str = "/mcp"):
    """Starts the MCP server over Streamable HTTP."""
    try:
        import uvicorn
    except ImportError:
        _exit_missing_dependency("uvicorn", "server")

    uvicorn.run(create_mcp_http_app(path=path), host=host, port=port, log_level="info")
