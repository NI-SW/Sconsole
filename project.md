     Sconsole 项目初步构建完成。以下是完整的项目结构和说明：
     项目结构

     Sconsole/
     ├── start.sh                     # 主启动脚本
     ├── requirements.txt             # Python 依赖
     ├── config/default.yaml          # 默认配置文件
     ├── sql_files/001_schema.sql     # OceanBase MySQL 数据库建表脚本
     │
     ├── server/                      # 服务端 (FastAPI)
     │   ├── main.py                  # 入口，启动 FastAPI + 静态文件
     │   ├── config.py                # 配置（数据库、代理、镜像等）
     │   ├── ws_manager.py            # WebSocket 连接管理（控制台/节点）
     │   ├── api/
     │   │   ├── routes.py            # REST API（配置CRUD、实例管理、节点）
     │   │   └── ws_routes.py         # WebSocket 路由（控制台/节点实时通信）
     │   ├── models/init.py       # 数据模型（AgentConfig、AgentInstance等）
     │   ├── services/
     │   │   ├── agent_service.py     # Agent 配置与实例管理
     │   │   └── node_service.py      # 节点注册与管理
     │   └── db/database.py           # OceanBase MySQL 连接层
     │
     ├── console/                     # 控制台前端
     │   ├── templates/index.html     # Web 控制台页面
     │   └── static/
     │       ├── css/style.css        # 样式（暗色主题）
     │       └── js/app.js            # 前端逻辑（WebSocket通信、多视图）
     │
     ├── node/                        # 节点 Agent
     │   ├── agent.py                 # 节点核心（连接服务端、管理Docker容器）
     │   └── start.sh                 # 节点启动脚本
     │
     ├── docker/                      # Docker 资源
     │   ├── Dockerfile               # Agent 镜像定义
     │   ├── build.sh                 # 镜像构建脚本
     │   └── scripts/entrypoint.sh    # 容器入口点（加载配置、轮询输入）
     │
     └── examples/stream-agent/       # 预设模板
         └── preset.yaml              # Stream Agent 模板（参考 /home/stream-agent）

     组件说明

     | 组件    | 说明                                     | 启动方式                                  |
     |---------|------------------------------------------|-------------------------------------------|
     | Server  | FastAPI + WebSocket 服务端，端口 8080    | ./start.sh 或 python3 -m server.main      |
     | Console | Web 控制台，访问 http://host:8080/       | 随 Server 启动，无需单独启动              |
     | Node    | 节点 Agent，连接服务端，管理 Docker 容器 | ./node/start.sh --server ws://server:8080 |
     | DB      | OceanBase MySQL 持久化 (5张表，SCL_前缀) | 通过 sql_files/001_schema.sql 初始化      |
     数据库表 (OceanBase MySQL)

     - SCL_agent_configs - Agent 配置模板（人格文件、记忆、模型参数、技能等）
     - SCL_workspaces - 工作空间（名称、节点、状态）
     - SCL_instance_agents - 工作空间内的 Agent（容器ID、端口、角色）
     - SCL_agent_messages_v3 - Agent 对话历史记录
     - SCL_nodes - 计算节点信息（心跳、资源状态）
     - SCL_skills - 已安装的技能列表
     关键特性

     1. 自定义 Agent 配置 - SOUL 文件、MEMORY 文件、模型、API Key 均可通过控制台配置
     2. WebSocket 实时通信 - 控制台与 Agent 之间的消息实时传递
     3. Docker/Podman 部署 - 节点通过容器运行时部署 Agent，共享文件夹传递配置
     4. 多节点支持 - 服务端可管理多个计算节点，自动选择可用节点
     5. Stream Agent 预设模板 - 预配置了流式数据处理 Agent
     6. 代理支持 - 通过配置代理访问外部网络 (http://192.168.34.4:7890)
     下一步

     1. 创建数据库: 在 OceanBase 中执行 sql_files/001_schema.sql
     2. 构建镜像: ./docker/build.sh
     3. 启动服务端: ./start.sh
     4. 启动节点: 另开终端 ./node/start.sh --server ws://localhost:8080
     5. 打开浏览器访问 http://localhost:8080 进行配置和部署
