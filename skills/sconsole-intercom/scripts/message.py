#!/usr/bin/env python3
"""
Sconsole Intercom - Message Send / Check / Read / Clean
用法:
  message.py send <target_id> "<content>"
  message.py check
  message.py read <message_id>
  message.py clean
"""
import os
import json
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

# 共享卷路径
VOLUME_DIR = os.getenv("AGENT_VOLUME_DIR", "/agent/volume")
MAILBOX_DIR = os.path.join(VOLUME_DIR, "mailbox")

# 自身 ID
MY_ID = os.getenv("AGENT_INSTANCE_ID", "")


def _ensure_dirs(*paths: str):
    for p in paths:
        os.makedirs(p, exist_ok=True)


def _generate_msg_id() -> str:
    ts = int(time.time())
    short = uuid.uuid4().hex[:8]
    return f"msg_{ts}_{short}"


def send_message(target_id: str, content: str) -> dict:
    """向目标 agent 发送消息."""
    if not target_id:
        return {"error": "target_id is required"}
    if not content.strip():
        return {"error": "content is required"}
    if not MY_ID:
        return {"error": "AGENT_INSTANCE_ID not set"}

    target_inbox = os.path.join(MAILBOX_DIR, str(target_id), "inbox")
    _ensure_dirs(target_inbox)

    msg = {
        "id": _generate_msg_id(),
        "from": int(MY_ID),
        "to": int(target_id),
        "content": content.strip(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "reply_to": None,
    }

    filepath = os.path.join(target_inbox, f"{msg['id']}.json")
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(msg, f, indent=2, ensure_ascii=False)

    return {"status": "sent", "message_id": msg["id"], "to": int(target_id)}


def check_inbox() -> list[dict]:
    """检查收件箱."""
    if not MY_ID:
        return []

    inbox = os.path.join(MAILBOX_DIR, str(MY_ID), "inbox")
    if not os.path.isdir(inbox):
        return []

    messages = []
    for fname in sorted(os.listdir(inbox)):
        if not fname.endswith(".json"):
            continue
        filepath = os.path.join(inbox, fname)
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                msg = json.load(f)
        except (json.JSONDecodeError, IOError):
            continue

        messages.append({
            "id": msg["id"],
            "from": msg["from"],
            "content": msg["content"][:200] + ("..." if len(msg["content"]) > 200 else ""),
            "timestamp": msg["timestamp"],
        })

    return messages


def read_message(msg_id: str) -> dict:
    """读取完整消息内容."""
    if not MY_ID:
        return {"error": "AGENT_INSTANCE_ID not set"}

    inbox = os.path.join(MAILBOX_DIR, str(MY_ID), "inbox")
    filepath = os.path.join(inbox, f"{msg_id}.json")

    if not os.path.exists(filepath):
        return {"error": f"message {msg_id} not found"}

    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def clean_inbox() -> dict:
    """清空收件箱."""
    if not MY_ID:
        return {"error": "AGENT_INSTANCE_ID not set"}

    inbox = os.path.join(MAILBOX_DIR, str(MY_ID), "inbox")
    count = 0
    if os.path.isdir(inbox):
        for fname in os.listdir(inbox):
            if fname.endswith(".json"):
                os.remove(os.path.join(inbox, fname))
                count += 1

    return {"status": "cleaned", "removed": count}


# ─── CLI ──────────────────────────────────────────────────────────────

def usage():
    print(__doc__.strip())
    sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        usage()

    cmd = sys.argv[1]

    if cmd == "send":
        if len(sys.argv) < 4:
            usage()
        target = sys.argv[2]
        content = sys.argv[3]
        result = send_message(target, content)
        print(json.dumps(result, indent=2, ensure_ascii=False))

    elif cmd == "check":
        messages = check_inbox()
        print(json.dumps(messages, indent=2, ensure_ascii=False))

    elif cmd == "read":
        if len(sys.argv) < 3:
            usage()
        msg_id = sys.argv[2]
        result = read_message(msg_id)
        print(json.dumps(result, indent=2, ensure_ascii=False))

    elif cmd == "clean":
        result = clean_inbox()
        print(json.dumps(result, indent=2, ensure_ascii=False))

    else:
        usage()
