"""HTML fragments served by the local FastAPI API."""


def backup_ui_html() -> str:
    return """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>GnuCash Agent - Restore Panel</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <script>
            function getApiHeaders(extra = {}) {
                const headers = { ...extra };
                let apiKey = sessionStorage.getItem('gcashApiKey') || '';
                if (!apiKey) {
                    apiKey = window.prompt('API key');
                    if (apiKey) {
                        sessionStorage.setItem('gcashApiKey', apiKey);
                    }
                }
                if (apiKey) {
                    headers['X-API-Key'] = apiKey;
                }
                return headers;
            }

            function showStatus(kind, message) {
                const msgBox = document.getElementById('statusMsg');
                const styles = {
                    info: 'p-4 mb-4 text-sm text-blue-800 rounded-lg bg-blue-50 block',
                    success: 'p-4 mb-4 text-sm text-green-800 rounded-lg bg-green-50 block',
                    error: 'p-4 mb-4 text-sm text-red-800 rounded-lg bg-red-50 block'
                };
                msgBox.className = styles[kind] || styles.info;
                msgBox.innerText = message;
            }

            function addCell(row, text, className) {
                const cell = document.createElement('td');
                cell.className = className;
                cell.textContent = text;
                row.appendChild(cell);
                return cell;
            }

            async function fetchBackups() {
                const response = await fetch('/api/backups', {
                    headers: getApiHeaders()
                });
                if (response.status === 401) {
                    sessionStorage.removeItem('gcashApiKey');
                    showStatus('error', 'Invalid or missing API key.');
                    return;
                }
                const data = await response.json();
                const tbody = document.getElementById('backupList');
                tbody.innerHTML = '';

                if (data.backups.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="4" class="px-6 py-4 text-center text-sm text-gray-500">No backups found</td></tr>';
                    return;
                }

                data.backups.forEach(b => {
                    const row = document.createElement('tr');
                    addCell(row, b.filename, 'px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900');
                    addCell(row, `${(b.size / 1024).toFixed(2)} KB`, 'px-6 py-4 whitespace-nowrap text-sm text-gray-500');
                    addCell(row, b.time, 'px-6 py-4 whitespace-nowrap text-sm text-gray-500');

                    const actionCell = addCell(row, '', 'px-6 py-4 whitespace-nowrap text-right text-sm font-medium');
                    const button = document.createElement('button');
                    button.className = 'bg-red-600 hover:bg-red-700 text-white font-bold py-2 px-4 rounded shadow transition-colors duration-200';
                    button.textContent = 'Restore';
                    button.addEventListener('click', () => restoreBackup(b.filename));
                    actionCell.appendChild(button);
                    tbody.appendChild(row);
                });
            }

            async function restoreBackup(filename) {
                if (!confirm(`WARNING\\n\\nAre you sure you want to OVERWRITE the current database using the backup: ${filename}?\\n\\nThis action cannot be undone.`)) {
                    return;
                }

                showStatus('info', 'Restoring database, please wait...');

                try {
                    const response = await fetch('/api/backups/restore', {
                        method: 'POST',
                        headers: getApiHeaders({ 'Content-Type': 'application/json' }),
                        body: JSON.stringify({ filename: filename })
                    });
                    if (response.status === 401) {
                        sessionStorage.removeItem('gcashApiKey');
                        showStatus('error', 'Invalid or missing API key.');
                        return;
                    }

                    const result = await response.json();

                    if (response.ok && result.status === 'success') {
                        showStatus('success', 'Success: ' + result.message);
                    } else {
                        showStatus('error', 'Error: ' + (result.detail || result.error || 'Unknown error'));
                    }
                } catch (e) {
                    showStatus('error', 'Request failed: ' + e.message);
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
                    Refresh List
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
                    </tbody>
                </table>
            </div>
        </div>
    </body>
    </html>
    """
