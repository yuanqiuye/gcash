"""FastAPI server for remote Agent invocation."""

import logging
import os
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Request, Security
from fastapi.responses import HTMLResponse
from fastapi.security.api_key import APIKeyHeader
from pydantic import BaseModel, Field

from gnucash_cli.auth import is_api_key_authorized, resolve_api_key
from gnucash_cli.backup import (
    execute_restore,
    get_backups_list,
    resolve_backup_file,
)
from gnucash_cli.book_backend import detect_book_backend
from gnucash_cli.config import load_config
from gnucash_cli.exceptions import BackupError, GCashError
from gnucash_cli.logging_config import logger
from gnucash_cli.server_ui import backup_ui_html
from gnucash_cli.services.transactions import add_transaction_input as service_add_transaction
from gnucash_cli.transaction_input import TransactionInput

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


class TransactionRequest(TransactionInput):
    pass


class RestoreRequest(BaseModel):
    filename: str = Field(min_length=1)


def get_configured_api_key(config: dict | None = None) -> Optional[str]:
    """Get API Key from environment or config file."""
    effective_config = config if config is not None else load_config()
    return resolve_api_key(effective_config)


def _book_backend(book_path: str | None) -> str | None:
    return detect_book_backend(book_path)


def create_app(config: dict | None = None, book_path: str | None = None) -> FastAPI:
    """Create a configured FastAPI app instance."""
    app_config = config if config is not None else load_config()
    configured_api_key = get_configured_api_key(app_config)
    if not configured_api_key:
        logging.warning("No API Key configured. Server is running in insecure development mode.")

    async def verify_api_key(request: Request, api_key: str = Security(api_key_header)):
        if request.url.path in {"/api/health", "/ui/backups"}:
            return api_key

        expected_key = request.app.state.api_key
        if not expected_key:
            return api_key

        if not is_api_key_authorized(expected_key=expected_key, x_api_key=api_key):
            raise HTTPException(status_code=401, detail="Invalid or missing API key")

        return api_key

    app = FastAPI(
        title="GnuCash Agent API",
        description="Local API server for remote Agent bookkeeping. Used for Option B architecture.",
        dependencies=[Depends(verify_api_key)],
    )
    app.state.config = app_config
    app.state.book_path = book_path or os.environ.get("GNUCASH_BOOK")
    app.state.api_key = configured_api_key

    @app.post("/api/tx/add")
    async def add_transaction(req: TransactionRequest, request: Request):
        """Add a new transaction by calling the service layer directly."""
        active_book_path = request.app.state.book_path
        if not active_book_path:
            raise HTTPException(status_code=500, detail="GNUCASH_BOOK context missing")

        try:
            result = service_add_transaction(
                book_path=active_book_path,
                tx_input=req,
                config=request.app.state.config,
            )
            logger.info("API: Transaction added via /api/tx/add: '%s'", req.description)
            return result
        except GCashError as e:
            logger.warning("API: Transaction rejected: %s", e)
            raise HTTPException(status_code=400, detail=str(e))

    @app.get("/api/health")
    async def health_check(request: Request):
        """Check if the API is running and the book path is set."""
        active_book_path = request.app.state.book_path
        return {
            "status": "ok",
            "book_configured": bool(active_book_path),
            "backend": _book_backend(active_book_path),
        }

    @app.get("/ui/backups", response_class=HTMLResponse)
    async def backup_ui():
        """Web interface for restoring database backups."""
        return backup_ui_html()

    @app.get("/api/backups")
    async def api_list_backups(request: Request):
        """List available database backups."""
        return {
            "backups": get_backups_list(
                book_path=request.app.state.book_path,
                config=request.app.state.config,
            )
        }

    @app.post("/api/backups/restore")
    async def api_restore_backup(req: RestoreRequest, request: Request):
        """Restore the database from a specified backup file."""
        active_book_path = request.app.state.book_path
        if not active_book_path:
            raise HTTPException(status_code=500, detail="GNUCASH_BOOK context missing")

        safe_filename = os.path.basename(req.filename)
        backup_file = resolve_backup_file(
            safe_filename,
            book_path=active_book_path,
            config=request.app.state.config,
        )

        if not os.path.exists(backup_file):
            raise HTTPException(status_code=404, detail=f"Backup file not found: {safe_filename}")

        try:
            execute_restore(active_book_path, backup_file, config=request.app.state.config)
            logger.warning("API: Database restored from %s", safe_filename)
            return {"status": "success", "message": f"Successfully restored database from {safe_filename}"}
        except BackupError as e:
            logger.error("API: Database restore failed: %s", e)
            raise HTTPException(status_code=500, detail=str(e))
        except GCashError as e:
            logger.warning("API: Database restore rejected: %s", e)
            raise HTTPException(status_code=409, detail=str(e))

    return app


class LazyApp:
    """ASGI wrapper that preserves `gnucash_cli.server:app` without import-time config loading."""

    def __init__(self):
        self._app: FastAPI | None = None

    async def __call__(self, scope, receive, send):
        if self._app is None:
            self._app = create_app()
        await self._app(scope, receive, send)


app = LazyApp()
