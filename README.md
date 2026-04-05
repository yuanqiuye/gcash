# gcash — GnuCash CLI for Automated Bookkeeping

基於 [piecash](https://github.com/sdementen/piecash) 的命令行記賬工具，專為 AI Agent 自動記賬設計。  
不需要安裝 GnuCash 或 Perl 模組，純 Python 環境即可運行。

## 安裝

```bash
cd gnucash-cli
pip install -e .
```

## 配置

建立配置文件 `~/.gnucash-cli/config.yaml`：

```yaml
# 預設幣別
default_currency: TWD

# 預設帳本路徑
default_book: ~/Documents/my_finance.gnucash
```

帳本路徑優先順序：`--book` 參數 > `GNUCASH_BOOK` 環境變數 > 配置文件

## 使用方式

### 科目管理

```bash
# 列出所有科目（樹狀結構）
gcash -b my.gnucash accounts list

# JSON 格式（適合 AI Agent 解析）
gcash -b my.gnucash accounts list --format json

# 按類型篩選
gcash -b my.gnucash accounts list --type EXPENSE

# 新增科目
gcash -b my.gnucash accounts create --name "餐飲" --type EXPENSE --parent "Expenses"
gcash -b my.gnucash accounts create --name "美金帳戶" --type BANK --parent "Assets" --currency USD
```

### 記賬

```bash
# 基本記賬（錢包付 150 元吃午餐）
gcash -b my.gnucash tx add \
  -d "午餐" \
  --debit "90_費用:用餐:正餐 150" \
  --credit "資産:A0現金:錢包 150"

# 指定日期
gcash -b my.gnucash tx add \
  -d "午餐" \
  --debit "90_費用:用餐:正餐 150" \
  --credit "資産:A0現金:錢包 150" \
  --date 2026-03-30

# 多幣別記賬：從 USD 帳戶付 30 USD（折合 930 TWD）的餐費
gcash -b my.gnucash tx add \
  -d "美金消費" \
  --debit "90_費用:用餐:正餐 930" \
  --credit "資産:美金帳戶 930 USD 30"

# 查看最近交易
gcash -b my.gnucash tx list

# 查詢特定科目的交易
gcash -b my.gnucash tx list --account "90_費用:用餐:正餐" --from 2026-01-01 --to 2026-03-31

# JSON 格式輸出
gcash -b my.gnucash tx list --format json
```

### Agent 專用：透過 JSON 檔案記賬

在單機自動化管線（CI、本地 Docker、Agent 同機）中，命令列傳遞 CJK 字元可能遇到編碼問題。  
可改用 `--file` 選項，將交易參數寫入 JSON 檔案後傳入：

```bash
gcash -b my.gnucash tx add --file tx.json --format json
```

### 跨機器協作：遠端 Server Agent 操作本地帳本

如果您遇到 **「Agent 和 Docker 在遠端 Server，而 GnuCash 在本地電腦」** 的情境，強烈警告：**絕對不要透過 SMB/網路硬碟掛載 SQLite**，這會導致 GnuCash 資料庫永久損毀（SQLite 不支援網路鎖定）。

我們提供兩種架構來解決遠端控制問題：

#### 方案 A：升級為資料庫連線 (PostgreSQL) — 【最強烈推薦】
GnuCash 官方原生支援關聯式資料庫。將帳本放在 Server 端資料庫，兩邊利用網路連線讀寫，從根本解決鎖死與檔案同步問題。

1. **部署 Postgres**：使用專案提供的 `docker-compose.yml` 在 Server 啟動資料庫 `docker compose up -d`。
2. **轉移帳本**：打開本地電腦 GnuCash GUI -> 另存新檔 -> 選擇「資料庫連線」 -> 輸入 Server IP、帳號 (`gnucash`)、密碼。
3. **Agent 呼叫**：在 Server 上設定 `GNUCASH_BOOK` (或放在 config.yaml) 後，透過新的 `docker-gcash.sh` 來呼叫 CLI。

> [!TIP]
> **🛡️ Agent 防呆退回機制 (Database Rollback) & Web 控制面板**
>
> 當您的 `GNUCASH_BOOK` 為 `postgresql://...` 且發生任何寫入動作（`tx add`, `accounts create` 等）前，系統會自動將資料庫備份到 `./.backups/`。
> 
> **🖥️ 使用 Web UI 一鍵還原 (推薦)**
> 當您執行 `docker compose up -d` 啟動 PostgreSQL 的同時，我們已經設定讓 `gnucash-cli` 的 Web UI 一併啟動了！
> 1. 您只需打開瀏覽器至 Server 的 IP：`http://<Server_IP>:8000/ui/backups`
> 2. 從精美的清單中挑選動作前的備份檔案，點擊「還原」即可瞬間倒回完美帳本狀態！
> 
> **💻 使用 CLI 還原**
> 您也可以透過終端機執行：`./docker-gcash.sh db list-backups` 與 `./docker-gcash.sh db restore --file .backups/xxx.sql` 來手動處理。

#### 方案 B：本地輕量 WEB API (FastAPI) — 【不用轉移資料庫的折衷方案】
如果堅持要將 SQLite 檔案留在本地電腦：
1. 在本地電腦安裝本專案的 Web 相依 (`pip install .[api]`) 或手動補齊 `fastapi`, `uvicorn`。
2. 配置 API Key（強烈建議）：
   設定環境變數 `GNUCASH_API_KEY=your-secret-key` 或在 `~/.gnucash-cli/config.yaml` 寫入 `api_key: your-secret-key`。
   若未設定，系統將處於無認證的開發模式。
3. 在本地終端機啟動：
   ```bash
   gcash -b my.gnucash serve --port 8000
   ```
4. 利用隧道工具 (如 Tailscale 或 Ngrok) 讓 Server 連到本地的 `8000` port。
5. **遠端 Agent 呼叫方法**：Agent 改為發送 HTTP POST 請求，並附上 `X-API-Key` 標頭：
   ```bash
   curl -X POST "http://<您的本地IP>:8000/api/tx/add" \
        -H "Content-Type: application/json" \
        -H "X-API-Key: your-secret-key" \
        -d '{"description": "午餐", "debits": ["90_費用:用餐 150"], "credits": ["資産:現金 150"]}'
   ```

### 多幣別記賬說明

多幣別的 split 格式：`"Account value [CURRENCY [quantity]]"`

| 格式 | 說明 |
|------|------|
| `"Account 100"` | 單幣別，value=100，quantity=100 |
| `"Account 930 USD 30"` | 多幣別，交易價值=930（交易幣別），實際=30 USD |

### 幣別管理

```bash
# 列出帳本中的幣別
gcash -b my.gnucash currencies list

# 新增幣別
gcash -b my.gnucash currencies add --code USD
gcash -b my.gnucash currencies add --code JPY

# 更新匯率（從 open.er-api.com 取得，支援 150+ 幣別含 TWD）
gcash -b my.gnucash currencies update-prices
gcash -b my.gnucash currencies update-prices --base USD
```

## 全局選項

| 選項 | 說明 |
|------|------|
| `--book`, `-b` | 指定 GnuCash 帳本路徑 |
| `--config` | 指定配置文件路徑 |
| `--version` | 顯示版本 |
| `--help` | 顯示說明 |

---

## 🤖 給 AI Agent 的整合指南 (MCP 支援)

本專案支援最新的 **Model Context Protocol (MCP)**。相較於讓 Agent 自己組合指令、掛載檔案，MCP 是目前最頂級且原生的整合方式。只要將本專案以 MCP Server 掛載給 Agent，Agent 就能直接調用完整的 `gnucash_add_transaction` 等原生 Tools，同時享有全自動資料庫備份等保護！

### 如何讓 Agent 接上 GnuCash MCP Server？

如果您使用支援 MCP 的框架 (例如 OpenClaw, Claude Desktop, 或 Cursor)：

設定它們的 `mcpServers` 組態檔（在此以連接同台 Server 上的 Docker 為例）：

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
        "gnucash-cli:latest",
        "gcash",
        "mcp"
      ]
    }
  }
}
```

> **原理**：這會啟動一個拋棄式的 CLI 容器，並透過 Standard I/O (stdio) 建立標準安全的 MCP 通道，Agent 從此就能透過標準化的 Tools Schema，輕易地對您的 PostgreSQL 帳本操作，過程完全不用撰寫與維護 Shell Script！

## 輸出格式

所有命令都支持 `--format table`（預設，人類可讀）和 `--format json`（適合 Agent 解析）。

## 依賴

- Python ≥ 3.9
- piecash ≥ 1.2.0
- click ≥ 8.0
- rich ≥ 13.0
- pyyaml ≥ 6.0
- requests ≥ 2.28.0
