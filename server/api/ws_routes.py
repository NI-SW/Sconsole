"""
Sconsole Server - WebSocket Handler
Manages real-time communication with consoles and nodes.
"""
import json
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from server.ws_manager import manager
from server.services.agent_service import AgentService
from server.services.node_service import NodeService

logger = logging.getLogger(__name__)
ws_router = APIRouter()


@ws_router.websocket("/ws/console/{console_id}")
async def console_websocket(ws: WebSocket, console_id: str):
    """WebSocket endpoint for the web console."""
    await ws.accept()
    await manager.connect_console(console_id, ws)
    try:
        while True:
            data = await ws.receive_json()
            msg_type = data.get("type", "")

            if msg_type == "agent_message":
                # User sends a message to an agent
                instance_id = data.get("instance_id")
                content = data.get("content", "")
                if instance_id and content:
                    inst = AgentService.get_instance(instance_id)
                    if inst:
                        # Forward to node
                        await manager.send_to_node(inst["node_id"], {
                            "type": "agent_input",
                            "instance_id": instance_id,
                            "content": content,
                        })

            elif msg_type == "bind_agent":
                # Bind console to a specific agent instance for streaming
                instance_id = data.get("instance_id")
                if instance_id:
                    manager.bind_agent_to_console(instance_id, ws)

            elif msg_type == "unbind_agent":
                instance_id = data.get("instance_id")
                if instance_id:
                    manager.unbind_agent(instance_id)

            elif msg_type == "list_nodes":
                nodes = NodeService.list_nodes()
                await ws.send_json({"type": "node_list", "nodes": nodes})

            elif msg_type == "list_instances":
                instances = AgentService.list_instances()
                await ws.send_json({"type": "instance_list", "instances": instances})

    except WebSocketDisconnect:
        manager.disconnect_console(console_id)
    except Exception as e:
        logger.error(f"Console WS error: {e}")
        manager.disconnect_console(console_id)


@ws_router.websocket("/ws/node/{node_id}")
async def node_websocket(ws: WebSocket, node_id: str):
    """WebSocket endpoint for compute nodes."""
    await ws.accept()
    await manager.connect_node(node_id, ws)
    try:
        while True:
            data = await ws.receive_json()
            msg_type = data.get("type", "")

            if msg_type == "register":
                # Node registration with system info
                NodeService.register_node(
                    node_id=node_id,
                    hostname=data.get("hostname", ""),
                    ip_address=data.get("ip_address", ""),
                    docker_version=data.get("docker_version", ""),
                    cpu_count=data.get("cpu_count", 0),
                    memory_mb=data.get("memory_mb", 0),
                )
                await ws.send_json({"type": "registered", "node_id": node_id})

            elif msg_type == "heartbeat":
                NodeService.update_heartbeat(node_id)

            elif msg_type == "agent_status":
                # Node reports agent container status change
                instance_id = data.get("instance_id")
                agent_id = data.get("agent_id", 0)
                status = data.get("status")
                container_id = data.get("container_id", "")
                host_port = data.get("host_port", 0)
                api_key = data.get("api_key", "")
                if instance_id and status:
                    if agent_id:
                        AgentService.update_agent_status(
                            agent_id, status,
                            container_id or None,
                            host_port, api_key,
                        )
                        # When agent becomes running, update master context
                        if status == "running":
                            master = AgentService.get_master_agent(instance_id)
                            # Update master context when:
                            # 1. A worker becomes running (needs to appear in master's context)
                            # 2. The master itself becomes running (master's own info needs updating)
                            if master:
                                ctx = AgentService.update_master_context(instance_id)
                                if ctx:
                                    # Only restart master when a *worker* becomes running.
                                    # Don't restart master on its own "running" event to avoid loops.
                                    if master["id"] != agent_id:
                                        inst = AgentService.get_instance(instance_id)
                                        if inst and master["status"] == "running":
                                            await manager.send_to_node(inst["node_id"], {
                                                "type": "restart_agent",
                                                "instance_id": instance_id,
                                                "agent_id": ctx["master_agent_id"],
                                            })
                    else:
                        AgentService.update_instance(instance_id, {"status": status})

                    # Auto-update workspace status based on agent states
                    if agent_id and status in ("running", "stopped", "error"):
                        try:
                            AgentService.sync_workspace_status(instance_id)
                        except Exception:
                            pass

                    # Notify bound console
                    await manager.send_agent_message(instance_id, {
                        "type": "agent_status",
                        "instance_id": instance_id,
                        "agent_id": agent_id,
                        "status": status,
                        "container_id": container_id,
                        "host_port": host_port,
                    })

            elif msg_type == "agent_output":
                # Node forwards agent output to console
                instance_id = data.get("instance_id")
                content = data.get("content", "")
                if instance_id and content:
                    await manager.send_agent_message(instance_id, {
                        "type": "agent_output",
                        "instance_id": instance_id,
                        "content": content,
                    })

            elif msg_type == "agent_log":
                # Log/execution progress
                instance_id = data.get("instance_id")
                log_data = data.get("data", {})
                if instance_id:
                    await manager.send_agent_message(instance_id, {
                        "type": "agent_log",
                        "instance_id": instance_id,
                        "data": log_data,
                    })

    except WebSocketDisconnect:
        manager.disconnect_node(node_id)
        NodeService.set_node_offline(node_id)
    except Exception as e:
        logger.error(f"Node WS error: {e}")
        manager.disconnect_node(node_id)
        NodeService.set_node_offline(node_id)
