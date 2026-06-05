"""
Sconsole Server - Node Service
Manages connected compute nodes.
"""
from typing import List, Optional
from datetime import datetime

from server.db.database import get_db


class NodeService:
    """Service for managing compute nodes."""

    @staticmethod
    def register_node(node_id: str, hostname: str, ip_address: str,
                      docker_version: str = "", cpu_count: int = 0,
                      memory_mb: int = 0) -> bool:
        """Register or update a node."""
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO SCL_nodes 
                       (node_id, hostname, ip_address, status, docker_version, 
                        cpu_count, memory_mb, last_heartbeat)
                       VALUES (%s,%s,%s,'online',%s,%s,%s,NOW())
                       ON DUPLICATE KEY UPDATE 
                       status='online', hostname=%s, ip_address=%s,
                       docker_version=%s, cpu_count=%s, memory_mb=%s,
                       last_heartbeat=NOW()""",
                    (node_id, hostname, ip_address, docker_version, cpu_count,
                     memory_mb, hostname, ip_address, docker_version,
                     cpu_count, memory_mb),
                )
                return True

    @staticmethod
    def update_heartbeat(node_id: str):
        """Update node heartbeat timestamp."""
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE SCL_nodes SET last_heartbeat = NOW() WHERE node_id = %s",
                    (node_id,),
                )

    @staticmethod
    def set_node_offline(node_id: str):
        """Mark a node as offline."""
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE SCL_nodes SET status = 'offline' WHERE node_id = %s",
                    (node_id,),
                )

    @staticmethod
    def list_nodes() -> List[dict]:
        """List all registered nodes."""
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM SCL_nodes ORDER BY last_heartbeat DESC")
                return [
                    {
                        "node_id": r[0],
                        "hostname": r[1],
                        "ip_address": r[2],
                        "status": r[3],
                        "docker_version": r[4] if r[4] else "",
                        "cpu_count": r[5],
                        "memory_mb": r[6],
                        "connected_at": str(r[7]) if r[7] else "",
                        "last_heartbeat": str(r[8]) if r[8] else "",
                    }
                    for r in cur.fetchall()
                ]

    @staticmethod
    def get_node(node_id: str) -> Optional[dict]:
        """Get a specific node."""
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM SCL_nodes WHERE node_id = %s", (node_id,)
                )
                r = cur.fetchone()
                if r:
                    return {
                        "node_id": r[0],
                        "hostname": r[1],
                        "ip_address": r[2],
                        "status": r[3],
                        "docker_version": r[4] if r[4] else "",
                        "cpu_count": r[5],
                        "memory_mb": r[6],
                        "connected_at": str(r[7]) if r[7] else "",
                        "last_heartbeat": str(r[8]) if r[8] else "",
                    }
        return None

    @staticmethod
    def delete_node(node_id: str) -> bool:
        """Remove a node."""
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM SCL_nodes WHERE node_id = %s", (node_id,))
                return cur.rowcount > 0
