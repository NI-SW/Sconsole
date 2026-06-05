-- Sconsole Database Schema
-- OceanBase MySQL compatible
-- Prefix: SCL_ (per project convention)

-- Create database (run manually if needed):
-- CREATE DATABASE IF NOT EXISTS SCL_sconsole CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- ─── Agent Configurations ───────────────────────────────────────────

CREATE TABLE IF NOT EXISTS SCL_agent_configs (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    name            VARCHAR(255) NOT NULL DEFAULT '',
    soul_file       TEXT COMMENT 'SOUL/personality configuration content',
    memory_file     TEXT COMMENT 'MEMORY context content',
    tech_docs       TEXT COMMENT 'Technical documentation content',
    model_url       VARCHAR(512) NOT NULL DEFAULT '' COMMENT 'LLM API endpoint URL',
    model_api_key   VARCHAR(512) NOT NULL DEFAULT '' COMMENT 'API key for model access',
    model_name      VARCHAR(255) NOT NULL DEFAULT '' COMMENT 'Model identifier (e.g. gpt-4)',
    model_provider  VARCHAR(64)  NOT NULL DEFAULT '' COMMENT 'API provider: openai, openrouter, deepseek, anthropic, xai, etc.',
    proxy           VARCHAR(512) NOT NULL DEFAULT '' COMMENT 'HTTP(S) proxy for skill downloads (e.g. http://host:port)',
    skills          JSON COMMENT 'JSON array of skill paths/URLs',
    extra_env       JSON COMMENT 'Additional environment variables as JSON object',
    attached_files  JSON COMMENT 'JSON array of uploaded file names for this config',
    created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Agent configuration templates';


CREATE TABLE IF NOT EXISTS SCL_instance_agents (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    instance_id     INT NOT NULL COMMENT 'FK to SCL_workspaces',
    config_id       INT NOT NULL COMMENT 'FK to SCL_agent_configs',
    name            VARCHAR(255) NOT NULL DEFAULT '' COMMENT 'Agent display name',
    role            VARCHAR(32) NOT NULL DEFAULT 'worker' COMMENT 'master, worker',
    container_id    VARCHAR(255) NOT NULL DEFAULT '' COMMENT 'Docker container ID',
    host_port       INT NOT NULL DEFAULT 0 COMMENT 'Host port mapped to container API port',
    api_key         VARCHAR(128) NOT NULL DEFAULT '' COMMENT 'Agent API key for hermes gateway',
    agent_port      INT NOT NULL DEFAULT 0 COMMENT 'Port this agent exposes for API access',
    status          ENUM('pending','deploying','running','stopped','error') NOT NULL DEFAULT 'pending',
    created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_instance_id (instance_id),
    INDEX idx_config_id (config_id),
    INDEX idx_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Agents within a workspace instance';


-- ─── Agent Messages ─────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS SCL_agent_messages (
    id                  INT AUTO_INCREMENT PRIMARY KEY,
    agent_instance_id   INT NOT NULL COMMENT 'FK to SCL_instance_agents (legacy column name, see SCL_agent_messages_v3)',
    direction           ENUM('user','agent','system') NOT NULL DEFAULT 'user',
    content             LONGTEXT COMMENT 'Message content',
    message_type        VARCHAR(50) NOT NULL DEFAULT 'text' COMMENT 'text, code, tool_call, error',
    created_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_instance (agent_instance_id),
    INDEX idx_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Agent conversation history';


-- ─── Nodes ──────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS SCL_nodes (
    node_id         VARCHAR(255) PRIMARY KEY,
    hostname        VARCHAR(255) NOT NULL DEFAULT '',
    ip_address      VARCHAR(45) NOT NULL DEFAULT '',
    status          ENUM('online','offline','busy') NOT NULL DEFAULT 'offline',
    docker_version  VARCHAR(100) NOT NULL DEFAULT '',
    cpu_count       INT NOT NULL DEFAULT 0,
    memory_mb       INT NOT NULL DEFAULT 0,
    connected_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_heartbeat  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Compute nodes connected to the system';


-- ─── Agent Conversations (hermes monitor / communicate) ──────────────

CREATE TABLE IF NOT EXISTS SCL_agent_conversations (
    id                INT AUTO_INCREMENT PRIMARY KEY,
    instance_id       INT NOT NULL COMMENT 'FK to SCL_workspaces',
    agent_id          INT NOT NULL DEFAULT 0 COMMENT 'FK to SCL_instance_agents',
    conversation_id   VARCHAR(128) NOT NULL DEFAULT '' COMMENT 'Hermes conversation ID',
    user_input        TEXT COMMENT 'User input / query',
    output            JSON COMMENT 'Full hermes output array (function_calls, messages, etc.)',
    usage_info        JSON COMMENT 'Token usage info (input_tokens, output_tokens, total_tokens)',
    status            VARCHAR(32) NOT NULL DEFAULT 'completed' COMMENT 'completed, in_progress, error',
    error_msg         TEXT COMMENT 'Error message if any',
    created_at        DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_instance (instance_id),
    INDEX idx_agent (agent_id),
    INDEX idx_conversation (conversation_id),
    INDEX idx_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Hermes agent conversation tracking for monitor view';


-- ─── Skills ─────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS SCL_skills (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    name        VARCHAR(255) NOT NULL,
    version     VARCHAR(50) NOT NULL DEFAULT '1.0.0',
    source      VARCHAR(1024) NOT NULL DEFAULT '' COMMENT 'URL or local path',
    description TEXT,
    installed_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE INDEX idx_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Installed agent skills';
