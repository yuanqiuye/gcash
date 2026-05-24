# gcash — GnuCash CLI for Automated Bookkeeping

A command-line bookkeeping tool built on [piecash](https://github.com/sdementen/piecash), designed for AI Agent automated bookkeeping.  
No need to install GnuCash or Perl modules — runs in a pure Python environment.

## Installation

```bash
cd gnucash-cli
pip install -e .
```

## Configuration

Create a config file at `~/.gnucash-cli/config.yaml`:

```yaml
# Default currency
default_currency: TWD

# Default book path
default_book: ~/Documents/my_finance.gnucash

# API Key (recommended when using the serve command)
api_key: your-secret-key

# MCP options. Set mcp_read_only for agents that should inspect accounts only.
mcp_read_only: false
mcp_http_api_key: your-mcp-http-secret

# Optional runtime directories. If omitted, backups for local SQLite books are
# stored beside the book in .backups, while PostgreSQL backups and locks use
# ~/.gnucash-cli/backups and ~/.gnucash-cli/locks.
backup_dir: ~/Documents/gnucash-backups
lock_dir: ~/.gnucash-cli/locks

# Optional unsafe override. Leave this false unless you manually accept the
# risk of skipping pre-write safety backups.
allow_unsafe_no_auto_backup: false
```

Book path priority: `--book` argument > `GNUCASH_BOOK` environment variable > config file
Runtime directory overrides: `GNUCASH_BACKUP_DIR` and `GNUCASH_LOCK_DIR` take priority over config values.

## Usage

### Account Management

```bash
# List all accounts (tree structure)
gcash -b my.gnucash accounts list

# JSON format (suitable for AI Agent parsing)
gcash -b my.gnucash accounts list --format json

# Filter by type
gcash -b my.gnucash accounts list --type EXPENSE

# Create an account
gcash -b my.gnucash accounts create --name "Dining" --type EXPENSE --parent "Expenses"
gcash -b my.gnucash accounts create --name "USD Account" --type BANK --parent "Assets" --currency USD
```

### Bookkeeping

```bash
# Basic bookkeeping (wallet paid 150 for lunch)
gcash -b my.gnucash tx add \
  -d "Lunch" \
  --debit "Expenses:Dining 150" \
  --credit "Assets:Cash:Wallet 150"

# Specify date
gcash -b my.gnucash tx add \
  -d "Lunch" \
  --debit "Expenses:Dining 150" \
  --credit "Assets:Cash:Wallet 150" \
  --date 2026-03-30

# Multi-currency: pay 30 USD (equivalent to 930 TWD) from a USD account
gcash -b my.gnucash tx add \
  -d "USD purchase" \
  --debit "Expenses:Dining 930" \
  --credit "Assets:USD Account 930 USD 30"

# View recent transactions
gcash -b my.gnucash tx list

# Query transactions for a specific account
gcash -b my.gnucash tx list --account "Expenses:Dining" --from 2026-01-01 --to 2026-03-31

# JSON output
gcash -b my.gnucash tx list --format json
```

### Agent-Friendly: Bookkeeping via JSON File

In automated pipelines (CI, local Docker, co-located Agent), passing CJK characters on the command line may encounter encoding issues.  
Use the `--file` option to pass transaction parameters via a JSON file instead:

```bash
gcash -b my.gnucash tx add --file tx.json --format json
```

### Cross-Machine Collaboration: Remote Server Agent Operating a Local Book

If you encounter the scenario where **"the Agent and Docker are on a remote server, but GnuCash is on your local machine"**, a strong warning: **never mount SQLite over SMB/network drives** — this will permanently corrupt the GnuCash database (SQLite does not support network locking).

We provide two architectures to solve remote control:

#### Option A: Upgrade to a Database Connection (PostgreSQL) — 【Highly Recommended】
GnuCash natively supports relational databases. Place the book on a server-side database so both sides read/write over the network, fundamentally solving lock and file sync issues.

1. **Deploy Postgres**: Create a `.env` file with credentials, then run `docker compose up -d`:
   ```env
   # .env
   POSTGRES_PASSWORD=your-secure-password
   POSTGRES_USER=gnucash
   POSTGRES_DB=gnucash_data
   GNUCASH_API_KEY=your-api-key
   ```
2. **Migrate your book**: Open GnuCash GUI on your local machine → Save As → choose "Database Connection" → enter the server IP, username (`POSTGRES_USER` from `.env`), and password (`POSTGRES_PASSWORD` from `.env`).
3. **Agent calls**: `docker compose up -d` also starts the CLI API Server. The book path is read automatically from `.env`.

> [!TIP]
> **🛡️ Agent Safety Net (Auto Backup & Rollback)**
>
> Before any write operation (`tx add`, `accounts create`, etc.), the system automatically backs up the database. Local SQLite books default to a `.backups/` directory beside the book; PostgreSQL defaults to `~/.gnucash-cli/backups`. Override with `GNUCASH_BACKUP_DIR` or `backup_dir`.
> **Supports both PostgreSQL and SQLite (.gnucash) backends.**
> Write operations are serialized with a per-book lock under `~/.gnucash-cli/locks` by default, so concurrent Agent calls from different working directories do not mutate the same book at the same time. Override with `GNUCASH_LOCK_DIR` or `lock_dir`.
> 
> **🖥️ One-Click Restore via Web UI (Recommended)**
> When you run the standalone MCP compose stack, the Web UI is served by the same HTTP service as MCP.
> 1. Open your browser to the server IP: `http://<Server_IP>:8765/ui/backups`
> 2. Enter your `GNUCASH_MCP_HTTP_API_KEY` when prompted.
> 3. Pick a backup from before the unwanted action, click "Restore" to revert your book!
> 
> **💻 Restore via CLI**
> You can also use the terminal: `./docker-gcash.sh db list-backups` and `./docker-gcash.sh db restore --file .backups/xxx.sql`.

#### Option B: Local Lightweight Web API (FastAPI) — 【Compromise Without Migrating the Database】
If you prefer to keep the SQLite file locally:
1. Install this project on your local machine (`pip install -e .`).
2. Configure an API Key (strongly recommended):
   Set the environment variable `GNUCASH_API_KEY=your-secret-key` (takes priority), or write `api_key: your-secret-key` in `~/.gnucash-cli/config.yaml`.
   Without an API key, `gcash serve` is allowed only on loopback hosts such as `127.0.0.1` for local development. Binding to an exposed host such as `0.0.0.0` requires an API key.
3. Start the server locally:
   ```bash
   gcash -b my.gnucash serve --port 8000
   ```
4. Use a tunneling tool (e.g. Tailscale or Ngrok) to let the server reach your local port `8000`.
5. **Remote Agent call method**: The Agent sends an HTTP POST request with an `X-API-Key` header:
   ```bash
   curl -X POST "http://<Your_Local_IP>:8000/api/tx/add" \
        -H "Content-Type: application/json" \
        -H "X-API-Key: your-secret-key" \
        -d '{"description": "Lunch", "debits": ["Expenses:Dining 150"], "credits": ["Assets:Cash 150"]}'
   ```
   Structured split objects are also accepted and are preferred for agents:
   ```bash
   curl -X POST "http://<Your_Local_IP>:8000/api/tx/add" \
        -H "Content-Type: application/json" \
        -H "X-API-Key: your-secret-key" \
        -d '{"description": "Lunch", "debits": [{"account": "Expenses:Dining", "value": "150"}], "credits": [{"account": "Assets:Cash", "value": "150"}]}'
   ```

### Multi-Currency Bookkeeping

Multi-currency split format: `"Account value [CURRENCY [quantity]]"`

| Format | Description |
|--------|-------------|
| `"Account 100"` | Single currency, value=100, quantity=100 |
| `"Account 930 USD 30"` | Multi-currency, transaction value=930 (in transaction currency), actual=30 USD |

### Currency Management

```bash
# List currencies in the book
gcash -b my.gnucash currencies list

# Add a currency
gcash -b my.gnucash currencies add --code USD
gcash -b my.gnucash currencies add --code JPY

# Update exchange rates (from open.er-api.com, supports 150+ currencies including TWD)
gcash -b my.gnucash currencies update-prices
gcash -b my.gnucash currencies update-prices --base USD
```

### Database Backup & Restore

```bash
# Manual backup
gcash -b my.gnucash db backup

# List backups
gcash -b my.gnucash db list-backups

# Restore from a backup
gcash -b my.gnucash db restore --file .backups/sqlite_backup_manual_20260405_163000.gnucash
```

> Write operations (`tx add`, `accounts create`) automatically trigger a backup. Disabling this safety backup requires `allow_unsafe_no_auto_backup: true` and `--unsafe-no-auto-backup`.

## Global Options

| Option | Description |
|--------|-------------|
| `--book`, `-b` | Specify the GnuCash book path |
| `--config` | Specify the config file path |
| `-v`, `--verbose` | Enable verbose logging output (DEBUG level) |
| `--version` | Show version |
| `--help` | Show help |

---

## 🤖 AI Agent Integration Guide (MCP Support)

This project supports the **Model Context Protocol (MCP)**. Rather than having the Agent assemble commands and mount files itself, MCP is currently the most robust and native integration method. By mounting this project as an MCP Server to the Agent, the Agent can directly call native Tools like `gnucash_add_transaction`, while enjoying automatic database backup protections!

### How to Connect an Agent to the GnuCash MCP Server?

If you use an MCP-supporting framework (e.g. Claude Desktop or Cursor):

Configure their `mcpServers` config file (example connecting to Docker on the same server):

```json
{
  "mcpServers": {
    "gnucash-agent": {
      "command": "docker",
      "args": [
        "run",
        "-i",
        "--rm",
        "--network",
        "gnucash-cli_gnucash_net",
        "-v",
        "./.backups:/app/.backups",
        "ghcr.io/yuanqiuye/gcash:master",
        "gcash",
        "mcp"
      ]
    }
  }
}
```

> **How it works**: This launches a disposable CLI container and establishes a standard secure MCP channel via Standard I/O (stdio). The Agent can then operate on your PostgreSQL book through a standardized Tools Schema — no need to write or maintain shell scripts!

### Read-Only MCP Mode

Use read-only mode for agents that should only inspect the book. In this mode the MCP server exposes `gnucash_list_accounts` and hides mutating tools such as `gnucash_add_transaction` and `gnucash_create_account`.

```bash
GNUCASH_MCP_READ_ONLY=1 gcash -b "postgresql://gcash:password@<server-ip>:5432/gnucash_user1" mcp
```

You can also set this in `~/.gnucash-cli/config.yaml`:

```yaml
mcp_read_only: true
```

### Streamable HTTP MCP

For a long-running MCP service, start the native Streamable HTTP endpoint instead of wrapping stdio over SSH:

```bash
export GNUCASH_MCP_HTTP_API_KEY="change-this-secret"
gcash -b "postgresql://gcash:password@<server-ip>:5432/gnucash_user1" \
  mcp-http --host 0.0.0.0 --port 8765 --path /mcp
```

When binding to anything other than `127.0.0.1`, `localhost`, or `::1`, an API key is required. Clients must send either:

```http
X-API-Key: change-this-secret
```

or:

```http
Authorization: Bearer change-this-secret
```

The same HTTP service also exposes the backup UI and backup APIs on the same port:

```text
http://<server-ip>:8765/ui/backups
```

Use the same API key header for protected backup API calls.

### Account Identifiers for Writes

`gnucash_list_accounts` returns both `id` and `guid` for each account. Treat this value as the stable account identifier for write tools.

Preferred transaction split format:

```json
{
  "description": "Lunch",
  "debits": [{"account_id": "expense-account-guid", "value": "150"}],
  "credits": [{"account_id": "cash-account-guid", "value": "150"}],
  "currency": "TWD"
}
```

Legacy account names/fullnames are still accepted for compatibility, but agents should call `gnucash_list_accounts` first and use `account_id`. This avoids wrong writes when account names are renamed, duplicated, localized, or abbreviated.

To inspect recent activity for one account:

```json
{
  "account_id": "cash-account-guid",
  "limit": 10
}
```

Call this through `gnucash_list_account_transactions`. The response includes `transaction_id` and per-split `split_id` values.

To edit a transaction, call `gnucash_edit_transaction` with `transaction_id`. Metadata-only edits are allowed:

```json
{
  "transaction_id": "transaction-guid",
  "description": "Corrected description",
  "date": "2026-05-24",
  "notes": "Corrected by MCP"
}
```

To change accounts or amounts, replace the full split set by providing both balanced `debits` and `credits`:

```json
{
  "transaction_id": "transaction-guid",
  "debits": [{"account_id": "expense-account-guid", "value": "50"}],
  "credits": [{"account_id": "cash-account-guid", "value": "50"}]
}
```

Partial split edits are intentionally not exposed, because GnuCash transactions must remain balanced.

### PostgreSQL GUI Lock Check

Before automated writes, PostgreSQL books are checked for active rows in GnuCash's `gnclock` table. If GnuCash GUI has the same SQL book open, writes are refused with a lock error. Read-only tools can still be exposed through MCP read-only mode.

### Per-User Compose Layout

For multiple users, keep each user in a separate `gnucash-mcp` compose project. This keeps migration, backup, restore, secrets, and API exposure independent from AstrBot and from other users.

Recommended layout:

```text
/opt/gnucash-mcp/
  user-alice/
    docker-compose.yml
    .env
    backups/
  user-bob/
    docker-compose.yml
    .env
    backups/
```

Each user should get:

- A unique Compose project name, for example `gnucash-alice`.
- A unique PostgreSQL database or schema, for example `gnucash_alice`.
- A unique MCP HTTP port if exposed directly, for example `8765`, `8766`, `8767`.
- A separate `GNUCASH_MCP_HTTP_API_KEY`.
- A separate backup directory mounted into that user's container.

AstrBot can remain in its own compose stack and call the selected user's MCP endpoint, for example `http://<server-ip>:8765/mcp`, with that user's API key. The GnuCash GUI should connect to the same user's PostgreSQL database. If the GUI is open, automated writes for that user's MCP service will be rejected by the `gnclock` check.

See `deploy/gnucash-mcp/` for a standalone compose template that includes PostgreSQL, the Streamable HTTP MCP service, the backup/restore HTTP UI, per-user backups, read-only mode, and migration notes.

---

## 🔌 API Endpoints

The FastAPI server started by `gcash serve` provides the following endpoints:

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/api/health` | ❌ | Check server status without exposing the book path |
| `POST` | `/api/tx/add` | ✅ | Add a new transaction |
| `GET` | `/api/backups` | ✅ | List available backups |
| `POST` | `/api/backups/restore` | ✅ | Restore the database from a specified backup |
| `GET` | `/ui/backups` | ✅ | Web backup restore interface |

**Authentication:** Include `X-API-Key: your-key` in the request header. The restore UI prompts for the same key and stores it only in browser session storage.
API Key priority: `GNUCASH_API_KEY` environment variable > `api_key` in `config.yaml`.
`/api/health` is intentionally safe for unauthenticated monitoring: it reports only status, whether a book is configured, and the backend type, never the full book path or database URL.

**POST /api/tx/add request format:**
```json
{
  "description": "Lunch",
  "date": "2026-04-06",
  "debits": [{"account": "Expenses:Dining", "value": "150"}],
  "credits": [{"account": "Assets:Cash", "value": "150"}],
  "notes": "Optional memo",
  "currency": "TWD"
}
```
Structured split `value` and `quantity` fields must be decimal strings. JSON floats such as `0.1` are rejected to preserve bookkeeping precision.
Legacy string split specs such as `"Expenses:Dining 150"` are still supported.

**POST /api/backups/restore request format:**
```json
{
  "filename": "sqlite_backup_pre_tx_20260405_163000.gnucash"
}
```

## Output Format

All commands support `--format table` (default, human-readable) and `--format json` (suitable for Agent parsing).
JSON amount fields such as `value`, `quantity`, `balance`, and exchange `rate` are decimal strings to preserve bookkeeping precision.

## Development Checks

Run the fast local checks with `uv`:

```bash
uv run pytest -q --basetemp .pytest-tmp
uv run --extra dev ruff check gnucash_cli tests
uv run python -m compileall -q gnucash_cli tests
```

The PostgreSQL `gnclock` integration test is opt-in because it mutates the target database. Use only a disposable database:

```bash
GNUCASH_TEST_POSTGRES_DSN="postgresql://user:password@localhost:5432/disposable_gnucash_test" \
GNUCASH_TEST_POSTGRES_MUTATE=1 \
uv run pytest -m integration tests/test_integration_postgres.py
```

## Dependencies

- Python ≥ 3.10
- piecash ≥ 1.2.0
- click ≥ 8.0
- rich ≥ 13.0
- pyyaml ≥ 6.0
- requests ≥ 2.28.0
- fastapi ≥ 0.100.0 (API server)
- uvicorn ≥ 0.22.0 (API server)
- mcp ≥ 1.2.0 (MCP server)
