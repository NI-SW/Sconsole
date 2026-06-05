"""
Sconsole Node Agent
Connects to the Sconsole server and manages Docker-based agent deployments.
"""
import os
import sys
import json
import time
import socket
import shutil
import asyncio
import logging
import argparse
import subprocess
import signal
from typing import Optional, Dict

import websockets
import docker
from docker.errors import DockerException, ImageNotFound, ContainerError

# ─── Utilities ────────────────────────────────────────────────────────

def _copytree_skip_errors(src, dst):
    """shutil.copytree wrapper that skips files with permission errors."""
    os.makedirs(dst, exist_ok=True)
    for root, dirs, files in os.walk(src):
        rel = os.path.relpath(root, src)
        target_dir = os.path.join(dst, rel) if rel != '.' else dst
        os.makedirs(target_dir, exist_ok=True)
        for f in files:
            s = os.path.join(root, f)
            d = os.path.join(target_dir, f)
            try:
                shutil.copy2(s, d, follow_symlinks=False)
            except (PermissionError, OSError):
                logger = logging.getLogger("Node")
                logger.warning(f"  Skipping unreadable file: {s}")


# ─── Configuration ───────────────────────────────────────────────────

# Project root: Sconsole/ directory (parent of node/)
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Bypass proxy for local WebSocket connections
if not os.environ.get("no_proxy"):
    os.environ["no_proxy"] = "localhost,127.0.0.1,::1"

SERVER_URL = os.getenv("SCONSOLE_SERVER", "ws://localhost:8080")
NODE_ID = os.getenv("SCONSOLE_NODE_ID", socket.gethostname())
PROXY_URL = os.getenv("SCONSOLE_PROXY", "http://192.168.34.4:7890")
AGENT_IMAGE = os.getenv("SCONSOLE_AGENT_IMAGE", "sconsole-agent:latest")
SHARED_DIR = os.getenv("SCONSOLE_SHARED_DIR", os.path.join(os.path.expanduser("~"), ".sconsole", "shared"))
CONTAINER_VOLUME_DIR = os.getenv("SCONSOLE_VOLUME_DIR", os.path.join(_PROJECT_ROOT, "container_volume"))
HEARTBEAT_INTERVAL = int(os.getenv("SCONSOLE_HEARTBEAT", "30"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [Node] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)


# ─── Docker Manager ──────────────────────────────────────────────────

class DockerManager:
    """Manages Docker/Podman containers for agent deployment."""

    def __init__(self):
        # Use DOCKER_HOST if set, otherwise try podman user socket
        docker_host = os.environ.get("DOCKER_HOST", "")
        podman_sockets = [
            docker_host,
            "unix:///tmp/podman-user.sock",
            "unix:///run/user/1001/podman/podman.sock",
            "unix:///run/user/1000/podman/podman.sock",
            "unix:///run/podman/podman.sock",
        ]
        for url in podman_sockets:
            if not url:
                continue
            try:
                self.client = docker.DockerClient(base_url=url)
                self.client.ping()
                logger.info(f"Container runtime connected: {url}")
                break
            except Exception as e:
                logger.warning(f"Socket {url} failed: {e}")
                continue
        else:
            raise RuntimeError("No container runtime available")

        # Ensure shared directory exists
        os.makedirs(SHARED_DIR, exist_ok=True)

    def get_info(self) -> dict:
        """Get system info for node registration."""
        try:
            info = self.client.info()
            return {
                "hostname": socket.gethostname(),
                "ip_address": self._get_ip(),
                "docker_version": info.get("ServerVersion", ""),
                "cpu_count": info.get("NCPU", 0),
                "memory_mb": int(info.get("MemTotal", 0) / (1024 * 1024)),
            }
        except Exception as e:
            logger.warning(f"Failed to get docker info: {e}")
            return {
                "hostname": socket.gethostname(),
                "ip_address": self._get_ip(),
                "docker_version": "unknown",
                "cpu_count": os.cpu_count() or 0,
                "memory_mb": 0,
            }

    def _get_ip(self) -> str:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"

    @staticmethod
    def _find_free_port(start: int = 18000, end: int = 19000) -> int:
        """Find a free TCP port in the given range."""
        for port in range(start, end):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                try:
                    s.bind(("", port))
                    return port
                except OSError:
                    continue
        raise RuntimeError(f"No free port found in range {start}-{end}")

    def deploy_agent(self, instance_id: int, agent_id: int, config: dict,
                     aconfig_path: str = "") -> tuple:
        """Deploy an agent container. Returns (container_id, host_port) or (None, 0)."""
        agent_name = f"agent-{instance_id}-{agent_id}"
        agent_shared = os.path.join(SHARED_DIR, str(instance_id), str(agent_id))
        os.makedirs(agent_shared, exist_ok=True)

        # Ensure container volume directory exists
        os.makedirs(CONTAINER_VOLUME_DIR, exist_ok=True)

        # Generate API key for this agent
        import uuid
        agent_api_key = uuid.uuid4().hex
        config["_api_key"] = agent_api_key

        # Write config files into agent's shared directory
        self._write_agent_files(agent_shared, config)

        # Find a free host port
        host_port = self._find_free_port()

        # Prepare environment variables
        env_vars = {
            "AGENT_INSTANCE_ID": str(instance_id),
            "AGENT_API_KEY": agent_api_key,
            "AGENT_SOUL": config.get("soul_file", ""),
            "AGENT_MEMORY": config.get("memory_file", ""),
            "AGENT_TECH_DOCS": config.get("tech_docs", ""),
            "AGENT_MODEL_URL": config.get("model_url", ""),
            "AGENT_MODEL_API_KEY": config.get("model_api_key", ""),
            "AGENT_MODEL_NAME": config.get("model_name", ""),
            "AGENT_MODEL_PROVIDER": config.get("model_provider", ""),
            "AGENT_SKILLS": ",".join(config.get("skills", [])),
            "AGENT_PROXY": config.get("proxy", ""),
            "SCONSOLE_PROXY": PROXY_URL,
            # Prevent proxy from interfering with inter-agent calls
            "no_proxy": "localhost,127.0.0.1,::1,host.containers.internal,.internal",
            "NO_PROXY": "localhost,127.0.0.1,::1,host.containers.internal,.internal",
            "AGENT_VOLUME_DIR": "/agent/volume",
            "AGENT_HOST_PORT": str(host_port),
        }
        # Set provider-specific API key env var
        provider = config.get("model_provider", "")
        api_key = config.get("model_api_key", "")
        if provider and api_key:
            provider_key_map = {
                "deepseek": "DEEPSEEK_API_KEY",
                "anthropic": "ANTHROPIC_API_KEY",
                "xai": "XAI_API_KEY",
                "google": "GOOGLE_API_KEY",
                "kimi": "KIMI_API_KEY",
                "alibaba": "DASHSCOPE_API_KEY",
                "minimax": "MINIMAX_API_KEY",
                "glm": "GLM_API_KEY",
                "openai": "OPENAI_API_KEY",
                "openrouter": "OPENAI_API_KEY",
            }
            key_env = provider_key_map.get(provider, "OPENAI_API_KEY")
            env_vars[key_env] = api_key
            # Also set generic fallback keys
            env_vars["OPENAI_API_KEY"] = api_key
            env_vars["OPENAI_BASE_URL"] = config.get("model_url", "")
            env_vars["DEFAULT_MODEL"] = config.get("model_name", "")
            env_vars["DEFAULT_PROVIDER"] = provider if provider and provider != "custom" else "custom"
        elif api_key:
            env_vars["OPENAI_API_KEY"] = api_key
            env_vars["OPENAI_BASE_URL"] = config.get("model_url", "")
            env_vars["DEFAULT_MODEL"] = config.get("model_name", "")
            env_vars["DEFAULT_PROVIDER"] = "custom"
        env_vars.update(config.get("extra_env", {}))
        # Filter empty values
        env_vars = {k: v for k, v in env_vars.items() if v}

        # Prepare volumes (with SELinux relabel for RHEL systems)
        volumes = {
            agent_shared: {"bind": "/agent/shared", "mode": "rw,z"},
            CONTAINER_VOLUME_DIR: {"bind": "/agent/volume", "mode": "rw,z"},
        }

        # Mount config files if provided
        if aconfig_path and os.path.isdir(aconfig_path):
            volumes[aconfig_path] = {"bind": "/agent/config", "mode": "ro,z"}
            logger.info(f"  Mounting config files: {aconfig_path} → /agent/config")

        # Port mapping: container 8642 → host random port
        ports = {"8642/tcp": host_port}

        # Remove existing container if any
        self._remove_container(agent_name)

        try:
            logger.info(f"Deploying agent {instance_id} as container '{agent_name}'")
            logger.info(f"  Image: {AGENT_IMAGE}")
            logger.info(f"  Shared dir: {agent_shared}")
            logger.info(f"  Volume dir: {CONTAINER_VOLUME_DIR} → /agent/volume")
            logger.info(f"  Port: {host_port} → container:8642")

            # Pull image if not present
            try:
                self.client.images.get(AGENT_IMAGE)
            except ImageNotFound:
                logger.info(f"Pulling image: {AGENT_IMAGE}")
                self.client.images.pull(AGENT_IMAGE)

            container = self.client.containers.run(
                image=AGENT_IMAGE,
                name=agent_name,
                environment=env_vars,
                volumes=volumes,
                ports=ports,
                detach=True,
                restart_policy={"Name": "unless-stopped"},
                network_mode="bridge",
            )

            logger.info(f"Agent container started: {container.id[:12]}")

            # Fix intercom skill permissions (copied as root by the image entrypoint)
            try:
                container.exec_run(
                    "chown -R hermes:hermes /opt/data/skills/sconsole-intercom 2>/dev/null || true",
                    user="root",
                )
            except Exception:
                pass

            # Fix /agent/volume permissions for intercom mailbox
            try:
                container.exec_run(
                    "chown -R hermes:hermes /agent/volume 2>/dev/null || true",
                    user="root",
                )
            except Exception:
                pass

            # Ensure mailbox directory exists with correct permissions
            try:
                container.exec_run(
                    "mkdir -p /agent/volume/mailbox && chmod 777 /agent/volume/mailbox 2>/dev/null || true",
                    user="root",
                )
            except Exception:
                pass

            # Fix registry directory permissions
            try:
                container.exec_run(
                    "chown -R hermes:hermes /agent/volume/registry 2>/dev/null || true",
                    user="root",
                )
            except Exception:
                pass

            return container.id, host_port

        except Exception as e:
            logger.error(f"Failed to deploy agent {instance_id}: {e}")
            return None, 0

    def stop_agent(self, instance_id: int, agent_id: int):
        """Stop and remove an agent container."""
        agent_name = f"agent-{instance_id}-{agent_id}"
        self._remove_container(agent_name)
        # Clean up shared directory
        agent_shared = os.path.join(SHARED_DIR, str(instance_id), str(agent_id))
        if os.path.isdir(agent_shared):
            shutil.rmtree(agent_shared)
            logger.info(f"Cleaned shared dir: {agent_shared}")

    def restart_agent(self, instance_id: int, agent_id: int):
        """Restart an agent container to pick up updated config files."""
        agent_name = f"agent-{instance_id}-{agent_id}"
        try:
            container = self.client.containers.get(agent_name)
            logger.info(f"Restarting container: {agent_name}")
            container.restart(timeout=10)
            logger.info(f"Container restarted: {agent_name}")
        except Exception as e:
            logger.warning(f"Failed to restart container {agent_name}: {e}")
            # Retry after a short delay (container may be mid-startup)
            import time
            time.sleep(3)
            try:
                container = self.client.containers.get(agent_name)
                container.restart(timeout=15)
                logger.info(f"Container restarted on retry: {agent_name}")
            except Exception as e2:
                logger.warning(f"Retry restart also failed for {agent_name}: {e2}")

    def _remove_container(self, name: str):
        """Remove container if it exists."""
        try:
            container = self.client.containers.get(name)
            logger.info(f"Stopping container: {name}")
            container.stop(timeout=10)
            container.remove(force=True)
            logger.info(f"Container removed: {name}")
        except Exception:
            pass  # Container not found or already removed

    def clean_intercom_artifacts(self, workspace_id: int, agent_ids: list):
        """Remove intercom registry and mailbox for a deleted workspace."""
        import subprocess
        cleaned = []

        # Registry file
        reg_file = os.path.join(CONTAINER_VOLUME_DIR, "registry", f"{workspace_id}.json")
        if os.path.exists(reg_file):
            try:
                os.remove(reg_file)
                cleaned.append(f"registry/{workspace_id}.json")
            except OSError:
                pass

        # Mailbox directories: workspace_id + each agent_id
        ids_to_clean = {workspace_id}
        ids_to_clean.update(agent_ids or [])

        for mid in ids_to_clean:
            mailbox = os.path.join(CONTAINER_VOLUME_DIR, "mailbox", str(mid))
            if os.path.isdir(mailbox):
                try:
                    shutil.rmtree(mailbox)
                    cleaned.append(f"mailbox/{mid}")
                except PermissionError:
                    # Fallback: use podman unshare for container-owned files
                    try:
                        subprocess.run(
                            ["podman", "unshare", "rm", "-rf", mailbox],
                            capture_output=True, timeout=10,
                        )
                        if not os.path.isdir(mailbox):
                            cleaned.append(f"mailbox/{mid}")
                    except Exception:
                        logger.warning(f"Failed to clean mailbox {mailbox}")

        if cleaned:
            logger.info(f"[Intercom] Cleaned for ws {workspace_id}: {', '.join(cleaned)}")

    def _write_agent_files(self, shared_dir: str, config: dict):
        """Write agent configuration files to shared directory."""
        # Write SOUL file
        soul = config.get("soul_file", "")
        # Append agent config prompt (workdir + config path info)
        agent_cfg_path = os.path.join(
            os.path.dirname(__file__), "..", "prompts", "agentConfig.md",
        )
        if os.path.exists(agent_cfg_path):
            with open(agent_cfg_path, "r", encoding="utf-8") as f:
                agent_cfg = f.read()
            if agent_cfg:
                soul = (soul or "") + "\n\n" + agent_cfg

        if soul:
            logger.info(f"Writing SOUL.md ({len(soul)} bytes) to {shared_dir}")
            with open(os.path.join(shared_dir, "SOUL.md"), "w", encoding="utf-8") as f:
                f.write(soul)

        # Write MEMORY file (or remove if empty for master agents)
        memory = config.get("memory_file", "")
        memory_path = os.path.join(shared_dir, "MEMORY.md")
        if memory:
            with open(memory_path, "w", encoding="utf-8") as f:
                f.write(memory)
        elif os.path.exists(memory_path):
            os.remove(memory_path)
            logger.info(f"Removed stale MEMORY.md from {shared_dir}")

        # Write tech docs (or remove if empty)
        docs = config.get("tech_docs", "")
        docs_path = os.path.join(shared_dir, "TECH_DOCS.md")
        if docs:
            with open(docs_path, "w", encoding="utf-8") as f:
                f.write(docs)
        elif os.path.exists(docs_path):
            os.remove(docs_path)

        # Fill default model_url if empty but provider is set
        provider = config.get("model_provider", "")
        if provider and not config.get("model_url", ""):
            default_urls = {
                "openai": "https://api.openai.com/v1",
                "openrouter": "https://openrouter.ai/api/v1",
                "deepseek": "https://api.deepseek.com/v1",
                "anthropic": "https://api.anthropic.com/v1",
                "xai": "https://api.x.ai/v1",
                "google": "https://generativelanguage.googleapis.com/v1beta",
                "kimi": "https://api.kimi.com/coding",
                "alibaba": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                "minimax": "https://api.minimax.chat/v1",
                "glm": "https://open.bigmodel.cn/api/paas/v4",
            }
            if provider in default_urls:
                config["model_url"] = default_urls[provider]
                logger.info(f"  Auto-filled model_url for provider '{provider}': {config['model_url']}")

        # Write full config as JSON
        # ── Copy local skill directories into shared dir ──
        # Project-level skills directory (contains built-in skills like retrieval-expert)
        _project_skills_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "skills")

        skills = config.get("skills", [])
        if skills:
            skills_dir = os.path.join(shared_dir, "skills")
            os.makedirs(skills_dir, exist_ok=True)
            remapped = []
            for skill_path in skills:
                if skill_path.startswith("http://") or skill_path.startswith("https://"):
                    # Remote URL — keep as is (entrypoint.sh will git clone)
                    remapped.append(skill_path)
                    continue
                # If skill_path is a bare name (not a path), resolve from project skills dir
                if not os.path.sep in skill_path and not skill_path.startswith("."):
                    candidate = os.path.join(_project_skills_dir, skill_path)
                    if os.path.isdir(candidate):
                        skill_path = candidate
                        logger.info(f"  Resolved skill name '{skills[len(remapped)] if len(remapped) < len(skills) else skill_path}' to {skill_path}")
                # Local path — copy into shared dir
                src = os.path.abspath(skill_path)
                if not os.path.isdir(src):
                    logger.warning(f"  Skill path not found, skipping: {src}")
                    continue
                skill_name = os.path.basename(src.rstrip("/"))
                dst = os.path.join(skills_dir, skill_name)
                if os.path.exists(dst):
                    shutil.rmtree(dst, ignore_errors=True)
                try:
                    _copytree_skip_errors(src, dst)
                except Exception as e:
                    logger.error(f"  Skill copy failed for {src}: {e}")
                    continue
                remapped.append(f"/agent/shared/skills/{skill_name}")
                logger.info(f"  Skill copied: {src} -> /agent/shared/skills/{skill_name}")
            config["skills"] = remapped

        with open(os.path.join(shared_dir, "agent_config.json"), "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)

        # Write agents.json if provided (for master agent runtime discovery)
        agents_json = config.get("_agents_json", "")
        if agents_json:
            with open(os.path.join(shared_dir, "agents.json"), "w", encoding="utf-8") as f:
                f.write(agents_json)

        logger.info(f"Agent files written to {shared_dir}")

    def get_container_logs(self, instance_id: int, tail: int = 100) -> str:
        """Get recent logs from an agent container."""
        agent_name = f"agent-{instance_id}"
        try:
            container = self.client.containers.get(agent_name)
            return container.logs(tail=tail).decode("utf-8", errors="replace")
        except Exception:
            return ""


# ─── Node WebSocket Client ───────────────────────────────────────────

class NodeClient:
    """WebSocket client that connects to Sconsole server."""

    def __init__(self, server_url: str, node_id: str):
        self.server_url = server_url
        self.node_id = node_id
        self.docker_mgr: Optional[DockerManager] = None
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self.running = False

    async def connect(self):
        """Connect to the server and start processing messages."""
        # Initialize Docker manager
        try:
            self.docker_mgr = DockerManager()
        except RuntimeError as e:
            logger.error(f"Cannot start node: {e}")
            return

        self.running = True

        while self.running:
            try:
                ws_url = f"{self.server_url}/ws/node/{self.node_id}"
                logger.info(f"Connecting to server: {ws_url}")

                async with websockets.connect(ws_url, ping_interval=30, ping_timeout=60) as ws:
                    self.ws = ws
                    logger.info("Connected to server.")

                    # Send registration info
                    info = self.docker_mgr.get_info()
                    await ws.send(json.dumps({
                        "type": "register",
                        "hostname": info["hostname"],
                        "ip_address": info["ip_address"],
                        "docker_version": info["docker_version"],
                        "cpu_count": info["cpu_count"],
                        "memory_mb": info["memory_mb"],
                    }))
                    logger.info("Registration sent.")

                    # Start heartbeat task
                    heartbeat_task = asyncio.create_task(self._heartbeat_loop())

                    # Process messages
                    try:
                        await self._message_loop(ws)
                    finally:
                        heartbeat_task.cancel()
                        try:
                            await heartbeat_task
                        except asyncio.CancelledError:
                            pass

            except (websockets.ConnectionClosed, ConnectionRefusedError,
                    OSError) as e:
                logger.warning(f"Connection lost: {e}. Reconnecting in 5s...")
                self.ws = None
                await asyncio.sleep(5)
            except Exception as e:
                logger.error(f"Unexpected error: {e}. Reconnecting in 10s...")
                self.ws = None
                await asyncio.sleep(10)

    async def _heartbeat_loop(self):
        """Send periodic heartbeats."""
        while self.running and self.ws:
            try:
                await self.ws.send(json.dumps({"type": "heartbeat"}))
            except Exception:
                break
            await asyncio.sleep(HEARTBEAT_INTERVAL)

    async def _message_loop(self, ws):
        """Process incoming messages from server."""
        async for raw in ws:
            try:
                msg = json.loads(raw)
                msg_type = msg.get("type", "")
                logger.info(f"Received: {msg_type}")

                if msg_type == "deploy_agent":
                    await self._handle_deploy(msg)
                elif msg_type == "stop_agent":
                    await self._handle_stop(msg)
                elif msg_type == "restart_agent":
                    await self._handle_restart(msg)
                elif msg_type == "agent_input":
                    await self._handle_agent_input(msg)
                elif msg_type == "clean_intercom":
                    await self._handle_clean_intercom(msg)
                else:
                    logger.warning(f"Unknown message type: {msg_type}")

            except json.JSONDecodeError:
                logger.error(f"Invalid JSON received: {raw[:200]}")
            except Exception as e:
                logger.error(f"Error handling message: {e}")

    async def _handle_deploy(self, msg: dict):
        """Handle agent deployment request."""
        instance_id = msg.get("instance_id") or msg.get("workspace_id")
        agent_id = msg.get("agent_id")
        config = msg.get("config", {})
        aconfig_path = msg.get("aconfig_path", "")
        soul_len = len(config.get("soul_file", ""))
        logger.info(f"Deploy agent {instance_id}/{agent_id}, soul_file={soul_len} bytes, aconfig={aconfig_path}")

        # Report status: deploying
        await self._send_status(instance_id, "deploying", agent_id)

        # Deploy the container (run in thread to avoid blocking event loop)
        container_id, host_port = await asyncio.get_event_loop().run_in_executor(
            None, self.docker_mgr.deploy_agent, instance_id, agent_id, config, aconfig_path
        )
        api_key = config.get("_api_key", "")

        if container_id:
            await self._send_status(instance_id, "running", agent_id, container_id, host_port, api_key)
            logger.info(f"Agent {instance_id}/{agent_id} deployed: {container_id[:12]} port={host_port}")
        else:
            await self._send_status(instance_id, "error", agent_id)
            logger.error(f"Agent {instance_id}/{agent_id} deployment failed")

    async def _handle_stop(self, msg: dict):
        """Handle agent stop request."""
        instance_id = msg.get("instance_id") or msg.get("workspace_id")
        agent_id = msg.get("agent_id")
        self.docker_mgr.stop_agent(instance_id, agent_id)
        await self._send_status(instance_id, "stopped", agent_id)
        logger.info(f"Agent {instance_id}/{agent_id} stopped")

    async def _handle_restart(self, msg: dict):
        """Handle agent restart request (for picking up updated config files)."""
        instance_id = msg.get("instance_id") or msg.get("workspace_id")
        agent_id = msg.get("agent_id")
        self.docker_mgr.restart_agent(instance_id, agent_id)
        logger.info(f"Agent {instance_id}/{agent_id} restarted")

    async def _handle_agent_input(self, msg: dict):
        """Forward input to agent container (via stdin or shared file)."""
        instance_id = msg.get("instance_id") or msg.get("workspace_id")
        content = msg.get("content", "")

        # Write input to shared file for agent to pick up
        shared_dir = os.path.join(SHARED_DIR, str(instance_id))
        input_file = os.path.join(shared_dir, "input.json")
        try:
            with open(input_file, "w", encoding="utf-8") as f:
                json.dump({"content": content, "timestamp": time.time()}, f)
            logger.info(f"Input written for agent {instance_id}")
        except Exception as e:
            logger.error(f"Failed to write input for agent {instance_id}: {e}")

    async def _handle_clean_intercom(self, msg: dict):
        """Handle cleanup of intercom artifacts after workspace deletion."""
        workspace_id = msg.get("workspace_id") or msg.get("instance_id")
        agent_ids = msg.get("agent_ids", [])
        if self.docker_mgr:
            self.docker_mgr.clean_intercom_artifacts(workspace_id, agent_ids)

    async def _send_status(self, instance_id: int, status: str, agent_id: int = 0,
                          container_id: str = "", host_port: int = 0, api_key: str = ""):
        """Send agent status update to server."""
        if self.ws:
            try:
                await self.ws.send(json.dumps({
                    "type": "agent_status",
                    "instance_id": instance_id,
                    "agent_id": agent_id,
                    "status": status,
                    "container_id": container_id,
                    "host_port": host_port,
                    "api_key": api_key,
                }))
            except Exception as e:
                logger.error(f"Failed to send status: {e}")


# ─── Main ────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Sconsole Node Agent")
    parser.add_argument(
        "--server", default=SERVER_URL,
        help=f"Server WebSocket URL (default: {SERVER_URL})"
    )
    parser.add_argument(
        "--node-id", default=NODE_ID,
        help=f"Node identifier (default: {NODE_ID})"
    )
    args = parser.parse_args()

    logger.info(f"Starting Sconsole Node '{args.node_id}'")
    logger.info(f"Server: {args.server}")

    client = NodeClient(args.server, args.node_id)

    def shutdown(sig, frame):
        logger.info("Shutting down...")
        client.running = False
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    asyncio.run(client.connect())


if __name__ == "__main__":
    main()
