"""
Sconsole Server - Database Layer
OceanBase MySQL connection management.
"""
import pymysql
from contextlib import contextmanager
from typing import Optional

from server.config import DB_CONFIG


def get_connection():
    """Create a new database connection."""
    return pymysql.connect(
        host=DB_CONFIG["host"],
        port=DB_CONFIG["port"],
        user=DB_CONFIG["user"],
        password=DB_CONFIG["password"],
        database=DB_CONFIG["database"],
        charset="utf8mb4",
        autocommit=False,
    )


@contextmanager
def get_db():
    """Context manager for database connections."""
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """Initialize database schema from sql_files/ and apply migrations."""
    import os
    from pathlib import Path

    sql_dir = Path(__file__).resolve().parent.parent.parent / "sql_files"
    if not sql_dir.exists():
        print(f"[DB] sql_files/ directory not found at {sql_dir}")
        return

    conn = get_connection()
    try:
        for sql_file in sorted(sql_dir.glob("*.sql")):
            print(f"[DB] Executing {sql_file.name}...")
            with open(sql_file, "r", encoding="utf-8") as f:
                sql = f.read()
            # Split by semicolons for multiple statements
            statements = [s.strip() for s in sql.split(";") if s.strip()]
            with conn.cursor() as cur:
                for stmt in statements:
                    if stmt and not stmt.startswith("--"):
                        cur.execute(stmt)
        conn.commit()

        # ─── Migrations: add columns/indexes if missing ─────────────────
        _run_migrations(conn)

        print("[DB] Schema initialized successfully.")
    except Exception as e:
        conn.rollback()
        print(f"[DB] Schema initialization failed: {e}")
        raise
    finally:
        conn.close()


def _column_exists(conn, table: str, column: str) -> bool:
    """Check if a column exists in a table (OceanBase compatible)."""
    with conn.cursor() as cur:
        cur.execute(
            """SELECT COUNT(*) FROM information_schema.COLUMNS
               WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s AND COLUMN_NAME = %s""",
            (table, column),
        )
        return cur.fetchone()[0] > 0


def _index_exists(conn, table: str, index_name: str) -> bool:
    """Check if an index exists on a table (OceanBase compatible)."""
    with conn.cursor() as cur:
        cur.execute(
            """SELECT COUNT(*) FROM information_schema.STATISTICS
               WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s AND INDEX_NAME = %s""",
            (table, index_name),
        )
        return cur.fetchone()[0] > 0


def _add_column_if_missing(conn, table: str, column: str, after: str, definition: str):
    """Add a column if it doesn't exist (OceanBase compatible)."""
    if not _column_exists(conn, table, column):
        with conn.cursor() as cur:
            cur.execute(f"ALTER TABLE {table} ADD COLUMN {definition} AFTER {after}")
        print(f"[DB] Added column {table}.{column}")


def _add_index_if_missing(conn, table: str, index_name: str, definition: str):
    """Add an index if it doesn't exist (OceanBase compatible)."""
    if not _index_exists(conn, table, index_name):
        with conn.cursor() as cur:
            cur.execute(f"ALTER TABLE {table} ADD INDEX {index_name} ({definition})")
        print(f"[DB] Added index {index_name} on {table}")


def _run_migrations(conn):
    """Apply incremental migrations for existing databases."""
    # ═══ SCL_workspaces: ensure indexes exist ════════════════════════════
    _add_index_if_missing(conn, "SCL_workspaces", "idx_node", "node_id")
    _add_index_if_missing(conn, "SCL_workspaces", "idx_status", "status")

    # ═══ SCL_instance_agents: ensure all v3 columns exist ═══════════════
    _add_column_if_missing(conn, "SCL_instance_agents", "description",
        "name", "description TEXT COMMENT 'Agent 角色描述，供 Master 调度使用'")
    _add_column_if_missing(conn, "SCL_instance_agents", "role",
        "description", "role VARCHAR(32) NOT NULL DEFAULT 'worker' COMMENT 'master, worker'")
    _add_column_if_missing(conn, "SCL_instance_agents", "container_id",
        "role", "container_id VARCHAR(255) NOT NULL DEFAULT '' COMMENT 'Docker container ID'")
    _add_column_if_missing(conn, "SCL_instance_agents", "host_port",
        "container_id", "host_port INT NOT NULL DEFAULT 0 COMMENT 'Host port mapped to container API port'")
    _add_column_if_missing(conn, "SCL_instance_agents", "api_key",
        "host_port", "api_key VARCHAR(128) NOT NULL DEFAULT '' COMMENT 'Agent API key for hermes gateway'")
    _add_column_if_missing(conn, "SCL_instance_agents", "agent_port",
        "api_key", "agent_port INT NOT NULL DEFAULT 0 COMMENT 'Port this agent exposes for API access'")

    # ═══ SCL_agent_configs: ensure attached_files column ════════════════
    _add_column_if_missing(conn, "SCL_agent_configs", "attached_files",
        "extra_env", "attached_files JSON COMMENT 'JSON array of uploaded file names for this config'")

    # ═══ SCL_agent_messages_v3: ensure table exists ═════════════════════
    with conn.cursor() as cur:
        cur.execute(
            """SELECT COUNT(*) FROM information_schema.TABLES
               WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'SCL_agent_messages_v3'"""
        )
        if cur.fetchone()[0] == 0:
            cur.execute("""CREATE TABLE SCL_agent_messages_v3 (
                id                  INT AUTO_INCREMENT PRIMARY KEY,
                instance_agent_id   INT NOT NULL COMMENT 'FK to SCL_instance_agents',
                direction           ENUM('user','agent','system') NOT NULL DEFAULT 'user',
                content             LONGTEXT COMMENT '消息内容',
                message_type        VARCHAR(50) NOT NULL DEFAULT 'text' COMMENT 'text, code, tool_call, error',
                created_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_instance_agent (instance_agent_id),
                INDEX idx_created (created_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            COMMENT='Agent 对话历史'""")
            print("[DB] Created table SCL_agent_messages_v3")

    # ═══ Normalize SCL_nodes collation ══════════════════════════════════
    with conn.cursor() as cur:
        try:
            cur.execute(
                "ALTER TABLE SCL_nodes CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
        except Exception as e:
            print(f"[DB] SCL_nodes collation migration warning: {e}")

    conn.commit()
    print("[DB] Migrations applied.")
