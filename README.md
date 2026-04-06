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
```

Book path priority: `--book` argument > `GNUCASH_BOOK` environment variable > config file

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
> Before any write operation (`tx add`, `accounts create`, etc.), the system automatically backs up the database to `./.backups/`.
> **Supports both PostgreSQL and SQLite (.gnucash) backends.**
> 
> **🖥️ One-Click Restore via Web UI (Recommended)**
> When you run `docker compose up -d` to start PostgreSQL, the Web UI starts alongside it!
> 1. Open your browser to the server IP: `http://<Server_IP>:8000/ui/backups`
> 2. Pick a backup from before the unwanted action, click "Restore" to revert your book!
> 
> **💻 Restore via CLI**
> You can also use the terminal: `./docker-gcash.sh db list-backups` and `./docker-gcash.sh db restore --file .backups/xxx.sql`.

#### Option B: Local Lightweight Web API (FastAPI) — 【Compromise Without Migrating the Database】
If you prefer to keep the SQLite file locally:
1. Install this project on your local machine (`pip install -e .`).
2. Configure an API Key (strongly recommended):
   Set the environment variable `GNUCASH_API_KEY=your-secret-key` (takes priority), or write `api_key: your-secret-key` in `~/.gnucash-cli/config.yaml`.
   If not set, the system prints a warning but still starts (development mode).
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

> Write operations (`tx add`, `accounts create`) automatically trigger a backup. Disable with `--no-auto-backup`.

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

---

## 🔌 API Endpoints

The FastAPI server started by `gcash serve` provides the following endpoints:

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/api/health` | ❌ | Check server status and book path |
| `POST` | `/api/tx/add` | ✅ | Add a new transaction |
| `GET` | `/api/backups` | ✅ | List available backups |
| `POST` | `/api/backups/restore` | ✅ | Restore the database from a specified backup |
| `GET` | `/ui/backups` | ✅ | Web backup restore interface |

**Authentication:** Include `X-API-Key: your-key` in the request header.
API Key priority: `GNUCASH_API_KEY` environment variable > `api_key` in `config.yaml`.

**POST /api/tx/add request format:**
```json
{
  "description": "Lunch",
  "date": "2026-04-06",
  "debits": ["Expenses:Dining 150"],
  "credits": ["Assets:Cash 150"],
  "notes": "Optional memo",
  "currency": "TWD"
}
```

**POST /api/backups/restore request format:**
```json
{
  "filename": "sqlite_backup_pre_tx_20260405_163000.gnucash"
}
```

## Output Format

All commands support `--format table` (default, human-readable) and `--format json` (suitable for Agent parsing).

## Dependencies

- Python ≥ 3.9
- piecash ≥ 1.2.0
- click ≥ 8.0
- rich ≥ 13.0
- pyyaml ≥ 6.0
- requests ≥ 2.28.0
- fastapi ≥ 0.100.0 (API server)
- uvicorn ≥ 0.22.0 (API server)
- mcp ≥ 1.2.0 (MCP server)
