"""
Sconsole Server - Agent Service
Manages agent configuration, instances (workspaces), and instance agents.
"""
import json
import os
import re
import shutil
from typing import List, Optional
from datetime import datetime

from server.models import AgentConfig, AgentInstance, InstanceAgent, Workspace
from server.db.database import get_db

# Path to master agent prompt template
MASTER_PROMPT_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "prompts", "masterAgent.md")


class AgentService:
    """Service for managing agent configurations, instances, and agents."""

    # ─── Config CRUD (unchanged) ─────────────────────────────────────

    @staticmethod
    def create_config(config: AgentConfig) -> int:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO SCL_agent_configs 
                       (name, soul_file, memory_file, tech_docs, 
                        model_url, model_api_key, model_name, model_provider, proxy,
                        skills, extra_env)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (
                        config.name,
                        config.soul_file,
                        config.memory_file,
                        config.tech_docs,
                        config.model_url,
                        config.model_api_key,
                        config.model_name,
                        config.model_provider,
                        config.proxy,
                        json.dumps(config.skills),
                        json.dumps(config.extra_env),
                    ),
                )
                return cur.lastrowid

    @staticmethod
    def get_config(config_id: int) -> Optional[dict]:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM SCL_agent_configs WHERE id = %s", (config_id,))
                row = cur.fetchone()
                if row:
                    return AgentService._row_to_config(row)
        return None

    @staticmethod
    def list_configs() -> List[dict]:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM SCL_agent_configs ORDER BY id DESC")
                return [AgentService._row_to_config(row) for row in cur.fetchall()]

    @staticmethod
    def update_config(config_id: int, updates: dict) -> bool:
        allowed = [
            "name", "soul_file", "memory_file", "tech_docs",
            "model_url", "model_api_key", "model_name", "model_provider", "proxy",
            "skills", "extra_env",
        ]
        set_clauses = []
        values = []
        for key in allowed:
            if key in updates:
                val = updates[key]
                # Skip empty model_api_key — means "don't change"
                if key == "model_api_key" and (val is None or val.strip() == ""):
                    continue
                if key in ("skills", "extra_env"):
                    val = json.dumps(val)
                set_clauses.append(f"{key} = %s")
                values.append(val)
        if not set_clauses:
            return False
        values.append(config_id)
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"UPDATE SCL_agent_configs SET {', '.join(set_clauses)}, "
                    f"updated_at = NOW() WHERE id = %s",
                    values,
                )
                return cur.rowcount > 0

    @staticmethod
    def get_config_agent_refs(config_id: int) -> list:
        """Return list of agents referencing this config."""
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT a.id, a.name, a.role, a.status, i.id as ws_id, i.name as ws_name "
                    "FROM SCL_instance_agents a "
                    "JOIN SCL_workspaces i ON a.instance_id = i.id "
                    "WHERE a.config_id = %s",
                    (config_id,),
                )
                rows = cur.fetchall()
                return [
                    {
                        "agent_id": r[0],
                        "agent_name": r[1],
                        "role": r[2],
                        "status": r[3],
                        "workspace_id": r[4],
                        "workspace_name": r[5],
                    }
                    for r in (rows or [])
                ]

    @staticmethod
    def delete_config(config_id: int) -> bool:
        # Delete associated aconfig files first
        cfg = AgentService.get_config(config_id)
        if cfg:
            cfg_name = cfg.get("name", "") or f"config-{config_id}"
            aconfig_dir = os.path.join(
                os.path.expanduser("~"), ".sconsole", "aconfig", cfg_name,
            )
            if os.path.isdir(aconfig_dir):
                shutil.rmtree(aconfig_dir)

        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM SCL_agent_configs WHERE id = %s", (config_id,))
                return cur.rowcount > 0

    # ─── Config File Tracking ──────────────────────────────────────────

    @staticmethod
    def get_attached_files(config_id: int) -> list:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT attached_files FROM SCL_agent_configs WHERE id = %s", (config_id,))
                row = cur.fetchone()
                if row and row[0]:
                    return json.loads(row[0]) if isinstance(row[0], str) else row[0]
        return []

    @staticmethod
    def update_attached_files(config_id: int, files: list):
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE SCL_agent_configs SET attached_files = %s, updated_at = NOW() WHERE id = %s",
                    (json.dumps(files), config_id),
                )

    # ─── Workspace CRUD ───────────────────────────────────────────────

    @staticmethod
    def create_instance(name: str, node_id: str, description: str = "") -> dict:
        """Create a new workspace with a master agent."""
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO SCL_workspaces 
                       (name, node_id, description, status)
                       VALUES (%s, %s, %s, 'pending')""",
                    (name, node_id, description),
                )
                instance_id = cur.lastrowid

                # Auto-create master agent
                cur.execute(
                    """INSERT INTO SCL_instance_agents 
                       (instance_id, config_id, name, description, role, status)
                       VALUES (%s, 0, 'Master', '', 'master', 'pending')""",
                    (instance_id,),
                )
                master_agent_id = cur.lastrowid
                return {"instance_id": instance_id, "master_agent_id": master_agent_id}

    @staticmethod
    def get_instance(instance_id: int) -> Optional[dict]:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT w.*, 
                        (SELECT COUNT(*) FROM SCL_instance_agents a WHERE a.instance_id = w.id) AS agent_count, 
                        (SELECT id FROM SCL_instance_agents b WHERE b.instance_id = w.id AND `role`='master') AS master_id
                        FROM SCL_workspaces w WHERE w.id = %s""",
                    (instance_id,),
                )
                row = cur.fetchone()
                if row:
                    return AgentService._row_to_workspace(row)
        return None

    @staticmethod
    def list_instances(status: Optional[str] = None) -> List[dict]:
        with get_db() as conn:
            with conn.cursor() as cur:
                where = "WHERE status = %s" if status else ""
                params = (status,) if status else ()
                cur.execute(
                    f"""SELECT w.*, 
                        (SELECT COUNT(*) FROM SCL_instance_agents a WHERE a.instance_id = w.id) AS agent_count, 
                        (select id from SCL_instance_agents b where b.instance_id = w.id and `role`='master') AS master_id
                        FROM SCL_workspaces w {where} ORDER BY w.id DESC""",
                    params,
                )
                return [AgentService._row_to_workspace(row) for row in cur.fetchall()]

    @staticmethod
    def update_instance(instance_id: int, updates: dict) -> bool:
        valid_statuses = ("pending", "running", "stopped", "error")
        if "status" in updates and updates["status"] not in valid_statuses:
            raise ValueError(f"Invalid status '{updates['status']}'. Must be one of: {', '.join(valid_statuses)}")
        allowed = ["name", "description", "status", "node_id"]
        set_clauses = []
        values = []
        for key in allowed:
            if key in updates:
                set_clauses.append(f"{key} = %s")
                values.append(updates[key])
        if not set_clauses:
            return False
        values.append(instance_id)
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"UPDATE SCL_workspaces SET {', '.join(set_clauses)}, "
                    f"updated_at = NOW() WHERE id = %s",
                    values,
                )
                return cur.rowcount > 0

    @staticmethod
    def delete_instance(instance_id: int) -> bool:
        """Delete a workspace and all its associated DB records (agents,
        conversations, messages, files)."""
        with get_db() as conn:
            with conn.cursor() as cur:
                # 1. Get all agent IDs for this workspace
                cur.execute(
                    "SELECT id FROM SCL_instance_agents WHERE instance_id = %s",
                    (instance_id,),
                )
                agent_ids = [row[0] for row in cur.fetchall()]

                # 2. Delete messages & conversations for each agent
                if agent_ids:
                    placeholders = ",".join(["%s"] * len(agent_ids))
                    cur.execute(
                        f"DELETE FROM SCL_agent_messages_v3 "
                        f"WHERE instance_agent_id IN ({placeholders})",
                        agent_ids,
                    )
                    # conversations uses (instance_id, agent_id), not instance_agent_id
                    cur.execute(
                        f"DELETE FROM SCL_agent_conversations "
                        f"WHERE instance_id = %s AND agent_id IN ({placeholders})",
                        [instance_id] + agent_ids,
                    )

                # 3. Delete agent records
                cur.execute(
                    "DELETE FROM SCL_instance_agents WHERE instance_id = %s",
                    (instance_id,),
                )

                # 4. Finally delete the workspace itself
                cur.execute(
                    "DELETE FROM SCL_workspaces WHERE id = %s", (instance_id,)
                )
                return cur.rowcount > 0

    # ─── Instance Agent CRUD ──────────────────────────────────────────

    @staticmethod
    def create_instance_agent(instance_id: int, config_id: int, name: str, description: str = "") -> Optional[int]:
        """Create a new agent within an instance."""
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO SCL_instance_agents 
                       (instance_id, config_id, name, description, status)
                       VALUES (%s, %s, %s, %s, 'pending')""",
                    (instance_id, config_id, name, description),
                )
                return cur.lastrowid

    @staticmethod
    def get_instance_agent(agent_id: int) -> Optional[dict]:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM SCL_instance_agents WHERE id = %s", (agent_id,)
                )
                row = cur.fetchone()
                if row:
                    return AgentService._row_to_agent(row)
        return None

    @staticmethod
    def get_master_agent(instance_id: int) -> Optional[dict]:
        """Get the master agent for a workspace."""
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM SCL_instance_agents WHERE instance_id = %s AND role = 'master' LIMIT 1",
                    (instance_id,),
                )
                row = cur.fetchone()
                if row:
                    return AgentService._row_to_agent(row)
        return None

    @staticmethod
    def get_workspace_agents_info(instance_id: int, exclude_master: bool = True) -> List[dict]:
        """Get all agents in a workspace with their config details for inter-agent communication."""
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT a.id, a.name, a.role, a.status, a.host_port, a.container_id,
                               c.name AS config_name, a.api_key
                       FROM SCL_instance_agents a
                       LEFT JOIN SCL_agent_configs c ON a.config_id = c.id
                       WHERE a.instance_id = %s
                       ORDER BY a.role DESC, a.id ASC""",
                    (instance_id,),
                )
                agents = []
                for row in cur.fetchall():
                    agent = {
                        "id": row[0],
                        "name": row[1] or "",
                        "role": row[2] or "worker",
                        "status": row[3] or "pending",
                        "host_port": row[4] or 0,
                        "container_id": (row[5] or "")[:12],
                        "config_name": row[6] or "",
                        "api_key": row[7] or "",
                    }
                    if exclude_master and agent["role"] == "master":
                        continue
                    agents.append(agent)
                return agents

    @staticmethod
    def build_master_soul(instance_id: int, master_agent_id: int,
                         worker_descriptions: dict = None) -> str:
        """Build the master agent's SOUL prompt with worker agent information.

        Args:
            instance_id: Workspace ID
            master_agent_id: Master agent ID
            worker_descriptions: Optional dict {agent_id: "custom description"}
        """
        worker_descriptions = worker_descriptions or {}
        # Read template
        template = ""
        if os.path.exists(MASTER_PROMPT_PATH):
            with open(MASTER_PROMPT_PATH, "r", encoding="utf-8") as f:
                template = f.read()

        if not template:
            template = "你是一个智能调度中心（Master Agent），负责协调子 Agent 完成任务。"

        # Get host IP for inter-agent communication
        host_ip = "127.0.0.1"
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT n.ip_address FROM SCL_workspaces w "
                    "JOIN SCL_nodes n ON w.node_id COLLATE utf8mb4_unicode_ci = n.node_id "
                    "WHERE w.id = %s", (instance_id,),
                )
                row = cur.fetchone()
                if row and row[0]:
                    host_ip = row[0]

        # Get worker agents
        workers = AgentService.get_workspace_agents_info(instance_id, exclude_master=True)

        # Build sub-agent list for prompt
        sub_lines = []
        for i, w in enumerate(workers):
            port = w["host_port"]
            w_id = w["id"]
            # Use custom description if provided, otherwise use config name
            desc = str(worker_descriptions.get(str(w_id), "") or worker_descriptions.get(w_id, ""))
            if not desc:
                desc = w["config_name"] or f"Worker Agent #{w['id']}"
            worker_api_key = w.get("api_key", "")
            status_note = "运行中" if w["status"] == "running" else w["status"]
            api_params = f"agent_port={port}, api_key={worker_api_key}"
            sub_lines.append(f"{i+1}. **{w['name']}** (ID:{w_id}, {status_note}): {desc} — 调用参数: {api_params}")

        if sub_lines:
            sub_section = "\n".join(sub_lines)
        else:
            sub_section = "（当前无可用子 Agent，请先部署 Worker Agent）"

        # Replace placeholder section
        soul = re.sub(
            r'## 可调用的子 Agent.*?(?=## Agent调用规则|## 工作原则|\Z)',
            f'## 可调用的子 Agent\n{sub_section}\n',
            template,
            flags=re.DOTALL,
        )

        # Append workspace context
        soul += f"\n\n## 当前工作空间\n"
        soul += f"- 工作空间 ID: {instance_id}\n"
        soul += f"- Master Agent ID: {master_agent_id}\n"
        soul += f"- Worker 数量: {len(workers)}\n"
        soul += f"- 容器网络: agent-{instance_id}-* 可通过容器名互相访问\n"

        return soul

    @staticmethod
    def build_agents_json(instance_id: int, master_agent_id: int) -> dict:
        """Build agents.json for runtime agent discovery."""
        agents = AgentService.get_workspace_agents_info(instance_id, exclude_master=False)
        return {
            "instance_id": instance_id,
            "master_agent_id": master_agent_id,
            "agents": agents,
        }

    @staticmethod
    def update_master_context(instance_id: int) -> Optional[dict]:
        """Rebuild and write master agent context files.

        Called when agents are added/removed from a workspace.
        Returns {master_agent_id, soul_path, agents_json_path} or None.
        """
        master = AgentService.get_master_agent(instance_id)
        if not master:
            return None

        master_id = master["id"]

        # Shared directory for this agent
        shared_dir = os.path.join(
            os.path.expanduser("~"), ".sconsole", "shared",
            str(instance_id), str(master_id),
        )
        os.makedirs(shared_dir, exist_ok=True)

        # Rebuild context (always write, even if master not running — will be picked up on start)
        # Try to read previously saved custom descriptions
        custom_desc = {}
        desc_file = os.path.join(shared_dir, "agent_descriptions.json")
        if os.path.exists(desc_file):
            try:
                with open(desc_file, "r", encoding="utf-8") as f:
                    custom_desc = json.load(f)
            except Exception:
                pass

        soul = AgentService.build_master_soul(instance_id, master_id, custom_desc)

        # Append agent config prompt
        agent_cfg_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "prompts", "agentConfig.md",
        )
        if os.path.exists(agent_cfg_path):
            with open(agent_cfg_path, "r", encoding="utf-8") as f:
                agent_cfg = f.read()
            if agent_cfg:
                soul += "\n\n" + agent_cfg

        agents_json = json.dumps(
            AgentService.build_agents_json(instance_id, master_id),
            ensure_ascii=False,
        )

        # Write to shared directory
        soul_path = os.path.join(shared_dir, "SOUL.md")
        with open(soul_path, "w", encoding="utf-8") as f:
            f.write(soul)

        # Clear MEMORY.md for master (only SOUL is used)
        memory_path = os.path.join(shared_dir, "MEMORY.md")
        if os.path.exists(memory_path):
            os.remove(memory_path)

        agents_path = os.path.join(shared_dir, "agents.json")
        with open(agents_path, "w", encoding="utf-8") as f:
            f.write(agents_json)

        return {
            "master_agent_id": master_id,
            "soul_path": soul_path,
            "agents_json_path": agents_path,
        }

    @staticmethod
    def list_instance_agents(instance_id: int, status: Optional[str] = None) -> List[dict]:
        with get_db() as conn:
            with conn.cursor() as cur:
                if status:
                    cur.execute(
                        "SELECT * FROM SCL_instance_agents WHERE instance_id = %s AND status = %s ORDER BY id DESC",
                        (instance_id, status),
                    )
                else:
                    cur.execute(
                        "SELECT * FROM SCL_instance_agents WHERE instance_id = %s ORDER BY id DESC",
                        (instance_id,),
                    )
                return [AgentService._row_to_agent(row) for row in cur.fetchall()]

    @staticmethod
    def update_agent_status(agent_id: int, status: str, container_id: str = None,
                            host_port: int = 0, api_key: str = ""):
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """UPDATE SCL_instance_agents 
                       SET status = %s, container_id = %s, host_port = %s, api_key = %s,
                           updated_at = NOW() 
                       WHERE id = %s""",
                    (status, container_id or "", host_port, api_key, agent_id),
                )

    @staticmethod
    def delete_instance_agent(agent_id: int) -> bool:
        # Clean up shared directory
        agent = AgentService.get_instance_agent(agent_id)
        if agent:
            shared_dir = os.path.join(
                os.path.expanduser("~"), ".sconsole", "shared",
                str(agent["instance_id"]), str(agent_id),
            )
            if os.path.isdir(shared_dir):
                shutil.rmtree(shared_dir)

        with get_db() as conn:
            with conn.cursor() as cur:
                # Cascade: delete messages & conversations first
                cur.execute(
                    "DELETE FROM SCL_agent_messages_v3 WHERE instance_agent_id = %s",
                    (agent_id,),
                )
                # conversations uses (instance_id, agent_id)
                if agent:
                    cur.execute(
                        "DELETE FROM SCL_agent_conversations WHERE instance_id = %s AND agent_id = %s",
                        (agent["instance_id"], agent_id),
                    )
                # Then delete the agent record
                cur.execute("DELETE FROM SCL_instance_agents WHERE id = %s", (agent_id,))
                return cur.rowcount > 0

    # ─── Messages ─────────────────────────────────────────────────────

    @staticmethod
    def save_message(instance_agent_id: int, direction: str, content: str, msg_type: str = "text"):
        """Save a message to the database (uses instance_agent_id as FK)."""
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO SCL_agent_messages_v3 
                       (instance_agent_id, direction, content, message_type)
                       VALUES (%s, %s, %s, %s)""",
                    (instance_agent_id, direction, content, msg_type),
                )

    @staticmethod
    def get_messages(instance_agent_id: int, limit: int = 100) -> List[dict]:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT * FROM SCL_agent_messages_v3 
                       WHERE instance_agent_id = %s 
                       ORDER BY id DESC LIMIT %s""",
                    (instance_agent_id, limit),
                )
                rows = list(cur.fetchall())
                rows.reverse()
                return [
                    {
                        "id": r[0],
                        "instance_agent_id": r[1],
                        "direction": r[2],
                        "content": r[3],
                        "message_type": r[4],
                        "created_at": str(r[5]) if r[5] else "",
                    }
                    for r in rows
                ]

    # ─── Conversations (hermes monitor) ──────────────────────────────

    @staticmethod
    def record_conversation(instance_id: int, agent_id: int, conversation_id: str,
                            user_input: str, output: list, usage_info: dict,
                            status: str = "completed", error_msg: str = "") -> int:
        """Record a hermes agent conversation turn into SCL_agent_conversations."""
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO SCL_agent_conversations
                       (instance_id, agent_id, conversation_id, user_input, output, usage_info, status, error_msg)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                    (instance_id, agent_id, conversation_id or "",
                     user_input or "",
                     json.dumps(output) if output else "[]",
                     json.dumps(usage_info) if usage_info else "{}",
                     status,
                     error_msg or ""),
                )
                return cur.lastrowid

    @staticmethod
    def get_agent_conversations(instance_id: int, agent_id: int = 0, limit: int = 50) -> List[dict]:
        """Get conversation history for an agent within an instance."""
        with get_db() as conn:
            with conn.cursor() as cur:
                if agent_id > 0:
                    cur.execute(
                        """SELECT id, instance_id, agent_id, conversation_id, user_input,
                                  output, usage_info, status, error_msg, created_at
                           FROM SCL_agent_conversations
                           WHERE instance_id = %s AND agent_id = %s
                           ORDER BY id DESC LIMIT %s""",
                        (instance_id, agent_id, limit),
                    )
                else:
                    cur.execute(
                        """SELECT id, instance_id, agent_id, conversation_id, user_input,
                                  output, usage_info, status, error_msg, created_at
                           FROM SCL_agent_conversations
                           WHERE instance_id = %s
                           ORDER BY id DESC LIMIT %s""",
                        (instance_id, limit),
                    )
                rows = cur.fetchall()
                results = []
                for row in rows:
                    try:
                        output = json.loads(row[5]) if isinstance(row[5], str) else (row[5] if row[5] else [])
                    except (json.JSONDecodeError, TypeError):
                        output = []
                    try:
                        usage_info = json.loads(row[6]) if isinstance(row[6], str) else (row[6] if row[6] else {})
                    except (json.JSONDecodeError, TypeError):
                        usage_info = {}
                    d = {
                        "id": row[0],
                        "instance_id": row[1],
                        "agent_id": row[2],
                        "conversation_id": row[3],
                        "user_input": row[4],
                        "output": output,
                        "usage_info": usage_info,
                        "status": row[7],
                        "error_msg": row[8] or "",
                        "created_at": str(row[9]) if row[9] else "",
                    }
                    results.append(d)
                results.reverse()
                return results

    @staticmethod
    def get_conversation_detail(conv_id: int) -> Optional[dict]:
        """Get a single conversation record by ID."""
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT id, instance_id, agent_id, conversation_id, user_input,
                              output, usage_info, status, error_msg, created_at
                       FROM SCL_agent_conversations WHERE id = %s""",
                    (conv_id,),
                )
                row = cur.fetchone()
                if not row:
                    return None
                return {
                    "id": row[0],
                    "instance_id": row[1],
                    "agent_id": row[2],
                    "conversation_id": row[3],
                    "user_input": row[4],
                    "output": json.loads(row[5]) if row[5] else [],
                    "usage_info": json.loads(row[6]) if row[6] else {},
                    "status": row[7],
                    "error_msg": row[8] or "",
                    "created_at": str(row[9]) if row[9] else "",
                }

    @staticmethod
    def delete_conversation(conv_id: int) -> bool:
        """Delete a single conversation record."""
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM SCL_agent_conversations WHERE id = %s", (conv_id,))
                return cur.rowcount > 0

    @staticmethod
    def batch_delete_conversations(ids: list) -> int:
        """Delete multiple conversation records. Returns count deleted."""
        if not ids:
            return 0
        with get_db() as conn:
            with conn.cursor() as cur:
                placeholders = ','.join(['%s'] * len(ids))
                cur.execute(
                    f"DELETE FROM SCL_agent_conversations WHERE id IN ({placeholders})",
                    ids,
                )
                return cur.rowcount

    @staticmethod
    def delete_conversations_by_conv_id(conversation_id: str) -> int:
        """Delete all records with the given conversation_id. Returns count."""
        if not conversation_id:
            return 0
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM SCL_agent_conversations WHERE conversation_id = %s",
                    (conversation_id,),
                )
                return cur.rowcount

    @staticmethod
    def insert_pending_conversation(instance_id: int, agent_id: int,
                                    conversation_id: str, user_input: str) -> int:
        """Insert a pending conversation record immediately (before agent responds).
        Returns the record ID."""
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO SCL_agent_conversations
                       (instance_id, agent_id, conversation_id, user_input, status)
                       VALUES (%s, %s, %s, %s, 'pending')""",
                    (instance_id, agent_id, conversation_id or "", user_input),
                )
                return cur.lastrowid

    @staticmethod
    def update_conversation_record(record_id: int, output: list,
                                   usage_info: dict, status: str = "completed",
                                   error_msg: str = ""):
        """Update a conversation record with agent response."""
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """UPDATE SCL_agent_conversations
                       SET output = %s, usage_info = %s, status = %s, error_msg = %s
                       WHERE id = %s""",
                    (json.dumps(output), json.dumps(usage_info),
                     status, error_msg or "", record_id),
                )

    # ─── Helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _mask_api_key(key: str) -> str:
        """Return a masked version of an API key for display."""
        if not key or len(key) <= 8:
            return "****" if key else ""
        return key[:4] + "****" + key[-4:]

    @staticmethod
    def _row_to_config(row) -> dict:
        raw_key = row[6]
        return {
            "id": row[0],
            "name": row[1],
            "soul_file": row[2],
            "memory_file": row[3],
            "tech_docs": row[4],
            "model_url": row[5],
            "model_api_key": AgentService._mask_api_key(raw_key or ""),
            "model_name": row[7],
            "model_provider": row[8] if len(row) > 8 else "",
            "proxy": row[9] if len(row) > 9 else "",
            "skills": json.loads(row[10]) if row[10] else [],
            "extra_env": json.loads(row[11]) if row[11] else {},
            "created_at": str(row[13]) if len(row) > 13 and row[13] else "",
            "updated_at": str(row[14]) if len(row) > 14 and row[14] else "",
        }

    @staticmethod
    def _row_to_instance(row) -> dict:
        """Deprecated: kept for backward compatibility."""
        return AgentService._row_to_workspace(row)

    @staticmethod
    def _row_to_workspace(row) -> dict:
        # Schema: id, name, description, node_id, status,
        #          created_at, updated_at, (agent_count from subquery), (master_id from subquery)
        d = {
            "id": row[0],
            "name": row[1] if len(row) > 1 and row[1] else "",
            "description": row[2] if len(row) > 2 and row[2] else "",
            "node_id": row[3] if len(row) > 3 and row[3] else "",
            "status": row[4] if len(row) > 4 else "pending",
            "created_at": str(row[5]) if len(row) > 5 and row[5] else "",
            "updated_at": str(row[6]) if len(row) > 6 and row[6] else "",
            "agent_count": row[7] if len(row) > 7 and row[7] is not None else 0,
            "master_agent_id": row[8] if len(row) > 8 and row[8] is not None else None,
        }
        return d

    @staticmethod
    def _row_to_agent(row) -> dict:
        # Schema: id, instance_id, config_id, name, description, role,
        #          container_id, host_port, api_key, agent_port,
        #          status, created_at, updated_at
        return {
            "id": row[0],
            "instance_id": row[1],
            "config_id": row[2],
            "name": row[3] if row[3] else "",
            "description": row[4] if len(row) > 4 and row[4] else "",
            "role": row[5] if len(row) > 5 and row[5] else "worker",
            "container_id": row[6] if len(row) > 6 and row[6] else "",
            "host_port": row[7] if len(row) > 7 and row[7] else 0,
            "api_key": row[8] if len(row) > 8 and row[8] else "",
            "agent_port": row[9] if len(row) > 9 and row[9] else 0,
            "status": row[10] if len(row) > 10 else "pending",
            "created_at": str(row[11]) if len(row) > 11 and row[11] else "",
            "updated_at": str(row[12]) if len(row) > 12 and row[12] else "",
        }

    @staticmethod
    def sync_workspace_status(instance_id: int):
        """Auto-update workspace status based on agent states.

        Rules:
        - If any agent is running → workspace is running
        - If all agents are stopped/error → workspace is stopped
        - If all agents are pending → workspace is pending
        """
        agents = AgentService.list_instance_agents(instance_id)
        if not agents:
            return

        statuses = [a["status"] for a in agents]
        if any(s == "running" for s in statuses):
            new_status = "running"
        elif all(s in ("stopped", "error") for s in statuses):
            new_status = "stopped"
        elif any(s == "error" for s in statuses):
            new_status = "error"
        else:
            new_status = "pending"

        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE SCL_workspaces SET status = %s, updated_at = NOW() WHERE id = %s AND status != %s",
                    (new_status, instance_id, new_status),
                )
