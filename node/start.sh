#!/bin/bash
# Sconsole Node - Startup Script
# Installs dependencies and launches the node agent.

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "=== Sconsole Node Setup ==="

# Check Python
if ! command -v python3 &>/dev/null; then
    echo "ERROR: python3 is required"
    exit 1
fi

# Setup virtual environment (shared with main project)
if [ ! -d "$PROJECT_DIR/.venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$PROJECT_DIR/.venv"
fi
source "$PROJECT_DIR/.venv/bin/activate"

# Install dependencies
echo "Installing dependencies..."
pip install -r "$PROJECT_DIR/requirements.txt" --quiet

# Check container runtime
if command -v podman &>/dev/null; then
    echo "Using podman as container runtime"
    export DOCKER_HOST="unix:///tmp/podman-user.sock"
elif command -v docker &>/dev/null; then
    echo "Using docker as container runtime"
else
    echo "ERROR: docker or podman is required"
    exit 1
fi

# Set default environment
export SCONSOLE_SERVER="${SCONSOLE_SERVER:-ws://localhost:58091}"
export SCONSOLE_NODE_ID="${SCONSOLE_NODE_ID:-$(hostname)}"
# Bypass proxy for local WebSocket connections
export no_proxy="${no_proxy:-localhost,127.0.0.1,::1}"

echo "Starting node agent..."
echo "  Server: $SCONSOLE_SERVER"
echo "  Node ID: $SCONSOLE_NODE_ID"

# Launch the node agent
exec python3 "$SCRIPT_DIR/agent.py" "$@"
