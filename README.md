# Sconsole

# 目标
```
让用户可以快速启动agent，用于各种不同任务

支持：
1、自定义人格（SOUL）文件、记忆（MEMORY）文件，技术文档、模型url、模型APIKEY、模型名称等
2、自定义技能，支持从url安装、压缩包安装等
3、预设agent模板，如stream-agent，参考/home/stream-agent/
4、支持控制台连接agent，发送消息，查看agent回复
5、支持在控制台上配置agent相关参数
6、agent监控，agent日志，agent执行进展等
7、支持使用自然语言让agent构建任务流，用户执行最终确认
```

# 控制台
```
提供一个控制台界面，用户可以在控制台上配置agent相关参数，如人格文件、记忆文件、技能、模型等，并通过控制台快速启动agent
```

# 服务端
```
接收任意节点的连接，节点连接后控制台可以在该节点上部署agent，部署时将配置的人格文件、记忆文件、技能、模型等参数传入docker容器内，agent在启动时使用配置好的参数进行启动
```

# 节点
```
需安装docker，主动连接至服务端，受服务端控制，接收服务端的部署指令，在本地启动docker容器，部署agent，并协调agent的运行（如多agent共享文件夹、传递消息等）
```

# 要点
```
agent使用docker部署，目前仅支持hermes-agent，后续可能会支持更多agent框架
将docker的部署封装为启动脚本，控制台可以通过脚本传入参数快速启动容器
启动agent时，将配置的人格文件、记忆文件、技能等参数传入docker容器内，agent在启动时使用配置好的参数进行启动

在多agent协作场景，agent之间可以通过共享文件夹、消息传递等方式进行协作，控制台可以监控agent的运行状态，查看agent的日志和执行进展等
```

# 代理
```
如连接外部网络失败，可尝试使用代理进行连接。
http://192.168.34.4:7890
```

# 数据库
```
如果需要使用数据库进行数据持久化存储，可以使用现有ob-mysql数据库，但要保留所有表结构的SQL文件，放置于sql_files/目录下，以便在需要时重新创建数据库。
需要创建数据库时，使用SCL_作为前缀，确保数据库名称的唯一性和识别性。
oceanbase-mysql数据库：[ ip/port=192.168.34.65/2881 database=mysql Tenant=sys user=root passwd=Info@1234 ]
可以使用mysql命令连接，如：mysql -h192.168.34.65 -P2881 -uroot -pInfo@1234
```

# 启动说明
```
Sconsole 手动启动步骤
0. 前提：启动 Podman Socket

bash
如果 podman socket 未运行（先检查）
ls /tmp/podman-user.sock
不存在则启动
podman system service --time=0 unix:///tmp/podman-user.sock &

1. 启动 Sconsole 服务端

bash
cd /home/dpfs/github/Sconsole
前台运行（终端会占用，方便观察日志）
.venv/bin/python3 -m uvicorn server.main:app --host 0.0.0.0 --port 58091 --log-level info
或后台运行
nohup .venv/bin/python3 -m uvicorn server.main:app --host 0.0.0.0 --port 58091 --log-level info > /tmp/sconsole_server.log 2>&1 &

验证：curl -s http://localhost:58091/ 返回 200。
2. 启动 Node Agent

bash
cd /home/dpfs/github/Sconsole

.venv/bin/python3 node/agent.py --server ws://localhost:58091 --node-id node-1

验证：curl -s http://localhost:58091/api/nodes 返回 node-1 online。
端口说明

| 组件            | 端口   | 说明                                        |
|-----------------|--------|---------------------------------------------|
| Sconsole Server | 58091  | FastAPI + WebSocket                         |
| Agent 容器      | 18001+ | 每个 Agent 动态分配 host_port → 容器内 8642 |
数据库

MySQL：xxx.xxx.xxx.xxx:3306 / 库 SCL_sconsole

```