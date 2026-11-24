#!/usr/bin/env bash
# Starts the dashboard + API. The 5 MCP servers are launched automatically as stdio subprocesses.
cd "$(dirname "$0")"
pip install -r requirements.txt --quiet 2>/dev/null || true
echo "Open http://localhost:${PORT:-5000}"
python3 backend/app.py
