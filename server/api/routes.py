"""
Sconsole Server - REST API Routes
"""
import json
import uuid
import os
import shutil
import asyncio
import httpx
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from typing import Optional, List

from server.models import AgentConfig, AgentInstance, Workspace, InstanceAgent
from server.services.agent_service import AgentService
from server.services.node_service import NodeService
from server.ws_manager import manager
from server.config import AGENT_UPLOAD_DIR

router = APIRouter()


# ─── Agent Config CRUD ───────────────────────────────────────────────

@router.get("/api/configs")
def list_configs():
    return {"configs": AgentService.list_configs()}


@router.post("/api/configs")
def create_config(data: dict):
    config = AgentConfig(
        name=data.get("name", ""),
        soul_file=data.get("soul_file", ""),
        memory_file=data.get("memory_file", ""),
        tech_docs=data.get("tech_docs", ""),
        model_url=data.get("model_url", ""),
        model_api_key=data.get("model_api_key", ""),
        model_name=data.get("model_name", ""),
        model_provider=data.get("model_provider", ""),
        proxy=data.get("proxy", ""),
        skills=data.get("skills", []),
        
        extra_env=data.get("extra_env", {}),
    )
    config_id = AgentService.create_config(config)
    return {"id": config_id, "message": "Config created"}


@router.get("/api/configs/{config_id}")
def get_config(config_id: int):
    cfg = AgentService.get_config(config_id)
    if not cfg:
        raise HTTPException(status_code=404, detail="Config not found")
    return cfg


@router.put("/api/configs/{config_id}")
def update_config(config_id: int, data: dict):
    ok = AgentService.update_config(config_id, data)
    if not ok:
        raise HTTPException(status_code=404, detail="Config not found")
    return {"message": "Config updated"}


@router.delete("/api/configs/{config_id}")
def delete_config(config_id: int):
    ok = AgentService.delete_config(config_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Config not found")
    return {"message": "Config deleted"}


# ─── Config File Upload ──────────────────────────────────────────────

ACONFIG_BASE = os.path.join(os.path.expanduser("~"), ".sconsole", "aconfig")


@router.post("/api/configs/{config_id}/files")
async def upload_config_files(config_id: int, files: List[UploadFile] = File(...)):
    """Upload files for an agent configuration."""
    cfg = AgentService.get_config(config_id)
    if not cfg:
        raise HTTPException(status_code=404, detail="Config not found")

    cfg_name = cfg["name"] or f"config-{config_id}"
    cfg_dir = os.path.join(ACONFIG_BASE, cfg_name)
    os.makedirs(cfg_dir, exist_ok=True)

    saved = []
    existing = AgentService.get_attached_files(config_id)

    for f in files:
        if not f.filename:
            continue
        safe_name = os.path.basename(f.filename)
        dest = os.path.join(cfg_dir, safe_name)
        with open(dest, "wb") as dst:
            shutil.copyfileobj(f.file, dst)
        if safe_name not in existing:
            existing.append(safe_name)
        saved.append(safe_name)

    AgentService.update_attached_files(config_id, existing)
    return {"files": existing, "message": f"{len(saved)} file(s) uploaded"}


@router.get("/api/configs/{config_id}/files")
def list_config_files(config_id: int):
    """List uploaded files for a config."""
    files = AgentService.get_attached_files(config_id)
    return {"files": files}


@router.delete("/api/configs/{config_id}/files/{filename}")
def delete_config_file(config_id: int, filename: str):
    """Delete an uploaded file from a config."""
    cfg = AgentService.get_config(config_id)
    if not cfg:
        raise HTTPException(status_code=404, detail="Config not found")

    cfg_name = cfg["name"] or f"config-{config_id}"
    cfg_dir = os.path.join(ACONFIG_BASE, cfg_name)
    file_path = os.path.join(cfg_dir, os.path.basename(filename))

    if os.path.exists(file_path):
        os.remove(file_path)

    existing = AgentService.get_attached_files(config_id)
    if filename in existing:
        existing.remove(filename)
        AgentService.update_attached_files(config_id, existing)

    return {"files": existing, "message": f"File '{filename}' deleted"}


# ─── 工作空间 CRUD ─────────────────────────────────────────────────────

@router.get("/api/workspaces")
def list_workspaces(status: Optional[str] = None):
    return {"workspaces": AgentService.list_instances(status)}


@router.post("/api/workspaces")
def create_workspace(data: dict):
    """创建新的工作空间（无需容器、无需节点即可创建）。"""
    name = data.get("name", "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="请输入工作空间名称")
    node_id = data.get("node_id", "")
    description = data.get("description", "")

    if not node_id:
        nodes = NodeService.list_nodes()
        online = [n for n in nodes if n["status"] == "online"]
        node_id = online[0]["node_id"] if online else ""

    result = AgentService.create_instance(name, node_id, description)
    return {
        "workspace_id": result["instance_id"],
        "master_agent_id": result["master_agent_id"],
        "node_id": node_id,
        "message": "工作空间创建成功",
    }


@router.get("/api/workspaces/{workspace_id}")
def get_workspace(workspace_id: int):
    inst = AgentService.get_instance(workspace_id)
    if not inst:
        raise HTTPException(status_code=404, detail="工作空间未找到")
    return inst


@router.put("/api/workspaces/{workspace_id}")
def update_workspace(workspace_id: int, data: dict):
    try:
        ok = AgentService.update_instance(workspace_id, data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not ok:
        raise HTTPException(status_code=404, detail="工作空间未找到")
    return {"message": "更新成功"}


@router.delete("/api/workspaces/{workspace_id}")
async def delete_workspace(workspace_id: int):
    agents = AgentService.list_instance_agents(workspace_id)
    inst = AgentService.get_instance(workspace_id)  # fetch BEFORE deleting
    node_id = inst["node_id"] if inst else ""

    for agent in agents:
        if agent["status"] in ("running", "pending"):
            if node_id:
                await manager.send_to_node(node_id, {
                    "type": "stop_agent",
                    "workspace_id": workspace_id,
                    "agent_id": agent["id"],
                })
    AgentService.delete_instance(workspace_id)

    # Clean up uploaded files
    import shutil
    upload_dir = _get_upload_dir(workspace_id)
    if os.path.isdir(upload_dir):
        shutil.rmtree(upload_dir, ignore_errors=True)

    # Clean up intercom artifacts via node agent
    agent_ids = [a["id"] for a in agents]
    if node_id:
        await manager.send_to_node(node_id, {
            "type": "clean_intercom",
            "workspace_id": workspace_id,
            "agent_ids": agent_ids,
        })

    return {"message": "工作空间已删除"}


# ═══ Backward-compatible /api/instances routes (redirect to workspaces) ═══

@router.get("/api/instances")
def list_instances_legacy(status: Optional[str] = None):
    """兼容旧 API：列出所有工作空间"""
    return {"instances": AgentService.list_instances(status)}


@router.get("/api/instances/{instance_id}")
def get_instance_legacy(instance_id: int):
    """兼容旧 API：获取工作空间"""
    return get_workspace(instance_id)


@router.post("/api/instances")
def create_instance_legacy(data: dict):
    """兼容旧 API：创建工作空间"""
    return create_workspace(data)


@router.put("/api/instances/{instance_id}")
def update_instance_legacy(instance_id: int, data: dict):
    """兼容旧 API：更新工作空间"""
    return update_workspace(instance_id, data)


@router.delete("/api/instances/{instance_id}")
async def delete_instance_legacy(instance_id: int):
    """兼容旧 API：删除工作空间"""
    return await delete_workspace(instance_id)


# ─── 工作空间内 Agent CRUD ─────────────────────────────────────────────

@router.get("/api/workspaces/{workspace_id}/agents")
def list_workspace_agents(workspace_id: int, status: Optional[str] = None):
    return {"agents": AgentService.list_instance_agents(workspace_id, status)}


@router.post("/api/workspaces/{workspace_id}/agents")
async def create_workspace_agent(workspace_id: int, data: dict):
    """在工作空间内创建并部署 Agent"""
    config_id = data.get("config_id")
    agent_name = data.get("name", "").strip()
    if not config_id:
        raise HTTPException(status_code=400, detail="请选择 Agent 配置")
    if not agent_name:
        raise HTTPException(status_code=400, detail="请输入 Agent 名称")

    config = AgentService.get_config(config_id)
    if not config:
        raise HTTPException(status_code=404, detail="配置未找到")

    inst = AgentService.get_instance(workspace_id)
    if not inst:
        raise HTTPException(status_code=404, detail="工作空间未找到")

    agent_id = AgentService.create_instance_agent(workspace_id, config_id, agent_name)

    node_id = inst.get("node_id", "")
    if not node_id:
        nodes = NodeService.list_nodes()
        online = [n for n in nodes if n["status"] == "online"]
        if not online:
            AgentService.update_agent_status(agent_id, "error")
            raise HTTPException(status_code=400, detail="没有可用的在线节点")
        node_id = online[0]["node_id"]

    cmd = {
        "type": "deploy_agent",
        "workspace_id": workspace_id,
        "agent_id": agent_id,
        "config": config,
        "aconfig_path": _get_aconfig_path(config),
    }
    success = await manager.send_to_node(node_id, cmd)
    if not success:
        AgentService.update_agent_status(agent_id, "error")
        raise HTTPException(status_code=500, detail="无法发送部署命令到节点")

    return {"agent_id": agent_id, "workspace_id": workspace_id, "message": "Agent 部署已开始"}


@router.get("/api/workspaces/{workspace_id}/agents/{agent_id}")
def get_workspace_agent(workspace_id: int, agent_id: int):
    agent = AgentService.get_instance_agent(agent_id)
    if not agent or agent["instance_id"] != workspace_id:
        raise HTTPException(status_code=404, detail="Agent 未找到")
    return agent


@router.post("/api/workspaces/{workspace_id}/agents/{agent_id}/stop")
async def stop_workspace_agent(workspace_id: int, agent_id: int):
    agent = AgentService.get_instance_agent(agent_id)
    if not agent or agent["instance_id"] != workspace_id:
        raise HTTPException(status_code=404, detail="Agent 未找到")

    inst = AgentService.get_instance(workspace_id)
    if inst:
        await manager.send_to_node(inst["node_id"], {
            "type": "stop_agent",
            "workspace_id": workspace_id,
            "agent_id": agent_id,
        })
    return {"message": "停止命令已发送"}


@router.delete("/api/workspaces/{workspace_id}/agents/{agent_id}")
async def delete_workspace_agent(workspace_id: int, agent_id: int):
    agent = AgentService.get_instance_agent(agent_id)
    if not agent or agent["instance_id"] != workspace_id:
        raise HTTPException(status_code=404, detail="Agent 未找到")

    inst = AgentService.get_instance(workspace_id)
    if inst and agent["status"] in ("running", "pending"):
        await manager.send_to_node(inst["node_id"], {
            "type": "stop_agent",
            "workspace_id": workspace_id,
            "agent_id": agent_id,
        })
    AgentService.delete_instance_agent(agent_id)
    return {"message": "Agent 已删除"}


@router.post("/api/workspaces/{workspace_id}/agents/{agent_id}/deploy")
async def deploy_workspace_agent(workspace_id: int, agent_id: int, data: dict):
    """部署已有的 Agent 记录"""
    return await deploy_existing_agent(workspace_id, agent_id, data)


@router.post("/api/workspaces/{workspace_id}/agents/{agent_id}/chat")
async def workspace_agent_chat(workspace_id: int, agent_id: int, data: dict):
    """与工作空间内的 Agent 对话"""
    return await agent_chat(workspace_id, agent_id, data)


@router.get("/api/workspaces/{workspace_id}/agents/{agent_id}/messages")
def get_workspace_agent_messages(workspace_id: int, agent_id: int, limit: int = 100):
    return {"messages": AgentService.get_messages(agent_id, limit)}


@router.get("/api/workspaces/{workspace_id}/agents/{agent_id}/logs")
def get_workspace_agent_logs(workspace_id: int, agent_id: int, tail: int = 200):
    return get_agent_logs(workspace_id, agent_id, tail)


@router.get("/api/workspaces/{workspace_id}/agents/{agent_id}/conversations")
def get_workspace_agent_conversations(workspace_id: int, agent_id: int, limit: int = 50):
    """获取 Agent 的历史对话"""
    agent = AgentService.get_instance_agent(agent_id)
    if not agent or agent["instance_id"] != workspace_id:
        raise HTTPException(status_code=404, detail="Agent 未找到")
    return {"conversations": AgentService.get_agent_conversations(workspace_id, agent_id, limit)}


@router.post("/api/workspaces/{workspace_id}/chat")
async def workspace_chat(workspace_id: int, data: dict):
    """与工作空间主控 Agent 对话"""
    return await instance_chat(workspace_id, data)


@router.get("/api/workspaces/{workspace_id}/activity")
def get_workspace_activity_new(workspace_id: int, tail: int = 80):
    """获取工作空间活动日志"""
    return get_workspace_activity(workspace_id, tail)


@router.get("/api/workspaces/{workspace_id}/conversations")
def get_workspace_conversations(workspace_id: int, limit: int = 100):
    """获取工作空间所有对话记录"""
    return {"conversations": AgentService.get_agent_conversations(workspace_id, 0, limit)}


# ─── Instance Agents (containers within a workspace) ──────────────────

@router.get("/api/instances/{instance_id}/agents")
def list_instance_agents(instance_id: int, status: Optional[str] = None):
    return {"agents": AgentService.list_instance_agents(instance_id, status)}


@router.post("/api/instances/{instance_id}/agents")
async def create_agent(instance_id: int, data: dict):
    """Create and deploy a new agent within an instance."""
    config_id = data.get("config_id")
    agent_name = data.get("name", "").strip()
    if not config_id:
        raise HTTPException(status_code=400, detail="config_id required")
    if not agent_name:
        raise HTTPException(status_code=400, detail="name required")

    config = AgentService.get_config(config_id)
    if not config:
        raise HTTPException(status_code=404, detail="Config not found")

    inst = AgentService.get_instance(instance_id)
    if not inst:
        raise HTTPException(status_code=404, detail="Instance not found")

    # Create agent record first
    agent_id = AgentService.create_instance_agent(instance_id, config_id, agent_name)

    # Get node: use instance's node or pick first online
    node_id = inst.get("node_id", "")
    if not node_id:
        nodes = NodeService.list_nodes()
        online = [n for n in nodes if n["status"] == "online"]
        if not online:
            AgentService.update_agent_status(agent_id, "error")
            raise HTTPException(status_code=400, detail="No online nodes available for deployment")
        node_id = online[0]["node_id"]

    # Send deploy command to node
    cmd = {
        "type": "deploy_agent",
        "instance_id": instance_id,
        "agent_id": agent_id,
        "config": config,
        "aconfig_path": _get_aconfig_path(config),
    }
    success = await manager.send_to_node(node_id, cmd)
    if not success:
        AgentService.update_agent_status(agent_id, "error")
        raise HTTPException(status_code=500, detail="Failed to send deploy command to node")

    return {"agent_id": agent_id, "instance_id": instance_id, "message": "Agent deployment started"}


@router.get("/api/instances/{instance_id}/agents/{agent_id}")
def get_instance_agent(instance_id: int, agent_id: int):
    agent = AgentService.get_instance_agent(agent_id)
    if not agent or agent["instance_id"] != instance_id:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@router.post("/api/instances/{instance_id}/agents/{agent_id}/stop")
async def stop_instance_agent(instance_id: int, agent_id: int):
    agent = AgentService.get_instance_agent(agent_id)
    if not agent or agent["instance_id"] != instance_id:
        raise HTTPException(status_code=404, detail="Agent not found")

    inst = AgentService.get_instance(instance_id)
    if inst:
        await manager.send_to_node(inst["node_id"], {
            "type": "stop_agent",
            "instance_id": instance_id,
            "agent_id": agent_id,
        })
    return {"message": "Stop command sent"}


@router.delete("/api/instances/{instance_id}/agents/{agent_id}")
async def delete_instance_agent(instance_id: int, agent_id: int):
    agent = AgentService.get_instance_agent(agent_id)
    if not agent or agent["instance_id"] != instance_id:
        raise HTTPException(status_code=404, detail="Agent not found")

    inst = AgentService.get_instance(instance_id)
    if inst and agent["status"] in ("running", "pending"):
        await manager.send_to_node(inst["node_id"], {
            "type": "stop_agent",
            "instance_id": instance_id,
            "agent_id": agent_id,
        })
    AgentService.delete_instance_agent(agent_id)
    return {"message": "Agent deleted"}


@router.post("/api/instances/{instance_id}/agents/{agent_id}/deploy")
async def deploy_existing_agent(instance_id: int, agent_id: int, data: dict):
    """Deploy an existing agent record (e.g. master agent) by assigning config and launching."""
    config_id = data.get("config_id")
    if not config_id:
        raise HTTPException(status_code=400, detail="config_id required")

    config = AgentService.get_config(config_id)
    if not config:
        raise HTTPException(status_code=404, detail="Config not found")

    agent = AgentService.get_instance_agent(agent_id)
    if not agent or agent["instance_id"] != instance_id:
        raise HTTPException(status_code=404, detail="Agent not found")

    # If deploying master agent, inject master SOUL and clear non-essential fields
    if agent.get("role") == "master":
        worker_descriptions = data.get("worker_descriptions", {})
        master_soul = AgentService.build_master_soul(instance_id, agent_id, worker_descriptions)
        config["soul_file"] = master_soul
        config["memory_file"] = ""      # master doesn't use user MEMORY
        config["tech_docs"] = ""        # master doesn't use user tech docs
        config["skills"] = []           # master uses built-in skills only
        config["_agents_json"] = json.dumps(AgentService.build_agents_json(instance_id, agent_id))
        # Save custom descriptions for future dynamic updates
        if worker_descriptions:
            shared_dir = os.path.join(
                os.path.expanduser("~"), ".sconsole", "shared",
                str(instance_id), str(agent_id),
            )
            os.makedirs(shared_dir, exist_ok=True)
            with open(os.path.join(shared_dir, "agent_descriptions.json"), "w", encoding="utf-8") as f:
                json.dump(worker_descriptions, f, ensure_ascii=False)

    inst = AgentService.get_instance(instance_id)
    if not inst:
        raise HTTPException(status_code=404, detail="Instance not found")

    # Get node
    node_id = inst.get("node_id", "")
    if not node_id:
        nodes = NodeService.list_nodes()
        online = [n for n in nodes if n["status"] == "online"]
        if not online:
            raise HTTPException(status_code=400, detail="No online nodes available")
        node_id = online[0]["node_id"]

    # Send deploy command
    cmd = {
        "type": "deploy_agent",
        "instance_id": instance_id,
        "agent_id": agent_id,
        "config": config,
        "aconfig_path": _get_aconfig_path(config),
    }
    success = await manager.send_to_node(node_id, cmd)
    if not success:
        AgentService.update_agent_status(agent_id, "error")
        raise HTTPException(status_code=500, detail="Failed to send deploy command to node")

    return {"agent_id": agent_id, "message": "Deploy command sent"}


def _get_aconfig_path(config: dict) -> str:
    """Get the aconfig directory path for a config, if files exist."""
    cfg_name = config.get("name", "")
    if not cfg_name:
        return ""
    cfg_dir = os.path.join(ACONFIG_BASE, cfg_name)
    if os.path.isdir(cfg_dir) and os.listdir(cfg_dir):
        return cfg_dir
    return ""


# ─── Agent Chat (proxy to container hermes gateway) ──────────────────

@router.post("/api/instances/{instance_id}/agents/{agent_id}/chat")
async def agent_chat(instance_id: int, agent_id: int, data: dict):
    """Proxy chat request to the agent's hermes gateway API."""
    agent = AgentService.get_instance_agent(agent_id)
    if not agent or agent["instance_id"] != instance_id:
        raise HTTPException(status_code=404, detail="Agent not found")
    if agent["status"] != "running":
        raise HTTPException(status_code=400, detail="Agent is not running")

    host_port = agent.get("host_port", 0)
    api_key = agent.get("api_key", "")
    if not host_port:
        raise HTTPException(status_code=400, detail="No port mapping found")

    agent_url = f"http://127.0.0.1:{host_port}/v1/chat/completions"
    messages = data.get("messages", [])
    stream = data.get("stream", False)

    payload = {
        "model": "hermes-agent",
        "messages": messages,
        "stream": stream,
    }

    # Extract user input from last user message
    user_input = ""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            user_input = msg.get("content", "")[:2000]
            break

    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            if stream:
                req = client.build_request(
                    "POST", agent_url,
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                )
                resp = await client.send(req, stream=True)
                # Record user input for stream (response text unknown)
                if user_input:
                    record_conversation(
                        instance_id=instance_id, agent_id=agent_id,
                        conversation_id="", user_input=user_input,
                        result=None,
                    )
                return StreamingResponse(
                    resp.aiter_bytes(),
                    media_type="text/event-stream",
                    status_code=resp.status_code,
                )
            else:
                resp = await client.post(
                    agent_url,
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                )
                result = resp.json()
                if user_input:
                    record_conversation(
                        instance_id=instance_id, agent_id=agent_id,
                        conversation_id="",
                        user_input=user_input,
                        result=result,
                    )
                return result
    except httpx.ConnectError:
        if user_input:
            record_conversation(
                instance_id=instance_id, agent_id=agent_id,
                conversation_id="", user_input=user_input,
                result=None, error_msg="Cannot connect to agent gateway",
            )
        raise HTTPException(status_code=502, detail="Cannot connect to agent gateway")
    except Exception as e:
        if user_input:
            record_conversation(
                instance_id=instance_id, agent_id=agent_id,
                conversation_id="", user_input=user_input,
                result=None, error_msg=str(e),
            )
        raise HTTPException(status_code=500, detail=str(e))


# ─── Agent Messages ──────────────────────────────────────────────────

@router.get("/api/instances/{instance_id}/agents/{agent_id}/messages")
def get_messages(instance_id: int, agent_id: int, limit: int = 100):
    return {"messages": AgentService.get_messages(agent_id, limit)}


# ─── Instance-level Chat (routes to master agent) ──────────────────

@router.post("/api/instances/{instance_id}/chat")
async def instance_chat(instance_id: int, data: dict):
    """Chat with the workspace master agent. Routes to master agent's API."""
    master = AgentService.get_master_agent(instance_id)
    if not master:
        raise HTTPException(status_code=404, detail="No master agent found for this workspace")

    if master["status"] != "running":
        raise HTTPException(status_code=400, detail=f"Master agent is {master['status']}. Deploy it first.")

    host_port = master.get("host_port", 0)
    api_key = master.get("api_key", "")
    if not host_port:
        raise HTTPException(status_code=400, detail="Master agent has no port mapping")

    agent_url = f"http://127.0.0.1:{host_port}/v1/chat/completions"
    messages = data.get("messages", [])
    stream = data.get("stream", False)

    payload = {"model": "hermes-agent", "messages": messages, "stream": stream}

    # Extract user input from last user message
    user_input = ""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            user_input = msg.get("content", "")[:2000]
            break

    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            if stream:
                req = client.build_request("POST", agent_url, json=payload,
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"})
                resp = await client.send(req, stream=True)
                # Record user input for stream
                if user_input:
                    record_conversation(
                        instance_id=instance_id, agent_id=master["id"],
                        conversation_id="", user_input=user_input,
                        result=None,
                    )
                return StreamingResponse(resp.aiter_bytes(), media_type="text/event-stream", status_code=resp.status_code)
            else:
                resp = await client.post(agent_url, json=payload,
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"})
                result = resp.json()
                if user_input:
                    record_conversation(
                        instance_id=instance_id, agent_id=master["id"],
                        conversation_id="",
                        user_input=user_input,
                        result=result,
                    )
                return result
    except httpx.ConnectError:
        if user_input:
            record_conversation(
                instance_id=instance_id, agent_id=master["id"],
                conversation_id="", user_input=user_input,
                result=None, error_msg="Cannot connect to master agent",
            )
        raise HTTPException(status_code=502, detail="Cannot connect to master agent")
    except Exception as e:
        if user_input:
            record_conversation(
                instance_id=instance_id, agent_id=master["id"],
                conversation_id="", user_input=user_input,
                result=None, error_msg=str(e),
            )
        raise HTTPException(status_code=500, detail=str(e))


# ─── Nodes ───────────────────────────────────────────────────────────

@router.get("/api/nodes")
def list_nodes():
    return {"nodes": NodeService.list_nodes()}


@router.get("/api/nodes/{node_id}")
def get_node(node_id: str):
    node = NodeService.get_node(node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    return node


@router.delete("/api/nodes/{node_id}")
def delete_node(node_id: str):
    ok = NodeService.delete_node(node_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Node not found")
    return {"message": "Node deleted"}


# ─── Skill Management ────────────────────────────────────────────────

@router.post("/api/skills/install")
def install_skill(data: dict):
    """Install a skill from URL or local path."""
    source = data.get("source", "")
    skill_name = data.get("name", "")
    if not source or not skill_name:
        raise HTTPException(status_code=400, detail="name and source required")
    # TODO: Implement skill installation pipeline
    return {"message": f"Skill '{skill_name}' installation requested from {source}"}


@router.get("/api/skills")
def list_skills():
    # TODO: Implement skill listing
    return {"skills": []}


# ─── Container Management (direct, bypasses node WS) ──────────────────

@router.get("/api/containers")
def list_containers():
    """List running agent containers directly via podman."""
    import subprocess
    import re
    try:
        result = subprocess.run(
            ["podman", "ps", "--filter", "name=agent-",
             "--format", '{{.ID}}\t{{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}'],
            capture_output=True, text=True, timeout=10,
        )
        containers = []
        for line in result.stdout.strip().split('\n'):
            if not line:
                continue
            parts = line.split('\t')
            if len(parts) >= 2:
                name = parts[1]
                # Extract instance_id and agent_id from names like:
                #   agent-44-1  → instance=44, agent=1
                #   agent-44    → instance=44, agent=0 (legacy)
                m = re.search(r'agent-(\d+)(?:-(\d+))?', name)
                instance_id = m.group(1) if m else '0'
                agent_id = m.group(2) if m and m.group(2) else '0'
                # Also extract host port
                host_port = 0
                ports_str = parts[4] if len(parts) > 4 else ''
                pm = re.search(r'0\.0\.0\.0:(\d+)->8642', ports_str)
                if pm:
                    host_port = int(pm.group(1))
                containers.append({
                    "name": name,
                    "container_id": parts[0],
                    "image": parts[2] if len(parts) > 2 else '',
                    "status": parts[3] if len(parts) > 3 else 'running',
                    "instance_id": instance_id,
                    "agent_id": agent_id,
                    "host_port": host_port,
                })
        return {"containers": containers}
    except Exception as e:
        return {"containers": [], "error": str(e)}


@router.post("/api/containers/{name}/stop")
def stop_container(name: str):
    """Stop a running agent container via podman."""
    import subprocess
    try:
        result = subprocess.run(
            ["podman", "stop", name],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            return {"message": f"Container {name} stopped", "name": name}
        else:
            return {"message": f"Failed: {result.stderr}", "name": name}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/containers/{name}/chat")
def send_to_container(name: str, data: dict):
    """Send a message to container agent. Calls LLM and writes response to output.json."""
    import time
    import subprocess
    import shlex
    content = data.get("content", "")
    if not content:
        raise HTTPException(status_code=400, detail="content required")

    instance_id = name.replace('agent-', '')
    shared_dir = os.path.join(os.path.expanduser("~"), ".sconsole", "shared", instance_id)
    input_file = os.path.join(shared_dir, "input.json")
    output_file = os.path.join(shared_dir, "output.json")

    os.makedirs(shared_dir, exist_ok=True)

    # Write input
    with open(input_file, "w", encoding="utf-8") as f:
        json.dump({"content": content, "timestamp": time.time()}, f)

    # Read agent personality
    soul, memory = "", ""
    soul_file = os.path.join(shared_dir, "SOUL.md")
    memory_file = os.path.join(shared_dir, "MEMORY.md")
    if os.path.exists(soul_file):
        with open(soul_file, "r") as f:
            soul = f.read().strip()
    if os.path.exists(memory_file):
        with open(memory_file, "r") as f:
            memory = f.read().strip()

    # Call LLM via hermes CLI
    system_prompt = soul
    if memory:
        system_prompt += f"\n\n{memory}"
    if system_prompt:
        full_prompt = f"[System: {system_prompt}]\n\nUser: {content}"
    else:
        full_prompt = content

    try:
        cmd = f"/home/dpfs/.local/bin/hermes chat -q {shlex.quote(full_prompt)} --max-turns 1 --yolo"
        result = subprocess.run(
            cmd, shell=True,
            capture_output=True, text=True, timeout=120,
            env={**os.environ, "HOME": "/home/dpfs"},
        )
        output = result.stdout

        # Extract response
        lines = output.split('\n')
        response_lines = []
        for line in lines:
            if '──' in line or '⚕' in line or line.strip().startswith('│'):
                continue
            stripped = line.strip()
            if stripped and not stripped.startswith('Query:') and \
               not stripped.startswith('Initializing') and \
               not stripped.startswith('──') and \
               not stripped.startswith('Iteration') and \
               not stripped.startswith('Resume') and \
               not stripped.startswith('Session:') and \
               not stripped.startswith('Duration:') and \
               not stripped.startswith('Messages:'):
                response_lines.append(stripped)

        reply = ' '.join(response_lines).strip()
        if not reply and result.stderr:
            reply = f"[Error] {result.stderr[:200]}"
        elif not reply:
            reply = "[Agent] No response."

    except subprocess.TimeoutExpired:
        reply = "[Error] LLM request timed out."
    except Exception as e:
        reply = f"[Error] {type(e).__name__}: {str(e)[:200]}"

    # Write response
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump({"content": reply, "timestamp": time.time()}, f)

    return {"message": "Message sent", "instance_id": instance_id, "preview": reply[:100]}


@router.get("/api/containers/{name}/response")
def get_container_response(name: str):
    """Poll for agent response from shared directory output.json."""
    instance_id = name.replace('agent-', '')
    output_file = os.path.join(
        os.path.expanduser("~"), ".sconsole", "shared", instance_id, "output.json",
    )

    if os.path.exists(output_file):
        try:
            with open(output_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return {
                "response": data.get("content", ""),
                "timestamp": data.get("timestamp", 0),
            }
        except (json.JSONDecodeError, IOError):
            return {"response": "", "timestamp": 0}
    return {"response": "", "timestamp": 0}


# ─── Agent Logs ──────────────────────────────────────────────────────

@router.get("/api/instances/{instance_id}/agents/{agent_id}/logs")
def get_agent_logs(instance_id: int, agent_id: int, tail: int = 200):
    """Get container logs for an agent."""
    import subprocess
    agent = AgentService.get_instance_agent(agent_id)
    if not agent or agent["instance_id"] != instance_id:
        raise HTTPException(status_code=404, detail="Agent not found")

    container_name = f"agent-{instance_id}-{agent_id}"
    # Also try legacy naming
    if not agent.get("container_id"):
        container_name = f"agent-{instance_id}"

    try:
        result = subprocess.run(
            ["podman", "logs", "--tail", str(tail), container_name],
            capture_output=True, text=True, timeout=10,
        )
        return {"logs": result.stdout, "stderr": result.stderr[:500] if result.stderr else ""}
    except subprocess.TimeoutExpired:
        return {"logs": "", "error": "Timeout fetching logs"}
    except Exception as e:
        return {"logs": "", "error": str(e)}


# ─── Workspace Activity (aggregated agent logs) ──────────────────────

@router.get("/api/instances/{instance_id}/activity")
def get_workspace_activity(instance_id: int, tail: int = 80):
    """Get categorized activity from all agents in a workspace."""
    import subprocess, re
    agents = AgentService.list_instance_agents(instance_id)
    master = AgentService.get_master_agent(instance_id)

    activity = []
    all_agents = [a for a in agents if a.get("container_id") or a.get("status") == "running"]
    if master:
        all_agents = [master] + [a for a in all_agents if a["id"] != master["id"]]

    for agent in all_agents:
        container_name = f"agent-{instance_id}-{agent['id']}"
        try:
            result = subprocess.run(
                ["podman", "logs", "--tail", str(tail), container_name],
                capture_output=True, text=True, timeout=8,
            )
            raw = result.stdout
        except Exception:
            raw = ""

        # Categorize log lines
        conversation = []
        work = []
        for line in raw.split('\n'):
            stripped = line.strip()
            if not stripped:
                continue
            # Skip hermes UI frames
            if any(c in stripped for c in ['───', '┌', '└', '┘', '┐', '│  ']):
                continue
            # Conversation lines
            if any(kw in stripped.lower() for kw in ['query:', 'user:', '你好', '请', '帮我', '?', '？', 'Response:']):
                conversation.append(stripped)
            else:
                work.append(stripped)

        entry = {
            "agent_id": agent["id"],
            "name": agent.get("name", f"Agent #{agent['id']}"),
            "role": agent.get("role", "worker"),
            "status": agent.get("status", "?"),
        }

        if agent["role"] == "master":
            entry["conversation"] = '\n'.join(conversation[-30:]) if conversation else "(等待用户输入)"
            entry["work"] = '\n'.join(work[-40:]) if work else "(空闲)"
        else:
            # Worker: task assignment from master + own work
            entry["task"] = '\n'.join(conversation[-15:]) if conversation else "(等待任务分配)"
            entry["work"] = '\n'.join(work[-30:]) if work else "(空闲)"

        activity.append(entry)

    return {"activity": activity}


# ─── Communicate (Hermes API proxy + conversation recording) ──────────

@router.post("/api/communicate")
async def api_communicate(data: dict):
    """Proxy to hermes agent API and record the conversation.

    Request body (see workspaceApi.md):
        agent_port  (required)  - agent port (e.g. 18000)
        conversation_id (optional) - hermes conversation ID
        input       (required)  - user message / query string
        store       (optional)  - whether to store (default true)
        api_key     (required)  - API key for hermes agent authentication

    This calls POST http://host:port/v1/responses on the hermes agent,
    then records the full interaction into SCL_agent_conversations.
    """
    agent_port = data.get("agent_port")
    conversation_id = data.get("conversation_id", "")
    user_input = data.get("input", "")
    store = data.get("store", True)
    api_key = data.get("api_key", "")

    if not agent_port:
        raise HTTPException(status_code=400, detail="agent_port required")
    if not user_input:
        raise HTTPException(status_code=400, detail="input required")
    if not api_key:
        raise HTTPException(status_code=400, detail="api_key required")

    # Determine agent_id and instance_id from port mapping across all instances
    agent_id = 0
    instance_id = 0
    all_instances = AgentService.list_instances()
    for inst in all_instances:
        agents = AgentService.list_instance_agents(inst["id"])
        for a in agents:
            if a.get("host_port") == agent_port or a.get("host_port") == int(agent_port):
                agent_id = a["id"]
                instance_id = inst["id"]
                break
        if agent_id > 0:
            break

    # If port doesn't match a known agent, still proceed but agent_id = 0, instance_id = 0

    hermes_url = f"http://127.0.0.1:{agent_port}/v1/responses"
    use_stream = data.get("stream", True)  # default: streaming
    payload = {
        "model": "hermes-agent",
        "input": user_input,
        "store": store,
        "stream": use_stream,
    }
    if conversation_id:
        payload["conversation"] = conversation_id

    # Immediately insert a pending record
    record_id = AgentService.insert_pending_conversation(
        instance_id=instance_id,
        agent_id=agent_id,
        conversation_id=conversation_id or "",
        user_input=user_input,
    )

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    if not use_stream:
        # ── Non-streaming (legacy fallback) ──
        try:
            async with httpx.AsyncClient(timeout=600.0) as client:
                resp = await client.post(hermes_url, json=payload, headers=headers)
                result = resp.json()
                # Check for Hermes error responses (e.g. invalid API key → 401)
                if resp.status_code != 200 or "error" in result:
                    error_detail = result.get("error", {})
                    if isinstance(error_detail, dict):
                        error_msg = error_detail.get("message", str(error_detail))
                    else:
                        error_msg = str(error_detail)
                    if not error_msg:
                        error_msg = f"Agent returned HTTP {resp.status_code}"
                    AgentService.update_conversation_record(
                        record_id=record_id, output=[], usage_info={},
                        status="error", error_msg=error_msg,
                    )
                    return {"code": resp.status_code, "status": "error", "conversation_id": conversation_id or "", "output": [], "error": error_msg}
                output = result.get("output", [])
                usage_info = result.get("usage", {})
                AgentService.update_conversation_record(
                    record_id=record_id, output=output,
                    usage_info=usage_info, status="completed",
                )
                return {
                    "code": 0, "status": "success",
                    "conversation_id": result.get("id", ""), "output": output,
                }
        except httpx.ConnectError:
            error_msg = f"Cannot connect to hermes agent at port {agent_port}"
            AgentService.update_conversation_record(
                record_id=record_id, output=[], usage_info={},
                status="error", error_msg=error_msg,
            )
            return {"code": 502, "status": "error", "conversation_id": conversation_id or "", "output": [], "error": error_msg}
        except httpx.TimeoutException:
            error_msg = "Agent 处理超时（超过 10 分钟）。"
            AgentService.update_conversation_record(
                record_id=record_id, output=[], usage_info={},
                status="error", error_msg=error_msg,
            )
            return {"code": 504, "status": "error", "conversation_id": conversation_id or "", "output": [], "error": error_msg}
        except Exception as e:
            error_msg = str(e)
            AgentService.update_conversation_record(
                record_id=record_id, output=[], usage_info={},
                status="error", error_msg=error_msg,
            )
            return {"code": 500, "status": "error", "conversation_id": conversation_id or "", "output": [], "error": error_msg}

    # ── Streaming mode (default) ──
    async def sse_stream():
        """Proxy SSE events from Hermes, accumulate output for DB."""
        accumulated_output = []
        accumulated_usage = {}
        try:
            async with httpx.AsyncClient(timeout=600.0) as client:
                async with client.stream("POST", hermes_url, json=payload, headers=headers) as resp:
                    if resp.status_code != 200:
                        body = await resp.aread()
                        error_msg = f"Hermes error {resp.status_code}: {body.decode('utf-8','replace')[:300]}"
                        try:
                            AgentService.update_conversation_record(
                                record_id=record_id, output=[], usage_info={},
                                status="error", error_msg=error_msg,
                            )
                        except Exception:
                            pass
                        yield f"event: error\ndata: {{\"error\": \"{error_msg}\"}}\n\n"
                        return

                    async for line in resp.aiter_lines():
                        yield line + "\n"

                        if line.startswith("data: "):
                            try:
                                evt = json.loads(line[6:])
                                if evt.get("type") == "response.completed":
                                    resp_data = evt.get("response", {})
                                    accumulated_output = resp_data.get("output", [])
                                    accumulated_usage = resp_data.get("usage", {})
                            except json.JSONDecodeError:
                                pass

                    # After stream completes, update DB
                    try:
                        AgentService.update_conversation_record(
                            record_id=record_id,
                            output=accumulated_output,
                            usage_info=accumulated_usage,
                            status="completed",
                        )
                    except Exception:
                        pass

        except httpx.ConnectError:
            error_msg = f"Cannot connect to hermes agent at port {agent_port}"
            try:
                AgentService.update_conversation_record(
                    record_id=record_id, output=[], usage_info={},
                    status="error", error_msg=error_msg,
                )
            except Exception:
                pass
            yield f"event: error\ndata: {{\"error\": \"{error_msg}\"}}\n\n"
        except Exception as e:
            error_msg = str(e)
            try:
                AgentService.update_conversation_record(
                    record_id=record_id, output=accumulated_output,
                    usage_info=accumulated_usage, status="error", error_msg=error_msg,
                )
            except Exception:
                pass
            yield f"event: error\ndata: {{\"error\": \"{error_msg}\"}}\n\n"

    return StreamingResponse(sse_stream(), media_type="text/event-stream")

def record_conversation(instance_id: int, agent_id: int, conversation_id: str,
                        user_input: str, result: dict = None,
                        error_msg: str = ""):
    """Record a conversation turn to the database.
    
    Supports both hermes response format ({output: [...], usage: {...}})
    and OpenAI chat/completion format ({choices: [...], usage: {...}}).
    """
    if result:
        # Hermes response format
        output = result.get("output", [])
        # Chat completion format: convert choices to output steps
        if not output and "choices" in result:
            choices = result.get("choices", [])
            if choices:
                msg = choices[0].get("message", {})
                content = msg.get("content", "")
                output = [{
                    "type": "message",
                    "role": msg.get("role", "assistant"),
                    "content": [{"text": content}],
                }]
        usage_info = result.get("usage", {})
    else:
        output = []
        usage_info = {}
    status = "completed" if result and not error_msg else "error"
    AgentService.record_conversation(
        instance_id=instance_id,
        agent_id=agent_id,
        conversation_id=conversation_id,
        user_input=user_input,
        output=output,
        usage_info=usage_info,
        status=status,
        error_msg=error_msg,
    )


# ─── Agent Conversation History (monitor view) ───────────────────────

@router.get("/api/instances/{instance_id}/agents/{agent_id}/conversations")
def get_agent_conversations(instance_id: int, agent_id: int, limit: int = 50):
    """Get recorded conversation history for a specific agent."""
    agent = AgentService.get_instance_agent(agent_id)
    if not agent or agent["instance_id"] != instance_id:
        raise HTTPException(status_code=404, detail="Agent not found")
    return {"conversations": AgentService.get_agent_conversations(instance_id, agent_id, limit)}


@router.get("/api/instances/{instance_id}/agents/{agent_id}/conversations/{conv_id}")
def get_agent_conversation_detail(instance_id: int, agent_id: int, conv_id: int):
    """Get a single conversation record by ID."""
    detail = AgentService.get_conversation_detail(conv_id)
    if not detail or detail["instance_id"] != instance_id:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return detail


@router.get("/api/instances/{instance_id}/conversations")
def get_instance_conversations(instance_id: int, limit: int = 100):
    """Get all conversation records for a workspace."""
    return {"conversations": AgentService.get_agent_conversations(instance_id, 0, limit)}


# ─── Conversation Delete ────────────────────────────────────────────

@router.delete("/api/conversations/{conv_id}")
def delete_conversation(conv_id: int):
    """Delete a single conversation record."""
    ok = AgentService.delete_conversation(conv_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"message": "Conversation deleted", "id": conv_id}


@router.post("/api/conversations/batch-delete")
def batch_delete_conversations(data: dict):
    """Delete multiple conversation records at once."""
    ids = data.get("ids", [])
    if not ids:
        raise HTTPException(status_code=400, detail="No IDs provided")
    count = AgentService.batch_delete_conversations(ids)
    return {"message": f"Deleted {count} conversation(s)", "deleted": count}


@router.delete("/api/conversations/by-conv-id/{conversation_id:path}")
def delete_conversations_by_conv_id(conversation_id: str):
    """Delete all records with the given conversation_id."""
    if not conversation_id:
        raise HTTPException(status_code=400, detail="conversation_id required")
    count = AgentService.delete_conversations_by_conv_id(conversation_id)
    return {"message": f"Deleted {count} record(s)", "deleted": count}





# ─── Agent File Upload ────────────────────────────────────────────

def _get_upload_dir(workspace_id: int) -> str:
    d = os.path.join(AGENT_UPLOAD_DIR, str(workspace_id))
    os.makedirs(d, exist_ok=True)
    return d


@router.post("/api/workspaces/{workspace_id}/upload")
async def agent_upload_file(workspace_id: int, file: UploadFile = File(...)):
    """Agent uploads a file to the workspace."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="filename required")
    safe_name = os.path.basename(file.filename)
    if not safe_name or safe_name in (".", ".."):
        raise HTTPException(status_code=400, detail="invalid filename")
    upload_dir = _get_upload_dir(workspace_id)
    dest = os.path.join(upload_dir, safe_name)
    content = await file.read()
    with open(dest, "wb") as f:
        f.write(content)
    return {"message": "File uploaded", "filename": safe_name, "size": len(content)}


@router.get("/api/workspaces/{workspace_id}/files")
def list_workspace_files(workspace_id: int):
    """List uploaded files for a workspace."""
    upload_dir = _get_upload_dir(workspace_id)
    files = []
    for name in sorted(os.listdir(upload_dir)):
        path = os.path.join(upload_dir, name)
        if os.path.isfile(path):
            files.append({
                "name": name,
                "size": os.path.getsize(path),
                "modified": os.path.getmtime(path),
            })
    return {"workspace_id": workspace_id, "files": files}


@router.get("/api/workspaces/{workspace_id}/files/{filename:path}")
def download_workspace_file(workspace_id: int, filename: str):
    """Download an uploaded file."""
    safe_name = os.path.basename(filename)
    path = os.path.join(_get_upload_dir(workspace_id), safe_name)
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="File not found")
    return StreamingResponse(
        open(path, "rb"),
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}"'}
    )


@router.delete("/api/workspaces/{workspace_id}/files/{filename:path}")
def delete_workspace_file(workspace_id: int, filename: str):
    """Delete an uploaded file."""
    safe_name = os.path.basename(filename)
    path = os.path.join(_get_upload_dir(workspace_id), safe_name)
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="File not found")
    os.remove(path)
    return {"message": "File deleted", "filename": safe_name}


# ─── Chat file upload: save to agent's shared volume ────────────────

@router.post("/api/workspaces/{workspace_id}/agents/{agent_id}/upload-file")
async def upload_file_to_agent(workspace_id: int, agent_id: int, file: UploadFile = File(...)):
    """Upload a file to the agent's shared volume so the agent can access it."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="filename required")
    safe_name = os.path.basename(file.filename)
    if not safe_name or safe_name in (".", ".."):
        raise HTTPException(status_code=400, detail="invalid filename")

    shared_dir = os.path.join(
        os.path.expanduser("~"), ".sconsole", "shared",
        str(workspace_id), str(agent_id)
    )
    os.makedirs(shared_dir, exist_ok=True)
    dest = os.path.join(shared_dir, safe_name)
    content = await file.read()
    with open(dest, "wb") as f:
        f.write(content)
    return {
        "message": "File uploaded to agent shared volume",
        "filename": safe_name,
        "size": len(content),
        "path": f"/agent/shared/{safe_name}",
    }


# ─── Workspace config view ──────────────────────────────────────────

@router.get("/api/workspaces/{workspace_id}/config")
def get_workspace_config(workspace_id: int):
    """Return the configuration summary for all agents in a workspace."""
    agents = AgentService.list_instance_agents(workspace_id)
    result = {"workspace_id": workspace_id, "agents": []}
    for a in agents:
        cfg = AgentService.get_config(a.get("config_id", 0))
        cfg_info = None
        if cfg:
            cfg_info = {
                "name": cfg.get("name", ""),
                "model_name": cfg.get("model_name", ""),
                "model_provider": cfg.get("model_provider", ""),
                "model_url": cfg.get("model_url", ""),
                "proxy": cfg.get("proxy", ""),
                "skills": cfg.get("skills", []),
            }
        elif a.get("role") == "master":
            cfg_info = {
                "name": "系统生成 (Master SOUL)",
                "model_name": a.get("model_name", "N/A"),
                "model_provider": "N/A",
                "model_url": "N/A",
                "proxy": "N/A",
                "skills": ["sconsole-intercom (内置)"],
            }
        result["agents"].append({
            "agent_id": a["id"],
            "agent_name": a["name"],
            "role": a.get("role", "worker"),
            "status": a.get("status", "pending"),
            "host_port": a.get("host_port", 0),
            "config": cfg_info,
        })
    return result
