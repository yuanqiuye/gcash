# Standalone GnuCash MCP Compose

Use this compose stack when AstrBot already runs elsewhere and each GnuCash user should own an independent PostgreSQL database, backup directory, and MCP endpoint.

## Server Layout

On the server, create one directory per user:

```bash
sudo mkdir -p /opt/gnucash-mcp/user1
cd /opt/gnucash-mcp/user1
cp /path/to/gnucash-cli/deploy/gnucash-mcp/docker-compose.yml .
cp /path/to/gnucash-cli/deploy/gnucash-mcp/.env.example .env
```

Edit `.env` for that user:

```dotenv
COMPOSE_PROJECT_NAME=gnucash-user1
BIND_IP=0.0.0.0
POSTGRES_USER=gnucash_user1
POSTGRES_PASSWORD=<strong-db-password>
POSTGRES_DB=gnucash_user1
POSTGRES_HOST_PORT=5432
MCP_HTTP_PORT=8765
GNUCASH_MCP_HTTP_API_KEY=<strong-mcp-api-key>
GNUCASH_CLI_IMAGE=ghcr.io/yuanqiuye/gcash:master
```

For the next user, use another directory and change at least:

- `COMPOSE_PROJECT_NAME`
- `POSTGRES_USER`
- `POSTGRES_PASSWORD`
- `POSTGRES_DB`
- `POSTGRES_HOST_PORT`
- `MCP_HTTP_PORT`
- `GNUCASH_MCP_HTTP_API_KEY`

Then start the stack:

```bash
docker compose up -d
docker compose ps
```

If you want a single-file deployment without a separate `.env`, use `docker-compose.standalone.yml`:

```bash
POSTGRES_PASSWORD='<strong-db-password>' \
GNUCASH_MCP_HTTP_API_KEY='<strong-mcp-api-key>' \
BIND_IP=0.0.0.0 \
docker compose -f docker-compose.standalone.yml up -d
```

The default application image is `ghcr.io/yuanqiuye/gcash:master`. Use a local image only for development testing, not for the standard server deployment.

## GnuCash GUI Connection

On the client machine, use the GnuCash GUI SQL connection:

- Host: the server IP or DNS name
- Port: the user's `POSTGRES_HOST_PORT`, for example `5432`
- Database: the user's `POSTGRES_DB`, for example `gnucash_user1`
- Username: the user's `POSTGRES_USER`
- Password: the user's `POSTGRES_PASSWORD`

If the GUI has this database open, automated writes are rejected by the MCP container because the PostgreSQL `gnclock` table is not empty.

## AstrBot Connection

Keep AstrBot in its existing compose stack. Configure it to call the user's MCP endpoint:

```text
http://<server-ip>:8765/mcp
```

Send either header:

```http
X-API-Key: <strong-mcp-api-key>
```

or:

```http
Authorization: Bearer <strong-mcp-api-key>
```

For write tools, have the agent call `gnucash_list_accounts` first and use the returned `id` as `account_id` in `gnucash_add_transaction` splits. Account names are still accepted for compatibility, but `account_id` is the stable identifier and avoids failures from renamed, duplicated, or abbreviated account names.

To inspect one account's recent records, call `gnucash_list_account_transactions`:

```json
{
  "account_id": "cash-account-guid",
  "limit": 10
}
```

The response includes `transaction_id`. Use that id with `gnucash_edit_transaction` to update metadata or replace all splits with a balanced debit/credit set:

```json
{
  "transaction_id": "transaction-guid",
  "description": "Corrected transaction",
  "debits": [{"account_id": "expense-account-guid", "value": "50"}],
  "credits": [{"account_id": "cash-account-guid", "value": "50"}]
}
```

## Backup HTTP Connection

The MCP HTTP service also serves the backup listing and restore UI on the same port. It uses the same `GNUCASH_BOOK`, `backups/`, and `locks/` directories as the MCP tools.

Open the restore UI:

```text
http://<server-ip>:8765/ui/backups
```

The UI prompts for `GNUCASH_MCP_HTTP_API_KEY` when it calls the protected backup APIs. Direct API calls use the same key as MCP:

```http
X-API-Key: <strong-mcp-api-key>
```

Useful endpoints:

```text
GET  /api/health
GET  /api/backups
POST /api/backups/restore
```

## Read-Only Mode

For an MCP server that can inspect accounts but cannot write:

```dotenv
GNUCASH_MCP_READ_ONLY=1
```

Restart:

```bash
docker compose up -d
```

The server exposes only `gnucash_list_accounts`.

## Backup and Migration

Each user directory is self-contained:

```text
user1/
  .env
  docker-compose.yml
  postgres_data/
  backups/
  locks/
```

To migrate one user, stop only that user's compose stack and archive that directory:

```bash
docker compose down
tar -czf gnucash-user1-$(date +%Y%m%d).tar.gz .env docker-compose.yml postgres_data backups
```

Restore it on another server by extracting the archive, checking `.env`, and running:

```bash
docker compose up -d
```
