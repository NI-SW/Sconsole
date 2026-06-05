#!/bin/bash
# Sconsole - Build Docker Image
set -e
cd "$(dirname "$0")/.."

# Auto-detect container runtime (podman or docker)
CONTAINER_RUNTIME="docker"
if command -v podman &>/dev/null; then
    CONTAINER_RUNTIME="podman"
fi

echo "Building sconsole-agent Docker image with ${CONTAINER_RUNTIME}..."
${CONTAINER_RUNTIME} build -t sconsole-agent:latest -f docker/Dockerfile .
echo "Build complete: sconsole-agent:latest"
