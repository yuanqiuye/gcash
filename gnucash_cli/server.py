"""FastAPI server for remote Agent invocation."""
import os
from typing import Optional
from fastapi import FastAPI, HTTPException, Depends, Security, Request
from pydantic import BaseModel
from fastapi.security.api_key import APIKeyHeader
from gnucash_cli.config import load_config
from gnucash_cli.service import add_transaction as service_add_transaction
from gnucash_cli.utils import logger
import logging

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

def get_configured_api_key() -> Optional[str]:
    """Get API Key from environment or config file."""
    env_key = os.environ.get("GNUCASH_API_KEY")
    if env_key:
        return env_key
    config = load_config()
    return config.get("api_key")

configured_api_key = get_configured_api_key()
if not configured_api_key:
    logging.warning("No API Key configured. Server is running in insecure development mode.")

async def verify_api_key(request: Request, api_key: str = Security(api_key_header)):
    """Dependency to check the API Key."""
    # Skip check for health endpoint
    if request.url.path == "/api/health":
        return api_key
        
    if not configured_api_key:
        return api_key
        
    if not api_key or api_key != configured_api_key:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
        
    return api_key

app = FastAPI(
    title="GnuCash Agent API", 
    description="Local API server for remote Agent bookkeeping. Used for Option B architecture.",
    dependencies=[Depends(verify_api_key)]
)

class TransactionRequest(BaseModel):
    description: str
    date: Optional[str] = None
    debits: list[str]
    credits: list[str]
    notes: Optional[str] = None
    currency: Optional[str] = None

_config = load_config()

@app.post("/api/tx/add")
async def add_transaction(req: TransactionRequest):
    """Add a new transaction by calling the service layer directly."""
    book_path = os.environ.get("GNUCASH_BOOK")
    if not book_path:
        raise HTTPException(status_code=500, detail="GNUCASH_BOOK context missing")

    try:
        result = service_add_transaction(
            book_path=book_path,
            description=req.description,
            debits=req.debits,
            credits_=req.credits,
            tx_date=req.date,
            tx_currency=req.currency,
            notes=req.notes or "",
            config=_config,
        )
        logger.info("API: Transaction added via /api/tx/add: '%s'", req.description)
        return result
    except ValueError as e:
        logger.warning("API: Transaction rejected: %s", e)
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/health")
async def health_check():
    """Check if the API is running and the book path is set."""
    return {"status": "ok", "book": os.environ.get("GNUCASH_BOOK")}

from fastapi.responses import HTMLResponse

@app.get("/ui/backups", response_class=HTMLResponse)
async def backup_ui():
    """Web interface for restoring database backups."""
    html_content = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>GnuCash Agent - Restore Panel</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <script>
            async function fetchBackups() {
                const response = await fetch('/api/backups');
                const data = await response.json();
                const tbody = document.getElementById('backupList');
                tbody.innerHTML = '';
                
                if (data.backups.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="4" class="px-6 py-4 text-center text-sm text-gray-500">No backups found</td></tr>';
                    return;
                }
                
                data.backups.forEach(b => {
                    const row = document.createElement('tr');
                    
                    row.innerHTML = `
                        <td class="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">${b.filename}</td>
                        <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">${(b.size / 1024).toFixed(2)} KB</td>
                        <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">${b.time}</td>
                        <td class="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                            <button onclick="restoreBackup('${b.filename}')" class="bg-red-600 hover:bg-red-700 text-white font-bold py-2 px-4 rounded shadow transition-colors duration-200">
                                ↻ Restore
                            </button>
                        </td>
                    `;
                    tbody.appendChild(row);
                });
            }
            
            async function restoreBackup(filename) {
                if (!confirm(`WARNING\\n\\nAre you sure you want to OVERWRITE the current database using the backup: ${filename}?\\n\\nThis action cannot be undone.`)) {
                    return;
                }
                
                // Show loading
                const msgBox = document.getElementById('statusMsg');
                msgBox.className = 'p-4 mb-4 text-sm text-blue-800 rounded-lg bg-blue-50 block';
                msgBox.innerText = 'Restoring database, please wait...';
                
                try {
                    const response = await fetch('/api/backups/restore', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ filename: filename })
                    });
                    
                    const result = await response.json();
                    
                    if (response.ok && result.status === 'success') {
                        msgBox.className = 'p-4 mb-4 text-sm text-green-800 rounded-lg bg-green-50 block';
                        msgBox.innerText = '✅ Success: ' + result.message;
                    } else {
                        msgBox.className = 'p-4 mb-4 text-sm text-red-800 rounded-lg bg-red-50 block';
                        msgBox.innerText = '❌ Error: ' + (result.detail || result.error || 'Unknown error');
                    }
                } catch (e) {
                    msgBox.className = 'p-4 mb-4 text-sm text-red-800 rounded-lg bg-red-50 block';
                    msgBox.innerText = '❌ Request failed: ' + e.message;
                }
            }
            
            window.onload = fetchBackups;
        </script>
    </head>
    <body class="bg-gray-100 min-h-screen p-8">
        <div class="max-w-5xl mx-auto">
            <div class="flex items-center justify-between mb-2">
                <h1 class="text-3xl font-bold text-gray-800">GnuCash Agent <span class="text-blue-600">Restore Panel</span></h1>
                <button onclick="fetchBackups()" class="flex items-center text-sm text-gray-600 hover:text-gray-900 bg-white border border-gray-300 rounded px-3 py-1 shadow-sm">
                    ↻ Refresh List
                </button>
            </div>
            
            <p class="text-gray-600 mb-8">Click <b>Restore</b> to instantly revert the database to a previous safe snapshot before the Agent performed an action.</p>
            
            <div id="statusMsg" class="hidden font-medium shadow-sm transition-all duration-300"></div>
            
            <div class="bg-white shadow overflow-hidden sm:rounded-lg">
                <table class="min-w-full divide-y divide-gray-200">
                    <thead class="bg-gray-50">
                        <tr>
                            <th scope="col" class="px-6 py-3 text-left text-xs font-bold text-gray-500 uppercase tracking-wider">Filename</th>
                            <th scope="col" class="px-6 py-3 text-left text-xs font-bold text-gray-500 uppercase tracking-wider">Size</th>
                            <th scope="col" class="px-6 py-3 text-left text-xs font-bold text-gray-500 uppercase tracking-wider">Creation Time</th>
                            <th scope="col" class="px-6 py-3 text-right text-xs font-bold text-gray-500 uppercase tracking-wider">Action</th>
                        </tr>
                    </thead>
                    <tbody id="backupList" class="bg-white divide-y divide-gray-200">
                        <!-- Filled by JS -->
                    </tbody>
                </table>
            </div>
        </div>
    </body>
    </html>
    """
    return html_content

@app.get("/api/backups")
async def api_list_backups():
    """List available database backups."""
    from gnucash_cli.commands.db import get_backups_list
    return {"backups": get_backups_list()}

class RestoreRequest(BaseModel):
    filename: str

@app.post("/api/backups/restore")
async def api_restore_backup(req: RestoreRequest):
    """Restore the database from a specified backup file."""
    import os
    from gnucash_cli.commands.db import execute_restore, _get_backup_dir
    
    book_path = os.environ.get("GNUCASH_BOOK")
    if not book_path:
        raise HTTPException(status_code=500, detail="GNUCASH_BOOK context missing")
        
    # Prevent directory traversal
    safe_filename = os.path.basename(req.filename)
    backup_file = os.path.join(_get_backup_dir(), safe_filename)
    
    if not os.path.exists(backup_file):
        raise HTTPException(status_code=404, detail=f"Backup file not found: {safe_filename}")
        
    success = execute_restore(book_path, backup_file)
    if success:
        logger.warning("API: Database restored from %s", safe_filename)
        return {"status": "success", "message": f"Successfully restored database from {safe_filename}"}
    else:
        logger.error("API: Database restore failed from %s", safe_filename)
        raise HTTPException(status_code=500, detail="Restore operation failed. Check server logs.")
