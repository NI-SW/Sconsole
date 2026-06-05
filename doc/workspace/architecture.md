# Sconsole Workspace 架构

## 概述

Sconsole 采用 **Workspace → Agents** 两级架构。Workspace 是顶层工作空间，内部包含一个 Master Agent 和若干 Worker Agent。用户通过 Master Agent 与整个工作空间交互，Master Agent 负责协调各 Worker Agent 完成复杂任务。

## 架构图

```
Workspace "My Project"
├── Master Agent (master, running) :18002     ← 用户唯一聊天入口
├── Agent-A (worker, running) :18003          ← 被 Master 调度
├── Agent-B (worker, running) :18004
└── Agent-C (worker, pending)                 ← 待部署
```

## 数据模型

### SCL_workspaces（工作空间）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INT PK | 工作空间 ID |
| name | VARCHAR(255) | 工作空间名称 |
| description | TEXT | 描述 |
| node_id | VARCHAR(255) | 运行节点 |
| status | ENUM | pending / running / stopped / error |
| agent_count | 计算字段 | 内部 Agent 数量（子查询） |

### SCL_instance_agents（工作空间内的 Agent）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INT PK | Agent ID |
| instance_id | INT FK | 所属工作空间 |
| config_id | INT FK | 配置模板 |
| name | VARCHAR(255) | Agent 名称 |
| role | VARCHAR(20) | master / worker |
| container_id | VARCHAR(255) | 容器 ID |
| host_port | INT | 映射端口 |
| api_key | VARCHAR(128) | API 密钥 |
| status | ENUM | pending / deploying / running / stopped / error |

## API 端点

### 工作空间

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/instances` | 创建工作空间（自动创建 Master Agent） |
| GET | `/api/instances` | 列出所有工作空间 |
| GET | `/api/instances/{id}` | 获取工作空间详情 |
| PUT | `/api/instances/{id}` | 更新工作空间 |
| DELETE | `/api/instances/{id}` | 删除工作空间及所有 Agent |
| POST | `/api/instances/{id}/chat` | **向 Master Agent 发送聊天消息** |

### Agent（工作空间内）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/instances/{id}/agents` | 创建并部署新 Agent |
| GET | `/api/instances/{id}/agents` | 列出工作空间内所有 Agent |
| GET | `/api/instances/{id}/agents/{aid}` | 获取 Agent 详情 |
| POST | `/api/instances/{id}/agents/{aid}/stop` | 停止 Agent |
| DELETE | `/api/instances/{id}/agents/{aid}` | 删除 Agent |
| POST | `/api/instances/{id}/agents/{aid}/deploy` | **部署已存在的 Agent（如 Master）** |
| POST | `/api/instances/{id}/agents/{aid}/chat` | 直接与指定 Agent 聊天 |

## 工作流程

### 1. 创建工作空间

```
用户 → POST /api/instances {name: "My Project"}
     → 创建 SCL_workspaces 记录
     → 自动创建 Master Agent（role=master, status=pending）
     → 返回 {instance_id, master_agent_id}
```

### 2. 部署 Master Agent

```
用户 → 展开工作空间，点击 "Deploy Master"
     → 选择配置模板
     → POST /api/instances/{id}/agents/{mid}/deploy {config_id}
     → 服务器通过 WebSocket 向 Node 发送 deploy_agent 命令
     → Node 创建容器 agent-{instance_id}-{agent_id}
     → Node 回报状态 → Master Agent status → running
```

### 3. 添加 Worker Agent

```
用户 → 在工作空间内点击 "+ Agent"
     → 输入名称，选择配置模板
     → POST /api/instances/{id}/agents {name, config_id}
     → 容器创建并启动
```

### 4. 用户聊天

```
用户 → 点击工作空间的 "Chat" 按钮
     → 输入消息
     → POST /api/instances/{id}/chat {messages}
     → 服务端查找 Master Agent
     → 代理请求到 Master Agent 的 Hermes API (http://127.0.0.1:{port}/v1/chat/completions)
     → 返回 Master Agent 回复
```

### 5. Master Agent 协调工作

Master Agent 运行在独立容器中，通过以下方式协调 Worker Agent：

- **共享目录**：`~/.sconsole/shared/{instance_id}/{agent_id}/` 下的文件交换
- **容器网络**：同一 Workspace 的 Agent 部署在同一 Podman 网络中，可通过容器名互相访问
- **API 调用**：Master Agent 可调用 Worker Agent 的 Hermes API（`http://agent-{instance_id}-{agent_id}:8642/v1/chat/completions`）

## 容器命名规则

```
agent-{instance_id}-{agent_id}

示例：
  agent-48-11    ← 工作空间 #48 的 Agent #11 (Master)
  agent-48-12    ← 工作空间 #48 的 Agent #12 (Worker)
```

旧版兼容格式：`agent-{instance_id}`（agent_id=0，视为孤儿容器）

## 前端 UI 层级

```
#agents 页面
├── 批量操作栏（勾选后显示）
├── Workspace "My Project"  [Chat] [+ Agent] [Delete]
│   ├── ▸ Master  [Master] running  [Deploy Master] / [Stop]
│   ├──   Agent-A  running  [Stop] [Delete]
│   └──   Agent-B  pending  [Stop] [Delete]
└── Workspace "Another"     [Chat] [+ Agent] [Delete]
```

- **Workspace 卡片**：左边框主题色，Chat 按钮发送消息给 Master Agent
- **Master Agent**：金色左边框 + "Master" 徽章，不可删除
- **Worker Agent**：标准样式，可 Stop / Delete

## 关键设计决策

1. **创建 Workspace 不强制要求在线节点**：Workspace 是纯逻辑实体，只在部署 Agent 时才需要节点
2. **Master Agent 不可删除**：每个 Workspace 必须有且仅有一个 Master
3. **聊天统一入口**：用户始终通过 Workspace 的 Chat 与 Master 交互，不直接与 Worker 对话
4. **Agent 间通信**：通过共享文件系统和容器网络实现，Master 负责编排
