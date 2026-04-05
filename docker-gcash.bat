@echo off
REM =====================================================================
REM GnuCash CLI - Docker Wrapper Script for AI Agents (Windows)
REM =====================================================================
REM This script mounts the current command prompt directory into the
REM Docker container at /workspace.
REM Agents can produce data.json in this directory and call this script.
REM All relative paths will work seamlessly.
REM
REM Usage:
REM   docker-gcash.bat [arguments]
REM 
REM Example:
REM   docker-gcash.bat tx add --file tx_data.json
REM =====================================================================

REM Check if Docker is installed
docker --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [Error] Docker is not installed or not running.
    exit /b 1
)

REM Run Docker container
REM --rm: Auto-delete container after execution
REM -i: Keep stdin open
REM -v "%cd%:/workspace": Mount current directory to /workspace
REM -w /workspace: Set working directory to /workspace
REM gnucash-cli:latest: Image name

docker run --rm -i ^
  -v "%cd%:/workspace" ^
  -w "/workspace" ^
  gnucash-cli:latest %*
