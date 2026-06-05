"""
Sconsole Server - WebSocket Manager
Handles connections from consoles and nodes.
"""
import json
import asyncio
from typing import Dict, Set
from fastapi import WebSocket


class ConnectionManager:
    """Manages WebSocket connections for consoles and nodes."""

    def __init__(self):
        # node_id -> WebSocket
        self.nodes: Dict[str, WebSocket] = {}
        # console_id -> WebSocket
        self.consoles: Dict[str, WebSocket] = {}
        # agent_instance_id -> console WebSocket
        self.agent_consoles: Dict[int, WebSocket] = {}
        # agent_instance_id -> node_id
        self.agent_nodes: Dict[int, str] = {}

    async def connect_node(self, node_id: str, ws: WebSocket):
        """Register a node connection (WebSocket already accepted by FastAPI)."""
        self.nodes[node_id] = ws
        print(f"[WS] Node connected: {node_id}")

    def disconnect_node(self, node_id: str):
        """Remove a node connection."""
        self.nodes.pop(node_id, None)
        # Remove associated agents
        to_remove = [aid for aid, nid in self.agent_nodes.items() if nid == node_id]
        for aid in to_remove:
            self.agent_nodes.pop(aid, None)
        print(f"[WS] Node disconnected: {node_id}")

    async def connect_console(self, console_id: str, ws: WebSocket):
        """Register a console connection (WebSocket already accepted by FastAPI)."""
        self.consoles[console_id] = ws
        print(f"[WS] Console connected: {console_id}")

    def disconnect_console(self, console_id: str):
        """Remove a console connection."""
        self.consoles.pop(console_id, None)
        print(f"[WS] Console disconnected: {console_id}")

    def bind_agent_to_console(self, agent_instance_id: int, console_ws: WebSocket):
        """Bind an agent instance to a console for message streaming."""
        self.agent_consoles[agent_instance_id] = console_ws

    def unbind_agent(self, agent_instance_id: int):
        """Unbind an agent instance."""
        self.agent_consoles.pop(agent_instance_id, None)
        self.agent_nodes.pop(agent_instance_id, None)

    async def send_to_node(self, node_id: str, message: dict):
        """Send a command/message to a specific node."""
        ws = self.nodes.get(node_id)
        if ws:
            try:
                await ws.send_json(message)
                return True
            except Exception:
                self.disconnect_node(node_id)
        return False

    async def send_to_console(self, console_id: str, message: dict):
        """Send a message to a specific console."""
        ws = self.consoles.get(console_id)
        if ws:
            try:
                await ws.send_json(message)
                return True
            except Exception:
                self.disconnect_console(console_id)
        return False

    async def send_agent_message(self, agent_instance_id: int, message: dict):
        """Send a message from agent to its bound console."""
        ws = self.agent_consoles.get(agent_instance_id)
        if ws:
            try:
                await ws.send_json(message)
                return True
            except Exception:
                pass
        return False

    async def broadcast_to_nodes(self, message: dict):
        """Broadcast a message to all connected nodes."""
        for node_id in list(self.nodes.keys()):
            await self.send_to_node(node_id, message)

    def get_node_ids(self) -> list:
        """Get list of connected node IDs."""
        return list(self.nodes.keys())

    def get_console_ids(self) -> list:
        """Get list of connected console IDs."""
        return list(self.consoles.keys())


# Singleton instance
manager = ConnectionManager()
