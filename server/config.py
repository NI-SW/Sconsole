"""
Sconsole Server - Configuration
"""
import os

# OceanBase MySQL configuration
DB_CONFIG = {
    "host": os.getenv("SCONSOLE_DB_HOST", "192.168.34.65"),
    "port": int(os.getenv("SCONSOLE_DB_PORT", "3306")),
    "user": os.getenv("SCONSOLE_DB_USER", "root"),
    "password": os.getenv("SCONSOLE_DB_PASS", "Info@1234"),
    "database": os.getenv("SCONSOLE_DB_NAME", "SCL_sconsole"),
}

# Server configuration
SERVER_HOST = os.getenv("SCONSOLE_HOST", "0.0.0.0")
SERVER_PORT = int(os.getenv("SCONSOLE_PORT", "58091"))

# Proxy configuration
PROXY_URL = os.getenv("SCONSOLE_PROXY", "http://192.168.34.4:7890")

# Docker image for agents
AGENT_DOCKER_IMAGE = os.getenv("SCONSOLE_AGENT_IMAGE", "sconsole-agent:latest")

# Shared directories
SHARED_DIR = os.getenv("SCONSOLE_SHARED_DIR", os.path.join(os.path.expanduser("~"), ".sconsole", "shared"))
AGENT_UPLOAD_DIR = os.getenv("SCONSOLE_UPLOAD_DIR", os.path.join(os.path.expanduser("~"), ".sconsole", "agent_upload"))

# Agent templates directory
TEMPLATES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "examples",
)
