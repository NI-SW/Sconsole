---
name: sconsole-intercom
description: "Sconsole Agent 间通信 — 通过共享卷发现、发送和接收消息"
version: 1.0.0
author: Sconsole
tags: [sconsole, intercom, agent-communication, messaging]
platforms: [linux]
---

# Sconsole Agent 间通信 (Intercom)

使 Sconsole 项目内部署的 agent 可以通过共享卷 (`/agent/volume`) 互相发现和通信。

## 工作原理

```
┌─────────────────────────────────────────────┐
│  宿主机: Sconsole/container_volume/          │
│  ├── registry/          ← agent 注册信息     │
│  │   ├── 36.json        ← agent #36 的元数据 │
│  │   └── 37.json        ← agent #37 的元数据 │
│  └── mailbox/           ← 消息信箱           │
│      ├── 36/inbox/      ← #36 的收件箱       │
│      └── 37/inbox/      ← #37 的收件箱       │
│          ↓ 容器挂载为 /agent/volume          │
└─────────────────────────────────────────────┘
```

所有 agent 容器共享同一个目录，通过文件系统进行发现和消息传递。

## 可用命令

### 发现其他 agent

```bash
python3 /agent/skills/sconsole-intercom/scripts/discover.py
```

列出当前注册的所有 agent（排除自身），输出 JSON。

### 发送消息

```bash
python3 /agent/skills/sconsole-intercom/scripts/message.py send <target_id> "<content>"
```

向指定 agent 发送消息。消息写入目标的收件箱。

### 检查收件箱

```bash
python3 /agent/skills/sconsole-intercom/scripts/message.py check
```

查看自己的收件箱，列出所有未读消息。

### 读取消息

```bash
python3 /agent/skills/sconsole-intercom/scripts/message.py read <message_id>
```

读取指定消息的完整内容。

### 清理已读消息

```bash
python3 /agent/skills/sconsole-intercom/scripts/message.py clean
```

清空自己的收件箱。

### 上传文件到宿主机

```bash
python3 /agent/skills/sconsole-intercom/scripts/upload.py <workspace_id> <file_path> [filename]
```

将 agent 容器内的文件上传到宿主机工作空间目录，上传后的文件可通过 Sconsole 前端浏览器下载，或由其他 agent 访问。

**参数说明：**
- `<workspace_id>` — 工作空间 ID（即 instance_id）
- `<file_path>` — 容器内的文件绝对路径
- `[filename]` — 可选，自定义上传后的文件名，默认使用原文件名

**上传目标：** 文件保存在宿主机 `~/.sconsole/agent_upload/<workspace_id>/` 目录下。

**工作原理：**
1. 读取容器内指定文件
2. 通过 multipart/form-data POST 到 Sconsole 服务端的 `/api/workspaces/{id}/upload` 端点
3. 服务端保存到宿主机目录
4. Sconsole 前端工作空间页面可通过「📁 文件」按钮浏览和下载

**示例：**
```bash
# 将分析结果上传到工作空间 60
python3 /agent/skills/sconsole-intercom/scripts/upload.py 60 /tmp/analysis_result.json

# 上传并自定义文件名
python3 /agent/skills/sconsole-intercom/scripts/upload.py 60 /tmp/output.csv results_20260604.csv
```

> **注意：** 需确保 Sconsole 服务端可从容器内访问。默认通过 `SCONSOLE_SERVER` 环境变量确定地址，备用为 `http://host.containers.internal:58091`。

## 使用示例

```
# Agent A (instance_id=36) 发现其他 agent
$ python3 discover.py
[{"instance_id": 37, "model_name": "deepseek-v4-pro", "registered_at": "..."}]

# Agent A 向 Agent B 发送消息
$ python3 message.py send 37 "请帮我分析 /agent/volume/data.csv"

# Agent B 检查收件箱
$ python3 message.py check
[{"id": "msg_001", "from": 36, "content": "请帮我分析 /agent/volume/data.csv", ...}]

# Agent B 回复 (通过发送消息给 Agent A)
$ python3 message.py send 36 "分析完成，结果在 /agent/volume/result.json"
```

## 通信协议

每条消息是一个 JSON 文件，格式：

```json
{
  "id": "msg_1717000000_abc123",
  "from": 36,
  "to": 37,
  "content": "消息内容",
  "timestamp": "2026-05-29T12:00:00",
  "reply_to": null
}
```

## 注册机制

Agent 启动时自动将元数据写入 `/agent/volume/registry/{instance_id}.json`：

```json
{
  "instance_id": 36,
  "api_key": "ecb350...",
  "api_port": 18000,
  "model_name": "deepseek-v4-pro",
  "registered_at": "2026-05-29T12:00:00"
}
```

Agent 停止时应清理自己的注册信息（容器销毁时自动随共享卷持久化，可手动清理）。
