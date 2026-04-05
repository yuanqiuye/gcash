#!/bin/bash
# =====================================================================
# GnuCash CLI - Docker Wrapper Script for AI Agents (Linux/Mac)
# =====================================================================
# This script is designed to be called by AI Agents (e.g. OpenClaw)
# running on a server. It mounts the current working directory into
# the Docker container at /workspace.
#
# Note: It automatically creates a .backups directory for safety snapshots.
# Do not delete this directory.
#
# Usage:
#   ./docker-gcash.sh [arguments]
# 
# Example (with PostgreSQL):
#   ./docker-gcash.sh -b postgresql://user:pass@IP:5432/db tx add --file tx.json
# =====================================================================

if ! command -v docker &> /dev/null; then
    echo "[Error] Docker is not installed or not running."
    exit 1
fi

# Ensure backups directory exists
mkdir -p "$(pwd)/.backups"

# Run Docker container
# --rm: Auto-delete container after execution
# -i: Keep stdin open
# -v "$(pwd):/workspace": Mount current directory to /workspace
# --network host: Allow Agent to access local Postgres database (for Local DB)

docker run --rm -i \
  --network host \
  -v "$(pwd):/workspace" \
  -w "/workspace" \
  gnucash-cli:latest "$@"
