@echo off
REM =====================================================================
REM GnuCash CLI - Docker Wrapper Script for AI Agents (e.g. OpenClaw)
REM =====================================================================
REM 此腳本會將「當前命令提示字元所在的目錄」掛載到 Docker 內部的 /workspace。
REM Agent 可以直接在此目錄下產出 data.json，並呼叫此腳本。
REM 所有相對路徑都會無縫銜接。
REM
REM 用法:
REM   docker-gcash.bat [指令]
REM 
REM 範例:
REM   docker-gcash.bat tx add --file tx_data.json
REM =====================================================================

REM 檢查 Docker 是否安裝
docker --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [Error] Docker is not installed or not running.
    exit /b 1
)

REM 執行 Docker 容器
REM -rm: 執行完畢自動刪除容器
REM -i: 保持標準輸入開啟
REM -v "%cd%:/workspace": 將本地當前目錄掛載到 /workspace
REM -w /workspace: 將工作目錄設為 /workspace
REM gnucash-cli:latest: 映像檔名稱

docker run --rm -i ^
  -v "%cd%:/workspace" ^
  -w "/workspace" ^
  gnucash-cli:latest %*
