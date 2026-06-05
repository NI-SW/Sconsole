-- ═══════════════════════════════════════════════════════════════════════
-- Sconsole v3 重构：Workspaces + 消息表修正 + 实例 Agent 增强列
-- ═══════════════════════════════════════════════════════════════════════
-- 
-- 变更内容：
--   1. SCL_workspaces（v3 中替代原 SCL_agent_instances）
--   2. SCL_agent_messages_v3（修正列名 agent_instance_id → instance_agent_id）
--   3. SCL_instance_agents 增加 description / role / agent_port 列
--   4. SCL_agent_configs 增加 attached_files 列
-- ═══════════════════════════════════════════════════════════════════════

-- ═══ SCL_workspaces ════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS SCL_workspaces (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    name            VARCHAR(255) NOT NULL DEFAULT '' COMMENT '工作空间显示名称',
    description     TEXT COMMENT '工作空间描述',
    node_id         VARCHAR(255) NOT NULL DEFAULT '' COMMENT '分配到的节点 ID',
    status          ENUM('pending','deploying','running','stopped','error') NOT NULL DEFAULT 'pending',
    created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_node (node_id),
    INDEX idx_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Agent 工作空间';

-- ═══ SCL_agent_messages_v3（列名修正后的新消息表）═══════════════════════
CREATE TABLE IF NOT EXISTS SCL_agent_messages_v3 (
    id                  INT AUTO_INCREMENT PRIMARY KEY,
    instance_agent_id   INT NOT NULL COMMENT 'FK to SCL_instance_agents.id',
    direction           ENUM('user','agent','system') NOT NULL DEFAULT 'user',
    content             LONGTEXT COMMENT '消息内容',
    message_type        VARCHAR(50) NOT NULL DEFAULT 'text' COMMENT 'text, code, tool_call, error',
    created_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_instance_agent (instance_agent_id),
    INDEX idx_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Agent 消息历史（v3 修正了列名）';

-- ═══ 向 SCL_instance_agents 新增缺失的列 ══════════════════════════════

-- 新增 description 列以存储 Agent 描述
SET @col_exists = (SELECT COUNT(*) FROM information_schema.COLUMNS 
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'SCL_instance_agents' AND COLUMN_NAME = 'description');
SET @sql = IF(@col_exists = 0,
    'ALTER TABLE SCL_instance_agents ADD COLUMN description TEXT COMMENT ''Agent 描述/用途'' AFTER name',
    'SELECT ''description 列已存在''');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- 新增 role 列以区分 master/worker Agent
SET @col_exists = (SELECT COUNT(*) FROM information_schema.COLUMNS 
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'SCL_instance_agents' AND COLUMN_NAME = 'role');
SET @sql = IF(@col_exists = 0,
    'ALTER TABLE SCL_instance_agents ADD COLUMN role VARCHAR(32) NOT NULL DEFAULT ''worker'' COMMENT ''Agent 角色：master/worker'' AFTER description',
    'SELECT ''role 列已存在''');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- 新增 agent_port 列（容器内 Hermes API 端口，通常为 8642）
SET @col_exists = (SELECT COUNT(*) FROM information_schema.COLUMNS 
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'SCL_instance_agents' AND COLUMN_NAME = 'agent_port');
SET @sql = IF(@col_exists = 0,
    'ALTER TABLE SCL_instance_agents ADD COLUMN agent_port INT NOT NULL DEFAULT 0 COMMENT ''容器内 Hermes API 端口'' AFTER api_key',
    'SELECT ''agent_port 列已存在''');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- ═══ 向 SCL_agent_configs 新增 attached_files 列 ══════════════════════
SET @col_exists = (SELECT COUNT(*) FROM information_schema.COLUMNS 
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'SCL_agent_configs' AND COLUMN_NAME = 'attached_files');
SET @sql = IF(@col_exists = 0,
    'ALTER TABLE SCL_agent_configs ADD COLUMN attached_files JSON COMMENT ''已上传的附件文件列表'' AFTER extra_env',
    'SELECT ''attached_files 列已存在''');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- ═══ 兼容性说明 ══════════════════════════════════════════════════════
-- 
-- 1. 应用程序代码使用 SCL_workspaces 替代 SCL_agent_instances
-- 2. 应用程序代码使用 SCL_agent_messages_v3 替代 SCL_agent_messages
-- 3. API 端点将 "/api/instances" 重命名为 "/api/workspaces"
--    旧端点保留以保持向后兼容
-- 4. 前端变量名从 "instances" 更新为 "workspaces"
-- ═══════════════════════════════════════════════════════════════════════
