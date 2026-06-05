# Sconsole 数据库表结构参考

## 工作空间相关

### instances (工作空间)
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INT | 工作空间ID |
| name | VARCHAR(100) | 名称 |
| description | TEXT | 描述 |
| node_id | VARCHAR(50) | 所属节点 |
| status | ENUM(pending,running,stopped,error) | 状态 |

### agents (Agent)
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INT | Agent ID |
| instance_id | INT | 所属工作空间 |
| config_id | INT | 配置ID |
| name | VARCHAR(100) | 名称 |
| role | ENUM(master,worker) | 角色 |
| description | TEXT | 描述 |
| host_port | INT | 主机端口 |
| api_key | VARCHAR(200) | API密钥 |
| container_id | VARCHAR(200) | 容器ID |
| status | ENUM(pending,deploying,running,stopped,error) | 状态 |

### agent_configs (Agent配置)
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INT | 配置ID |
| name | VARCHAR(100) | 名称 |
| soul_file | TEXT | 灵魂文件(SOUL.md)内容 |
| memory_file | TEXT | 记忆文件(MEMORY.md)内容 |
| tech_docs | TEXT | 技术文档 |
| model_url | VARCHAR(500) | 模型API地址 |
| model_api_key | VARCHAR(500) | 模型API密钥 |
| model_name | VARCHAR(100) | 模型名称 |
| model_provider | VARCHAR(50) | 模型供应商 |
| proxy | VARCHAR(500) | 代理地址 |
| skills | JSON | 技能列表 |

### conversations (对话记录)
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INT | 对话ID |
| instance_id | INT | 工作空间ID |
| agent_id | INT | Agent ID |
| conversation_id | VARCHAR(100) | 对话唯一ID |
| user_input | TEXT | 用户输入 |
| output | JSON | 输出内容 |
| usage_info | JSON | Token使用信息 |
| status | VARCHAR(20) | 状态 |

## 食品溯源相关

### food_trace (食品溯源记录)
用于食品溯源场景的核心数据表，存储食品从生产到消费的全链路信息。
