# Sconsole 工作空间模块 — 技术说明

> 版本: v3 | 更新日期: 2026-06-07

---

## 1. 概述

工作空间（Workspace）是 Sconsole 的核心组织单元。每个工作空间包含一组 Agent 实例（1 个主控 Master + N 个工作 Agent），它们共享同一容器运行环境，通过 Hermes Agent 框架提供 AI 对话与工具调用能力。

**核心数据模型关系:**

```
SCL_workspaces (1) ──< SCL_instance_agents (N)  >── SCL_agent_configs
     工作空间              Agent 实例                   Agent 配置模板
        │                      │
        │                      ├── SCL_agent_conversations
        │                      │       对话记录
        │                      │
        │                      └── SCL_agent_messages_v3
        │                              消息记录
        │
        └── SCL_nodes (关联)
                运行节点
```

---

## 2. 数据库表结构

### 2.1 SCL_workspaces — 工作空间

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | int | PK, AUTO_INCREMENT | 工作空间 ID |
| name | varchar(255) | NOT NULL | 名称 |
| description | text | | 描述 |
| node_id | varchar(255) | NOT NULL, IDX | 部署节点 ID |
| status | enum('pending','running','stopped','error') | NOT NULL, IDX | 状态 |
| created_at | datetime | NOT NULL | 创建时间 |
| updated_at | datetime | NOT NULL | 更新时间 |

### 2.2 SCL_instance_agents — Agent 实例

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | int | PK, AUTO_INCREMENT | Agent 实例 ID |
| instance_id | int | NOT NULL, IDX | 所属工作空间 ID |
| config_id | int | NOT NULL, IDX | 关联配置模板 ID |
| name | varchar(255) | NOT NULL | Agent 名称 |
| description | text | | 描述 |
| role | varchar(32) | NOT NULL, DEFAULT 'worker' | 角色: master/worker |
| container_id | varchar(255) | NOT NULL | 容器 ID |
| host_port | int | NOT NULL, DEFAULT 0 | 宿主机端口映射 |
| api_key | varchar(128) | NOT NULL | 认证密钥 |
| agent_port | int | NOT NULL, DEFAULT 0 | 容器内端口 |
| status | enum('pending','deploying','running','stopped','error') | NOT NULL, IDX | 状态 |
| created_at | datetime | NOT NULL | 创建时间 |
| updated_at | datetime | NOT NULL | 更新时间 |

### 2.3 SCL_agent_configs — Agent 配置模板

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | int | PK, AUTO_INCREMENT | 配置 ID |
| name | varchar(255) | NOT NULL, IDX | 名称 |
| soul_file | text | | SOUL 提示词文件内容 |
| memory_file | text | | MEMORY 文件内容 |
| tech_docs | text | | 技术文档内容 |
| model_url | varchar(512) | NOT NULL | 模型 API 地址 |
| model_api_key | varchar(512) | NOT NULL | 模型 API 密钥 |
| model_name | varchar(255) | NOT NULL | 模型名称 |
| model_provider | varchar(64) | NOT NULL | 供应商 (openai/deepseek/kimi等) |
| proxy | varchar(512) | NOT NULL | 代理地址 |
| skills | json | | 技能列表 |
| extra_env | json | | 额外环境变量 |
| attached_files | json | | 附件文件列表 |
| created_at | datetime | NOT NULL | 创建时间 |
| updated_at | datetime | NOT NULL | 更新时间 |

### 2.4 SCL_agent_conversations — 对话记录

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | int | PK, AUTO_INCREMENT | 记录 ID |
| instance_id | int | NOT NULL, IDX | 工作空间 ID |
| agent_id | int | NOT NULL, IDX | Agent ID |
| conversation_id | varchar(128) | NOT NULL, IDX | 会话 ID |
| user_input | text | | 用户输入 |
| output | json | | Agent 输出 (结构化) |
| usage_info | json | | Token 用量 |
| status | varchar(32) | NOT NULL, DEFAULT 'completed' | 状态: pending/streaming/completed/error |
| error_msg | text | | 错误信息 |
| created_at | datetime | NOT NULL, IDX | 创建时间 |

### 2.5 SCL_agent_messages_v3 — 消息记录

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | int | PK, AUTO_INCREMENT | 消息 ID |
| instance_agent_id | int | NOT NULL, IDX | Agent 实例 ID |
| direction | enum('user','agent','system') | NOT NULL | 方向 |
| content | text | NOT NULL | 消息内容 |
| message_type | varchar(50) | NOT NULL | 消息类型 |
| created_at | datetime | NOT NULL, IDX | 创建时间 |

### 2.6 其他表

- **SCL_agent_messages** — 消息记录旧版 (v2)，保留兼容
- **SCL_nodes** — 节点信息 (node_id, hostname, ip_address, status, docker_version, cpu_count, memory_mb)
- **SCL_skills** — 技能库 (name, version, source, description)

---

## 3. API 接口

### 3.1 工作空间 CRUD

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/workspaces | 列出所有工作空间 (可选 ?status=running 过滤) |
| POST | /api/workspaces | 创建工作空间 (需 name, node_id; 自动创建 Master Agent) |
| GET | /api/workspaces/{id} | 获取工作空间详情 |
| PUT | /api/workspaces/{id} | 更新工作空间 (name, description, status) |
| DELETE | /api/workspaces/{id} | 删除工作空间 (级联删除 Agent 和容器) |

**创建工作空间请求示例:**

```json
{
  "name": "my-workspace",
  "node_id": "node-1",
  "description": "示例工作空间",
  "config_ids": [1, 2]
}
```

**工作空间详情返回:**

```json
{
  "id": 106,
  "name": "SQL_OBJECT_TRANSFORMER",
  "description": "",
  "node_id": "node-1",
  "status": "running",
  "master_agent_id": 193,
  "agent_count": 3,
  "created_at": "2026-06-05 05:29:00",
  "updated_at": "2026-06-07 06:30:00"
}
```

### 3.2 Agent 管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/workspaces/{id}/agents | 列出工作空间下所有 Agent |
| POST | /api/workspaces/{id}/agents | 添加 Agent (需 config_id, name) |
| GET | /api/workspaces/{id}/agents/{aid} | 获取 Agent 详情 |
| POST | /api/workspaces/{id}/agents/{aid}/deploy | 部署 Agent 容器 |
| POST | /api/workspaces/{id}/agents/{aid}/stop | 停止 Agent 容器 |
| DELETE | /api/workspaces/{id}/agents/{aid} | 删除 Agent |

**Agent 详情返回:**

```json
{
  "id": 195,
  "instance_id": 106,
  "config_id": 1,
  "name": "sql_transformer",
  "description": "",
  "role": "worker",
  "container_id": "4f861e26d268...",
  "host_port": 18001,
  "api_key": "f7d1d4a7ab60...",
  "agent_port": 5891,
  "status": "running",
  "created_at": "2026-06-05 05:29:00"
}
```

### 3.3 Agent 交互

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/workspaces/{id}/agents/{aid}/logs | 获取容器日志 (?tail=200) |
| GET | /api/workspaces/{id}/agents/{aid}/messages | 获取消息记录 (?limit=100) |
| GET | /api/workspaces/{id}/agents/{aid}/conversations | 获取对话历史 (?limit=50) |
| POST | /api/workspaces/{id}/agents/{aid}/chat | 单 Agent 对话 |

### 3.4 工作空间级接口

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /api/workspaces/{id}/chat | 与 Master Agent 对话 |
| GET | /api/workspaces/{id}/activity | 获取活动流 |
| GET | /api/workspaces/{id}/conversations | 获取全量对话记录 |
| GET | /api/workspaces/{id}/config | 获取工作空间配置 |

### 3.5 文件管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/workspaces/{id}/files | 列出文件 |
| GET | /api/workspaces/{id}/files/{filename} | 下载文件 |
| POST | /api/workspaces/{id}/upload | 上传文件 (multipart) |
| DELETE | /api/workspaces/{id}/files/{filename} | 删除文件 |
| POST | /api/workspaces/{id}/agents/{aid}/upload-file | 上传文件到 Agent |

### 3.6 核心通信端点

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /api/communicate | 流式/非流式 Agent 通信 (默认流式) |

**请求参数:**

```json
{
  "agent_port": 18001,
  "api_key": "f7d1d4a7ab604053ad055a784d32e383",
  "input": "你好",
  "stream": true,
  "conversation_id": "conv_1780812582783_abc"
}
```

详见 [第 5 节: 通信架构](#5-通信架构)。

---

## 4. 服务层

`AgentService` 类 (server/services/agent_service.py) 提供全部业务逻辑，共 32 个静态方法。

### 4.1 核心方法

| 方法 | 签名 | 说明 |
|------|------|------|
| create_instance | `(name, node_id, description="") -> dict` | 创建工作空间 + 自动创建 Master Agent |
| create_instance_agent | `(instance_id, config_id, name, description="") -> int` | 添加 Agent 实例 |
| get_master_agent | `(instance_id) -> Optional[dict]` | 获取 Master Agent |
| list_instance_agents | `(instance_id, status=None) -> List[dict]` | 列出 Agent |
| update_agent_status | `(agent_id, status, container_id=None, ...)` | 更新 Agent 状态 |
| update_master_context | `(instance_id) -> Optional[dict]` | 更新 Master 上下文（收集所有 worker 信息写入 SOUL） |

### 4.2 对话管理方法

| 方法 | 签名 | 说明 |
|------|------|------|
| insert_pending_conversation | `(instance_id, agent_id, conversation_id, user_input) -> int` | 插入 pending 记录，返回 record_id |
| update_conversation_record | `(record_id, output, usage_info, status, error_msg="")` | 更新对话记录 |
| get_agent_conversations | `(instance_id, agent_id=0, limit=50) -> List[dict]` | 查询对话历史 |
| get_conversation_detail | `(conv_id) -> Optional[dict]` | 获取单条对话详情 |
| delete_conversation | `(conv_id) -> bool` | 删除对话 |
| delete_conversations_by_conv_id | `(conversation_id) -> int` | 按会话 ID 删除 |

### 4.3 配置方法

| 方法 | 签名 | 说明 |
|------|------|------|
| create_config | `(config: AgentConfig) -> int` | 创建配置 |
| get_config | `(config_id) -> Optional[dict]` | 获取配置 |
| list_configs | `() -> List[dict]` | 列出所有配置 |
| update_config | `(config_id, updates) -> bool` | 更新配置 |
| delete_config | `(config_id) -> bool` | 删除配置 |
| get_attached_files | `(config_id) -> list` | 获取附件列表 |
| update_attached_files | `(config_id, files)` | 更新附件列表 |

---

## 5. 通信架构

### 5.1 架构图

```
                    ┌────────────────────────────────────────────┐
                    │           Sconsole Server (routes.py)      │
                    │                                            │
  Browser           │   sse_stream()    ←──  asyncio.Queue      │   _hermes_drain_task()
  (app.js)          │   (生成器)              (sse_queue)        │   (asyncio.Task)
     │              │       │                    ↑                │       │
     │  fetch POST  │       │ yield chunk        │ put chunk      │       │ 读取 Hermes SSE
     ├─────────────>│       │                    │                │       │
     │              │   StreamingResponse        │                │   httpx.stream
     │<─────────────│       │                    │                │       │
     │  SSE events  │       └────────────────────┘                │       │
     │              │                                             │       │
     │  断开后:      │   生成器停止                                │       │ 继续运行
     │              │                                             │       │ 直到完成
     │              │                                             │       │ 写入DB
     │              └─────────────────────────────────────────────┘       │
     │                                                                    │
     │            重新进入 → 从 DB 加载 streaming/pending 记录            │
     │            Recovery Poll 每3秒刷新 → 文本实时增长                   │
```

### 5.2 请求流程 (POST /api/communicate)

```
1. 验证参数 (agent_port, input, api_key)
2. 通过 agent_port 反查 agent_id + instance_id (SELECT from SCL_instance_agents)
3. 构造 Hermes payload:
     POST http://127.0.0.1:{agent_port}/v1/responses
     Headers: Authorization: Bearer {api_key}
     Body: { input, stream: true, conversation_id, ... }
4. 立即 insert_pending_conversation → DB 记录 status="pending"
5. 根据 stream 参数分两路:
   ├─ stream=false → httpx.post 同步请求 → 更新DB → 返回 JSON
   └─ stream=true  → Queue + Background Task 模式 (默认)
```

### 5.3 流式处理 (Queue + Background Task)

**设计目标:** 客户端断开连接后，后端仍能完整消费 Hermes Agent 的响应并写入数据库。

**实现:**

```python
sse_queue = asyncio.Queue()

async def _hermes_drain_task():
    """后台任务: 消费 Hermes SSE 流 + 更新 DB + 推入队列"""
    async with httpx.AsyncClient(timeout=600.0) as client:
        async with client.stream("POST", hermes_url, ...) as resp:
            async for line in resp.aiter_lines():
                await sse_queue.put(line + "\n")     # 推入队列
                # 解析 SSE 事件，累积 output
                # 每 5 行或 5 秒 flush DB (status="streaming")
            # 流结束 → flush DB (status="completed")
    await sse_queue.put(None)  # 结束信号

async def sse_stream():
    """SSE 生成器: 从队列读取并 yield 给客户端"""
    while True:
        chunk = await sse_queue.get()
        if chunk is None: break
        yield chunk

drain_task = asyncio.create_task(_hermes_drain_task())
return StreamingResponse(sse_stream(), media_type="text/event-stream")
```

**关键特性:**
- `_hermes_drain_task` 是独立 `asyncio.Task`，生命周期不受 SSE 生成器影响
- 客户端断开 → `sse_stream` 生成器收到 `CancelledError` → 退出循环 → `_hermes_drain_task` 继续运行
- 数据库最终被更新为 `completed`，用户重新进入可获取完整回复

### 5.4 SSE 事件类型

| 事件 | 含义 | 前端处理 |
|------|------|----------|
| response.output_item.added | 开始一个输出项 | 显示"调用: xxx" |
| response.output_text.delta | 文本增量 (核心流式事件) | 拼接 fullReply += delta，实时更新 DOM |
| response.output_text.done | 文本输出完成 | 修正最终文本 |
| response.output_item.done | 一个输出项完成 | 显示"整理回复..." |
| response.completed | 整个响应完成 | 移除 pending，标记完成 |
| error | 出错 | 显示错误消息 |

### 5.5 DB 增量刷新策略

```
触发条件 (满足其一):
  - 累积 data: 行数达到 5 的倍数
  - 距上次 flush 超过 5 秒且有新数据

刷新内容:
  - output: 累积的 output_item + 合成的部分 message
  - usage_info: 累积的 token 用量
  - status: "streaming"

最终写入:
  - output: response.completed 中的完整 output
  - usage_info: 最终 usage
  - status: "completed" 或 "error"
```

### 5.6 前端 Recovery Poll 机制

用户退出对话后重新进入，如果有 `streaming`/`pending` 状态的记录：

```javascript
startRecoveryPoll(instanceId, agentId) {
    setInterval(3000ms, async () => {
        // 1. 查询 conversations API
        // 2. 更新 streaming/pending 记录的 DOM 文本
        // 3. 检测 completed 记录 → 更新最终文本 → 移除 data-conv-id
        // 4. 无 in-progress 记录 → 停止轮询
    });
}
```

**DOM 更新方式:** 通过 `data-conv-id` 属性定位消息元素，直接更新 `textContent`，实现原地刷新。

---

## 6. 前端架构

### 6.1 app.js 核心函数

| 函数 | 说明 |
|------|------|
| openAgentChat | 打开 Agent 对话: 获取信息 → 恢复会话 → 加载 DB 历史 → 启动 Recovery Poll |
| closeChatView | 关闭对话: 中止流请求 → 缓存 Agent 信息 → 清理状态 |
| sendChatMessage | 发送消息: fetch POST /api/communicate (stream:true) → ReadableStream 解析 SSE |
| syncConversationFromDB | DB 回查: 查询 conversations → 过滤已显示 → 更新 pending DOM |
| startRecoveryPoll | 恢复轮询: 每 3s 查询 DB → 更新 streaming/pending 消息 → 完成后停止 |

### 6.2 对话状态管理

```javascript
state = {
    activeChatAgentId,       // 当前对话 Agent ID
    activeChatInstanceId,    // 当前工作空间 ID
    chatMessages,            // 消息列表 [{role, content}]
    _chatAgentPort,          // Agent 端口
    _chatAgentApiKey,        // Agent 密钥
    _conversationId,         // 当前会话 ID
    _shownConversationIds,   // 已显示的对话 ID 集合 (避免重复)
    chatPollTimer,           // Recovery Poll 定时器
    _abortController,        // 流式请求中断控制器
}
```

### 6.3 SSE 解析 (非 EventSource)

前端使用 `fetch` + `ReadableStream` 手动解析 SSE，因为 `EventSource` 只支持 GET 请求：

```javascript
const resp = await fetch('/api/communicate', { method: 'POST', body: ... });
const reader = resp.body.getReader();
const decoder = new TextDecoder();

while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    const text = decoder.decode(value, { stream: true });
    // 按 \n\n 切割 SSE 事件块
    // 解析 event: / data: 行
}
```

---

## 7. 配置

### 7.1 服务端配置 (server/config.py)

| 配置项 | 环境变量 | 默认值 | 说明 |
|--------|---------|--------|------|
| DB host | SCONSOLE_DB_HOST | 192.168.34.65 | 数据库主机 |
| DB port | SCONSOLE_DB_PORT | 3306 | 数据库端口 |
| DB user | SCONSOLE_DB_USER | root | 数据库用户 |
| DB password | SCONSOLE_DB_PASS | Info@1234 | 数据库密码 |
| DB name | SCONSOLE_DB_NAME | SCL_sconsole | 数据库名 |
| Server host | SCONSOLE_HOST | 0.0.0.0 | 服务监听地址 |
| Server port | SCONSOLE_PORT | 58091 | 服务监听端口 |
| Proxy | SCONSOLE_PROXY | http://192.168.34.4:7890 | 代理地址 |
| Agent image | SCONSOLE_AGENT_IMAGE | sconsole-agent:latest | Agent 容器镜像 |
| Shared dir | SCONSOLE_SHARED_DIR | ~/.sconsole/shared | 共享卷目录 |
| Upload dir | SCONSOLE_UPLOAD_DIR | ~/.sconsole/agent_upload | 上传目录 |

### 7.2 容器运行时

- 运行时: Podman 5.8.0
- Socket: `unix:///tmp/podman-user.sock`
- Volume 挂载: `~/.sconsole/shared/{instance_id}/:/agent/shared/:z`
- SELinux: 需要 `:z` 标签

### 7.3 Agent 容器内部结构

```
/agent/
├── shared/          ← 宿主机 ~/.sconsole/shared/{instance_id}/
│   ├── skills/      ← 技能文件
│   ├── volume/      ← 数据卷
│   └── ...
├── skills/          ← 内置技能
├── .hermes/
│   ├── soul.md      ← SOUL 提示词
│   └── memory.md    ← MEMORY 文件
└── entrypoint.sh    ← 启动脚本
```

---

## 8. 已知问题与限制

### 8.1 已修复 Bug

| Bug | 原因 | 修复 |
|-----|------|------|
| GET .../messages 返回 500 | pymysql `fetchall()` 返回 tuple，调用 `.reverse()` 报 AttributeError | `rows = list(cur.fetchall())` |
| 日志弹窗滚动到顶端 | innerHTML 替换后同步设置 scrollTop，DOM 重排未完成 | setTimeout 50ms 延迟恢复 scrollTop |

### 8.2 待修复设计问题

| 问题 | 影响 | 建议 |
|------|------|------|
| 不存在的 workspace ID 对 activity/files API 返回 200+空数据 | REST 语义不一致 | 统一返回 404 或加 exists 标记 |
| POST /api/workspaces/{id}/chat 请求格式无校验 | 传错格式直接透传 Hermes 报错 | 增加请求体校验 |
| pending/streaming 记录无超时清理 | Agent 崩溃后记录永远卡住 | 添加定时任务，超时标记为 error |

### 8.3 架构限制

| 限制 | 说明 |
|------|------|
| 单节点部署 | 当前所有工作空间部署在同一节点 |
| app.js 单文件 2100+ 行 | 随功能增长将变得难以维护，建议 3000 行前拆分模块 |
| pymysql 默认 cursor | fetchall() 返回 tuple 而非 list，所有 service 方法需注意 |
| 不支持 SSE 断线续传 | Recovery Poll 是从 DB 轮询而非 SSE Last-Event-ID 重连 |

---

## 9. 技术栈

| 层 | 技术 |
|----|------|
| 前端 | 原生 JavaScript + CSS (无框架，SPA 单页) |
| 后端 | Python 3.9 + FastAPI + uvicorn |
| 数据库 | OceanBase MySQL (兼容 MySQL 协议) |
| ORM | 无 (原生 pymysql + SQL) |
| HTTP 客户端 | httpx (支持 async + stream) |
| 容器运行时 | Podman 5.8.0 (user namespace) |
| AI Agent | Hermes Agent (OpenAI Responses API 兼容) |
| 实时通信 | SSE (Server-Sent Events) |
| 前后端架构 | BFF-Serve SPA (逻辑分离，单体部署) |
