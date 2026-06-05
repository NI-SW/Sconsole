#!/usr/bin/env python3
"""
Sconsole Intercom - Agent Discovery
列出共享卷中注册的所有 agent（排除自身）。
"""
import os
import json
import sys
from pathlib import Path

# 共享卷路径
VOLUME_DIR = os.getenv("AGENT_VOLUME_DIR", "/agent/volume")
REGISTRY_DIR = os.path.join(VOLUME_DIR, "registry")

# 自身 ID
MY_ID = os.getenv("AGENT_INSTANCE_ID", "")


def discover() -> list[dict]:
    """发现所有已注册的 agent."""
    if not os.path.isdir(REGISTRY_DIR):
        return []

    agents = []
    for fname in sorted(os.listdir(REGISTRY_DIR)):
        if not fname.endswith(".json"):
            continue
        filepath = os.path.join(REGISTRY_DIR, fname)
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                meta = json.load(f)
        except (json.JSONDecodeError, IOError):
            continue

        agent_id = str(meta.get("instance_id", ""))
        # 排除自身
        if MY_ID and agent_id == str(MY_ID):
            continue

        agents.append({
            "instance_id": meta.get("instance_id"),
            "model_name": meta.get("model_name", ""),
            "api_port": meta.get("api_port", 0),
            "registered_at": meta.get("registered_at", ""),
        })

    return agents


if __name__ == "__main__":
    result = discover()
    print(json.dumps(result, indent=2, ensure_ascii=False))
