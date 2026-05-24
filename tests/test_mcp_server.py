import gnucash_cli.mcp_server as mcp_server
from gnucash_cli.mcp_server import (
    TOOL_SPECS,
    _is_http_authorized,
    add_transaction_input_schema,
    build_mcp_transaction_input,
    create_mcp_http_app,
    get_mcp_http_api_key,
    iter_tool_specs,
    mcp_read_only_enabled,
    mcp_tool_definitions,
)
from gnucash_cli.transaction_input import TransactionInput


def test_mcp_add_transaction_schema_accepts_structured_and_legacy_splits():
    schema = add_transaction_input_schema()

    debits = schema["properties"]["debits"]
    credits = schema["properties"]["credits"]

    assert debits["minItems"] == 1
    assert credits["minItems"] == 1
    assert debits["items"]["type"] == "object"
    assert debits["items"]["required"] == ["value"]
    assert "account_id" in debits["items"]["properties"]
    assert debits["items"]["additionalProperties"] is False


def test_mcp_build_transaction_input_normalizes_structured_args():
    tx_input = build_mcp_transaction_input(
        {
            "description": "Lunch",
            "date": "2026-05-11",
            "debits": [{"account": "Expenses:Dining", "value": "150"}],
            "credits": ["Assets:Cash 150"],
            "currency": "twd",
            "notes": "memo",
        }
    )

    assert tx_input.description == "Lunch"
    assert tx_input.currency == "TWD"
    assert tx_input.debits[0].account_fullname == "Expenses:Dining"
    assert tx_input.credits[0].account_fullname == "Assets:Cash"


def test_mcp_build_transaction_input_accepts_account_id_splits():
    tx_input = build_mcp_transaction_input(
        {
            "description": "Lunch",
            "debits": [{"account_id": "expense-guid", "value": "150"}],
            "credits": [{"account_id": "cash-guid", "value": "150"}],
        }
    )

    assert tx_input.debits[0].account_id == "expense-guid"
    assert tx_input.debits[0].account_fullname is None
    assert tx_input.credits[0].account_id == "cash-guid"


def test_mcp_server_has_no_deprecated_cli_subprocess_helper():
    assert not hasattr(mcp_server, "call_gcash_cli")


def test_mcp_read_only_tool_definitions_expose_only_read_tools():
    tools = mcp_tool_definitions(read_only=True)

    assert [tool["name"] for tool in tools] == [
        "gnucash_list_accounts",
        "gnucash_list_account_transactions",
    ]
    assert [spec.name for spec in iter_tool_specs(read_only=True)] == [
        "gnucash_list_accounts",
        "gnucash_list_account_transactions",
    ]


def test_mcp_read_write_tool_definitions_include_mutations():
    tools = mcp_tool_definitions(read_only=False)

    assert [tool["name"] for tool in tools] == [
        "gnucash_add_transaction",
        "gnucash_list_accounts",
        "gnucash_list_account_transactions",
        "gnucash_edit_transaction",
        "gnucash_create_account",
    ]


def test_mcp_create_account_schema_accepts_parent_account_id():
    schema = mcp_server.create_account_input_schema()

    assert "parent_account_id" in schema["properties"]
    assert schema["required"] == ["name", "type"]
    assert "anyOf" not in schema


def test_mcp_list_account_transactions_schema_requires_account_reference():
    schema = mcp_server.list_account_transactions_input_schema()

    assert "anyOf" not in schema
    assert "account_id" in schema["properties"]
    assert "account" in schema["properties"]
    assert schema["properties"]["limit"]["maximum"] == 100


def test_mcp_edit_transaction_schema_exposes_full_split_replacement():
    schema = mcp_server.edit_transaction_input_schema()

    assert schema["required"] == ["transaction_id"]
    assert "debits" in schema["properties"]
    assert "credits" in schema["properties"]
    assert schema["properties"]["debits"]["items"]["properties"]["account_id"]["type"] == "string"


def test_mcp_read_only_can_be_enabled_by_config_or_env(monkeypatch):
    monkeypatch.delenv("GNUCASH_MCP_READ_ONLY", raising=False)
    assert mcp_read_only_enabled({"mcp_read_only": True}) is True
    assert mcp_read_only_enabled({"mcp_read_only": False}) is False

    monkeypatch.setenv("GNUCASH_MCP_READ_ONLY", "1")
    assert mcp_read_only_enabled({"mcp_read_only": False}) is True


def test_mcp_http_api_key_prefers_specific_env(monkeypatch):
    monkeypatch.setenv("GNUCASH_API_KEY", "general")
    monkeypatch.setenv("GNUCASH_MCP_HTTP_API_KEY", "specific")

    assert get_mcp_http_api_key({"api_key": "config"}) == "specific"


def test_mcp_http_api_key_falls_back_to_config(monkeypatch):
    monkeypatch.delenv("GNUCASH_API_KEY", raising=False)
    monkeypatch.delenv("GNUCASH_MCP_HTTP_API_KEY", raising=False)

    assert get_mcp_http_api_key({"mcp_http_api_key": "mcp-config", "api_key": "config"}) == "mcp-config"


def test_mcp_http_auth_accepts_x_api_key_header():
    scope = {"headers": [(b"x-api-key", b"secret")]}

    assert _is_http_authorized(scope, "secret") is True
    assert _is_http_authorized(scope, "wrong") is False


def test_mcp_http_auth_accepts_bearer_header():
    scope = {"headers": [(b"authorization", b"Bearer secret")]}

    assert _is_http_authorized(scope, "secret") is True
    assert _is_http_authorized(scope, "wrong") is False


def test_mcp_http_auth_allows_missing_expected_key_for_loopback_dev():
    assert _is_http_authorized({"headers": []}, None) is True


def test_mcp_transaction_schema_tracks_model_required_fields():
    schema = add_transaction_input_schema()
    model_schema = TransactionInput.model_json_schema(by_alias=True)

    assert schema["required"] == model_schema["required"]


def test_mcp_tool_registry_is_single_source_for_mutating_tools():
    mutating_names = {spec.name for spec in TOOL_SPECS if spec.mutates}

    assert mutating_names == mcp_server.MUTATING_TOOLS
    assert set(mcp_server.TOOL_BY_NAME) == {spec.name for spec in TOOL_SPECS}


def test_mcp_tool_descriptions_guide_account_creation_flow():
    tools = {tool["name"]: tool for tool in mcp_tool_definitions(read_only=False)}

    for name in ("gnucash_add_transaction", "gnucash_list_accounts", "gnucash_edit_transaction"):
        description = tools[name]["description"]
        assert "gnucash_list_accounts" in description
        assert "ask the user whether to create a new account first" in description
        assert "gnucash_create_account" in description
        assert "account_id" in description

    create_description = tools["gnucash_create_account"]["description"]
    assert "only after the user confirms" in create_description

    split_schema = mcp_server.transaction_split_schema()
    assert "Do not invent" in split_schema["properties"]["account_id"]["description"]
    assert "ask the user whether to create one first" in split_schema["properties"]["account_id"]["description"]


def test_mcp_tool_schemas_avoid_top_level_combinators():
    forbidden = {"oneOf", "anyOf", "allOf", "enum", "not"}

    for tool in mcp_tool_definitions(read_only=False):
        schema = tool["inputSchema"]
        assert schema["type"] == "object"
        assert forbidden.isdisjoint(schema)


def test_mcp_json_results_preserve_unicode_text():
    text = mcp_server._mcp_json_text({"description": "買飲料", "account": "資產:A0現金:錢包"})
    error = mcp_server._mcp_json_error_result("帳戶不存在")

    assert "買飲料" in text
    assert "資產:A0現金:錢包" in text
    assert "\\u" not in text
    assert "帳戶不存在" in error.content[0].text
    assert "\\u" not in error.content[0].text


def test_mcp_http_app_rejects_missing_api_key():
    from starlette.testclient import TestClient

    client = TestClient(create_mcp_http_app(config={"mcp_http_api_key": "secret"}))

    assert client.post("/mcp/", content=b"{}").status_code == 401


def test_mcp_http_app_serves_backup_routes_on_same_port(tmp_path):
    from starlette.testclient import TestClient

    client = TestClient(
        create_mcp_http_app(config={"mcp_http_api_key": "secret", "backup_dir": str(tmp_path / "backups")})
    )

    response = client.get("/", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "/ui/backups"
    assert client.get("/ui/backups").status_code == 200
    assert client.get("/api/health").json() == {"status": "ok", "book_configured": False, "backend": None}
    assert client.get("/api/backups").status_code == 401
    assert client.get("/api/backups", headers={"X-API-Key": "secret"}).json() == {"backups": []}


def test_mcp_http_app_serves_streamable_http_tools():
    import anyio
    import httpx
    from mcp.client.session import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    async def run_client():
        app = create_mcp_http_app(config={"mcp_http_api_key": "secret"})

        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://testserver",
                headers={"X-API-Key": "secret"},
                timeout=30,
            ) as http_client:
                client_context = streamable_http_client(
                    "http://testserver/mcp/",
                    http_client=http_client,
                )
                async with client_context as (read_stream, write_stream, _get_session_id):
                    async with ClientSession(read_stream, write_stream) as session:
                        await session.initialize()
                        tools = await session.list_tools()

        return [tool.name for tool in tools.tools]

    assert anyio.run(run_client) == [
        "gnucash_add_transaction",
        "gnucash_list_accounts",
        "gnucash_list_account_transactions",
        "gnucash_edit_transaction",
        "gnucash_create_account",
    ]
