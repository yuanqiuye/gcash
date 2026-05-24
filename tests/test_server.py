from fastapi.testclient import TestClient


def _load_server(monkeypatch, tmp_path):
    monkeypatch.setenv("GNUCASH_API_KEY", "secret")

    import gnucash_cli.server as server

    app = server.create_app(
        config={"api_key": "secret", "default_currency": "TWD", "backup_dir": str(tmp_path / "backups")},
        book_path="dummy.gnucash",
    )
    return server, app


def test_restore_ui_loads_without_header_but_api_requires_key(monkeypatch, tmp_path):
    _server, app = _load_server(monkeypatch, tmp_path)
    client = TestClient(app)

    assert client.get("/ui/backups").status_code == 200
    assert client.get("/api/backups").status_code == 401
    assert client.get("/api/backups", headers={"X-API-Key": "secret"}).status_code == 200


def test_root_redirects_to_backup_ui(monkeypatch, tmp_path):
    _server, app = _load_server(monkeypatch, tmp_path)
    client = TestClient(app, follow_redirects=False)

    response = client.get("/")

    assert response.status_code == 307
    assert response.headers["location"] == "/ui/backups"


def test_api_rejects_empty_transaction_before_service_call(monkeypatch, tmp_path):
    _server, app = _load_server(monkeypatch, tmp_path)
    client = TestClient(app)

    response = client.post(
        "/api/tx/add",
        headers={"X-API-Key": "secret"},
        json={"description": "Empty", "debits": [], "credits": []},
    )

    assert response.status_code == 422


def test_api_accepts_structured_transaction_splits(monkeypatch, tmp_path):
    server, app = _load_server(monkeypatch, tmp_path)
    client = TestClient(app)
    captured = {}

    def fake_add_transaction(book_path, tx_input, config):
        captured["book_path"] = book_path
        captured["tx_input"] = tx_input
        return {"status": "success", "transaction": {"description": tx_input.description}}

    monkeypatch.setattr(server, "service_add_transaction", fake_add_transaction)

    response = client.post(
        "/api/tx/add",
        headers={"X-API-Key": "secret"},
        json={
            "description": "Lunch",
            "date": "2026-05-11",
            "debits": [{"account": "Expenses:Dining", "value": "150"}],
            "credits": [{"account": "Assets:Cash", "value": "150"}],
            "currency": "twd",
        },
    )

    assert response.status_code == 200
    assert captured["book_path"] == "dummy.gnucash"
    assert captured["tx_input"].currency == "TWD"
    assert captured["tx_input"].debits[0].account_fullname == "Expenses:Dining"


def test_api_accepts_account_id_transaction_splits(monkeypatch, tmp_path):
    server, app = _load_server(monkeypatch, tmp_path)
    client = TestClient(app)
    captured = {}

    def fake_add_transaction(book_path, tx_input, config):
        captured["tx_input"] = tx_input
        return {"status": "success", "transaction": {"description": tx_input.description}}

    monkeypatch.setattr(server, "service_add_transaction", fake_add_transaction)

    response = client.post(
        "/api/tx/add",
        headers={"X-API-Key": "secret"},
        json={
            "description": "Lunch",
            "debits": [{"account_id": "expense-guid", "value": "150"}],
            "credits": [{"account_id": "cash-guid", "value": "150"}],
        },
    )

    assert response.status_code == 200
    assert captured["tx_input"].debits[0].account_id == "expense-guid"
    assert captured["tx_input"].debits[0].account_fullname is None


def test_create_app_uses_instance_state_not_import_time_env(monkeypatch, tmp_path):
    monkeypatch.setenv("GNUCASH_API_KEY", "env-secret")

    import gnucash_cli.server as server

    sensitive_book = "postgresql://user:secret@example.com/gnucash"
    app = server.create_app(
        config={"api_key": "config-secret", "backup_dir": str(tmp_path / "backups")},
        book_path=sensitive_book,
    )
    client = TestClient(app)

    health = client.get("/api/health").json()
    assert health == {"status": "ok", "book_configured": True, "backend": "postgresql"}
    assert "secret" not in str(health)
    assert client.get("/api/backups", headers={"X-API-Key": "config-secret"}).status_code == 401
    assert client.get("/api/backups", headers={"X-API-Key": "env-secret"}).status_code == 200


def test_api_rejects_float_amounts(monkeypatch, tmp_path):
    _server, app = _load_server(monkeypatch, tmp_path)
    client = TestClient(app)

    response = client.post(
        "/api/tx/add",
        headers={"X-API-Key": "secret"},
        json={
            "description": "Float",
            "debits": [{"account": "Expenses:Dining", "value": 0.1}],
            "credits": [{"account": "Assets:Cash", "value": "0.10"}],
        },
    )

    assert response.status_code == 422
    assert "JSON floats are not accepted" in response.text
