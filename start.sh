#!/bin/bash
# Sconsole - Main Startup Script
# Starts the server and optionally a local node.
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "========================================="
echo "  Sconsole - Agent Management Console"
echo "========================================="

# Check Python
if ! command -v python3 &>/dev/null; then
    echo "ERROR: python3 is required"
    exit 1
fi

# Setup virtual environment if needed
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi

# Activate virtual environment
source .venv/bin/activate

# Install dependencies
echo "Installing dependencies..."
pip install -r requirements.txt --quiet

# Initialize database (optional - will try on server start)
echo ""
echo "Starting Sconsole server..."

# Start the server
python3 -m server.main "$@"
