#!/bin/bash
# =====================================================================
# GnuCash CLI - Docker Wrapper Script for AI Agents (Linux/Mac)
# =====================================================================
# 此腳本設計給在 Server 上運行的 AI Agent (如 OpenClaw) 呼叫。
# 它會將「當前命令提示字元所在的目錄」掛載到 Docker 內部的 /workspace。
#
# 注意：它會自動建立 .backups 目錄供安全快照使用，請勿刪除此目錄。
#
# 用法:
#   ./docker-gcash.sh [指令]
# 
# 範例 (配合 PostgreSQL):
#   ./docker-gcash.sh -b postgresql://user:pass@IP:5432/db tx add --file tx.json
# =====================================================================

if ! command -v docker &> /dev/null; then
    echo "[Error] Docker is not installed or not running."
    exit 1
fi

# Ensure backups directory exists
mkdir -p "$(pwd)/.backups"

# 執行 Docker 容器
# -rm: 執行完畢自動刪除容器
# -i: 保持標準輸入開啟
# -v "$(pwd):/workspace": 將本地當前目錄掛載到 /workspace
# --network host: 允許 Agent 輕易存取本機 Postgres 資料庫 (適用於 Local DB)

docker run --rm -i \
  --network host \
  -v "$(pwd):/workspace" \
  -w "/workspace" \
  gnucash-cli:latest "$@"
