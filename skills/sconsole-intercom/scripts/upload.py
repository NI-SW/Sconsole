#!/usr/bin/env python3
"""
Sconsole Intercom - File Upload
用法:
  upload.py <workspace_id> <file_path> [filename]

从 agent 容器内上传文件到宿主机工作空间目录。
文件保存在 ~/.sconsole/agent_upload/<workspace_id>/ 下。
"""
import os
import sys
import urllib.request
import urllib.error

# sconsole server 地址（从环境变量或参数推断）
SCONSOLE_URL = os.getenv("SCONSOLE_PROXY", os.getenv("SCONSOLE_SERVER", ""))
if not SCONSOLE_URL:
    # fallback: assume sconsole is reachable at the gateway host
    SCONSOLE_URL = "http://host.containers.internal:58091"

# strip trailing slash
SCONSOLE_URL = SCONSOLE_URL.rstrip("/")


def upload(workspace_id: str, file_path: str, filename: str = ""):
    if not os.path.isfile(file_path):
        print(f"ERROR: file not found: {file_path}")
        sys.exit(1)

    name = filename or os.path.basename(file_path)
    url = f"{SCONSOLE_URL}/api/workspaces/{workspace_id}/upload"

    boundary = "----SconsoleUploadBoundary"
    with open(file_path, "rb") as f:
        data = f.read()

    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{name}"\r\n'
        f"Content-Type: application/octet-stream\r\n\r\n"
    ).encode("utf-8") + data + f"\r\n--{boundary}--\r\n".encode("utf-8")

    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Content-Length": str(len(body)),
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = resp.read().decode("utf-8")
            print(f"OK: {result}")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"ERROR HTTP {e.code}: {body}")
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    ws_id = sys.argv[1]
    path = sys.argv[2]
    fname = sys.argv[3] if len(sys.argv) > 3 else ""
    upload(ws_id, path, fname)
