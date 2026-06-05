#!/bin/bash
# Sconsole Agent Entrypoint
# Loads configuration from shared volume, configures hermes-agent,
# and launches the hermes gateway API server.
set -e

echo "=== Sconsole Agent Entrypoint ==="
echo "Instance ID: ${AGENT_INSTANCE_ID}"
echo "Shared Dir:  ${AGENT_SHARED_DIR:-/agent/shared}"
echo "Volume Dir:  ${AGENT_VOLUME_DIR:-/agent/volume}"
echo "Skills Dir:  ${AGENT_SKILLS_DIR:-/agent/skills}"

SHARED_DIR="${AGENT_SHARED_DIR:-/agent/shared}"
SKILLS_DIR="${AGENT_SKILLS_DIR:-/agent/skills}"
HERMES_DIR="/opt/data"
HERMES_ENV="${HERMES_DIR}/.env"

mkdir -p "${HERMES_DIR}" "${HERMES_DIR}/memories" "${HERMES_DIR}/skills" "${HERMES_DIR}/logs"

# Ensure hermes uses /opt/data as its home directory
export HERMES_HOME="${HERMES_DIR}"

# ─── Step 0: Copy built-in skills to hermes directory ──────────────────

echo "[Skills] Installing built-in skills..."
if [ -d "${AGENT_SKILLS_DIR:-/agent/skills}" ]; then
    for skill_dir in "${AGENT_SKILLS_DIR:-/agent/skills}"/*/; do
        skill_name=$(basename "$skill_dir")
        if [ -f "${skill_dir}SKILL.md" ]; then
            dst="${HERMES_DIR}/skills/${skill_name}"
            mkdir -p "$dst"
            cp -r "${skill_dir}"* "$dst/" 2>/dev/null
            echo "  ✓ ${skill_name}"
        fi
    done
fi

# ─── Step 1: Load config from shared volume ──────────────────────────

CONFIG_FILE="${SHARED_DIR}/agent_config.json"
MODEL_URL=""
MODEL_API_KEY=""
MODEL_NAME=""
MODEL_PROVIDER=""
PROXY_URL=""

if [ -f "$CONFIG_FILE" ]; then
    echo "[Config] Loading from ${CONFIG_FILE}..."
    MODEL_URL=$(python3 -c "import json; c=json.load(open('${CONFIG_FILE}')); print(c.get('model_url',''))" 2>/dev/null || echo "")
    MODEL_API_KEY=$(python3 -c "import json; c=json.load(open('${CONFIG_FILE}')); print(c.get('model_api_key',''))" 2>/dev/null || echo "")
    MODEL_NAME=$(python3 -c "import json; c=json.load(open('${CONFIG_FILE}')); print(c.get('model_name',''))" 2>/dev/null || echo "")
    MODEL_PROVIDER=$(python3 -c "import json; c=json.load(open('${CONFIG_FILE}')); print(c.get('model_provider',''))" 2>/dev/null || echo "")
    PROXY_URL=$(python3 -c "import json; c=json.load(open('${CONFIG_FILE}')); print(c.get('proxy',''))" 2>/dev/null || echo "")
    SKILLS_JSON=$(python3 -c "import json; c=json.load(open('${CONFIG_FILE}')); print(','.join(c.get('skills',[])))" 2>/dev/null || echo "")
    if [ -n "${SKILLS_JSON}" ] && [ -z "${AGENT_SKILLS}" ]; then
        AGENT_SKILLS="${SKILLS_JSON}"
    fi
else
    echo "[Config] No config file, using env vars."
    MODEL_URL="${AGENT_MODEL_URL:-}"
    MODEL_API_KEY="${AGENT_MODEL_API_KEY:-}"
    MODEL_NAME="${AGENT_MODEL_NAME:-}"
    MODEL_PROVIDER="${AGENT_MODEL_PROVIDER:-}"
    PROXY_URL="${AGENT_PROXY:-}"
fi

# Auto-detect provider from URL if not specified
if [ -z "${MODEL_PROVIDER}" ] && [ -n "${MODEL_URL}" ]; then
    case "${MODEL_URL}" in
        *deepseek*) MODEL_PROVIDER="deepseek" ;;
        *openai*)   MODEL_PROVIDER="openai" ;;
        *)          MODEL_PROVIDER="" ;;
    esac
    [ -n "${MODEL_PROVIDER}" ] && echo "[Config] Auto-detected provider: ${MODEL_PROVIDER}"
fi

# ─── Step 2: Generate API key if not provided ────────────────────────

AGENT_API_KEY="${AGENT_API_KEY:-$(python3 -c "import uuid; print(uuid.uuid4().hex)")}"
echo "[API] Key: ${AGENT_API_KEY:0:12}..."

# ─── Step 3: Write hermes .env (API server config) ───────────────────

cat > "${HERMES_ENV}" << HERMES_EOF
# Sconsole Agent - Hermes API Server Config
API_SERVER_ENABLED=true
API_SERVER_HOST=0.0.0.0
API_SERVER_PORT=${API_SERVER_PORT:-8642}
API_SERVER_KEY=${AGENT_API_KEY}
API_SERVER_CORS_ORIGINS=*
API_SERVER_MODEL_NAME=${MODEL_NAME:-hermes-agent}
HERMES_EOF

echo "[Hermes] .env written to ${HERMES_ENV}"

# ─── Step 4: Configure inference provider ────────────────────────────

if [ -n "${MODEL_URL}" ] && [ -n "${MODEL_NAME}" ]; then
    echo "[Hermes] Configuring provider: ${MODEL_NAME} @ ${MODEL_URL} (provider=${MODEL_PROVIDER:-auto})"

    # ── 4a: Determine provider-specific env var key ──────────────
    # Map provider name to hermes-recognized provider and env var key
    case "${MODEL_PROVIDER}" in
        deepseek)
            HERMES_PROVIDER="deepseek"
            PROVIDER_KEY_ENV="DEEPSEEK_API_KEY"
            ;;
        anthropic)
            HERMES_PROVIDER="anthropic"
            PROVIDER_KEY_ENV="ANTHROPIC_API_KEY"
            ;;
        xai)
            HERMES_PROVIDER="xai"
            PROVIDER_KEY_ENV="XAI_API_KEY"
            ;;
        google)
            HERMES_PROVIDER="google"
            PROVIDER_KEY_ENV="GOOGLE_API_KEY"
            ;;
        kimi|moonshot)
            HERMES_PROVIDER="kimi"
            PROVIDER_KEY_ENV="KIMI_API_KEY"
            ;;
        alibaba|dashscope)
            HERMES_PROVIDER="alibaba"
            PROVIDER_KEY_ENV="DASHSCOPE_API_KEY"
            ;;
        minimax)
            HERMES_PROVIDER="minimax"
            PROVIDER_KEY_ENV="MINIMAX_API_KEY"
            ;;
        glm|zai)
            HERMES_PROVIDER="glm"
            PROVIDER_KEY_ENV="GLM_API_KEY"
            ;;
        openai|openrouter)
            HERMES_PROVIDER="${MODEL_PROVIDER}"
            PROVIDER_KEY_ENV="OPENAI_API_KEY"
            ;;
        custom|*)
            # Custom or unknown provider: use custom provider mode
            HERMES_PROVIDER="custom"
            PROVIDER_KEY_ENV="OPENAI_API_KEY"
            echo "[Hermes] Custom/unknown provider — using custom provider mode"
            ;;
    esac

    # ── 4b: Set all runtime env vars ────────────────────────────
    export OPENAI_API_KEY="${MODEL_API_KEY:-sk-placeholder}"
    export OPENAI_BASE_URL="${MODEL_URL}"
    export DEFAULT_MODEL="${MODEL_NAME}"
    # Set provider-specific key env var
    if [ -n "${PROVIDER_KEY_ENV}" ]; then
        export "${PROVIDER_KEY_ENV}=${MODEL_API_KEY:-sk-placeholder}"
    fi
    echo "[Hermes] Runtime env vars set."

    # ── 4c: Write API credentials to hermes .env file ───────────
    HERMES_DOTENV="${HERMES_DIR}/.env"
    touch "${HERMES_DOTENV}"
    # Write provider-specific key
    if [ -n "${PROVIDER_KEY_ENV}" ]; then
        if ! grep -q "^${PROVIDER_KEY_ENV}=" "${HERMES_DOTENV}" 2>/dev/null; then
            echo "${PROVIDER_KEY_ENV}=${MODEL_API_KEY:-sk-placeholder}" >> "${HERMES_DOTENV}"
        fi
    fi
    # Always write generic fallback keys
    if ! grep -q "^OPENAI_API_KEY=" "${HERMES_DOTENV}" 2>/dev/null; then
        echo "OPENAI_API_KEY=${MODEL_API_KEY:-sk-placeholder}" >> "${HERMES_DOTENV}"
    fi
    if ! grep -q "^OPENAI_BASE_URL=" "${HERMES_DOTENV}" 2>/dev/null; then
        echo "OPENAI_BASE_URL=${MODEL_URL}" >> "${HERMES_DOTENV}"
    fi
    echo "[Hermes] ${PROVIDER_KEY_ENV:-OPENAI_API_KEY} written to ${HERMES_DOTENV}"

    # ── 4d: Register model via hermes config ────────────────────
    echo "[Hermes] Registering model in config.yaml..."
    hermes config set model.default "${MODEL_NAME}" 2>/dev/null || \
        echo "[Hermes][warn] hermes config set model.default failed"
    hermes config set model.base_url "${MODEL_URL}" 2>/dev/null || true
    hermes config set model.api_key "${MODEL_API_KEY}" 2>/dev/null || true
    if [ -n "${HERMES_PROVIDER}" ]; then
        hermes config set model.provider "${HERMES_PROVIDER}" 2>/dev/null || \
            echo "[Hermes][warn] Provider '${HERMES_PROVIDER}' not recognized, trying generic mode"
    fi
    echo "[Hermes] Model registered successfully."
else
    echo "[Hermes] No model URL/name provided — using hermes defaults."
fi

# ─── Step 5: Install SOUL file ───────────────────────────────────────

SOUL_SRC="${SHARED_DIR}/SOUL.md"
SOUL_DST="${HERMES_DIR}/SOUL.md"

if [ -f "${SOUL_SRC}" ] && [ -s "${SOUL_SRC}" ]; then
    cp "${SOUL_SRC}" "${SOUL_DST}"
    echo "[Soul] Installed (${SOUL_DST}, $(wc -c < ${SOUL_DST}) bytes)"
elif [ -n "${AGENT_SOUL}" ]; then
    echo "${AGENT_SOUL}" > "${SOUL_DST}"
    echo "[Soul] Installed from env (${SOUL_DST}, $(wc -c < ${SOUL_DST}) bytes)"
else
    echo "[Soul] No personality file."
fi

# ─── Step 6: Install MEMORY file ─────────────────────────────────────

MEMORY_SRC="${SHARED_DIR}/MEMORY.md"
MEMORY_DST="${HERMES_DIR}/memories/MEMORY.md"

if [ -f "${MEMORY_SRC}" ] && [ -s "${MEMORY_SRC}" ]; then
    cp "${MEMORY_SRC}" "${MEMORY_DST}"
    echo "[Memory] Installed (${MEMORY_DST}, $(wc -c < ${MEMORY_DST}) bytes)"
elif [ -n "${AGENT_MEMORY}" ]; then
    echo "${AGENT_MEMORY}" > "${MEMORY_DST}"
    echo "[Memory] Installed from env (${MEMORY_DST}, $(wc -c < ${MEMORY_DST}) bytes)"
else
    echo "[Memory] No memory file."
fi

# ─── Step 7: Install TECH_DOCS ───────────────────────────────────────

DOCS_SRC="${SHARED_DIR}/TECH_DOCS.md"
DOCS_DST="${HERMES_DIR}/tech_docs.md"

if [ -f "${DOCS_SRC}" ] && [ -s "${DOCS_SRC}" ]; then
    cp "${DOCS_SRC}" "${DOCS_DST}"
    echo "[Docs] Installed (${DOCS_DST}, $(wc -c < ${DOCS_DST}) bytes)"
elif [ -n "${AGENT_TECH_DOCS}" ]; then
    echo "${AGENT_TECH_DOCS}" > "${DOCS_DST}"
    echo "[Docs] Installed from env (${DOCS_DST})"
fi

# ─── Step 8: Install skills ──────────────────────────────────────────

# Setup proxy for skill downloads if configured
if [ -n "${PROXY_URL}" ]; then
    echo "[Skills] Using proxy: ${PROXY_URL}"
    export http_proxy="${PROXY_URL}"
    export https_proxy="${PROXY_URL}"
    export HTTP_PROXY="${PROXY_URL}"
    export HTTPS_PROXY="${PROXY_URL}"
fi

if [ -n "${AGENT_SKILLS}" ]; then
    echo "[Skills] Installing: ${AGENT_SKILLS}"
    IFS=',' read -ra SKILL_ARRAY <<< "$AGENT_SKILLS"
    for skill in "${SKILL_ARRAY[@]}"; do
        skill=$(echo "$skill" | xargs)
        if [ -n "$skill" ]; then
            skill_name=$(basename "$skill" .git)
            skill_name=$(basename "$skill_name" .zip)
            echo "  - ${skill_name}"
            if [[ "$skill" == http* ]]; then
                git clone "$skill" "${SKILLS_DIR}/${skill_name}" 2>/dev/null && \
                    echo "    cloned" || echo "    clone failed"
            elif [ -d "$skill" ]; then
                cp -r "$skill" "${SKILLS_DIR}/${skill_name}" && \
                    echo "    copied" || echo "    copy failed"
            fi
        fi
    done
fi

# Clear proxy after skill downloads
if [ -n "${PROXY_URL}" ]; then
    unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY
    echo "[Skills] Proxy cleared."
fi

# ─── Step 9: Write instance metadata ─────────────────────────────────

VOLUME_REGISTRY="${AGENT_VOLUME_DIR:-/agent/volume}/registry"
mkdir -p "${VOLUME_REGISTRY}" 2>/dev/null || true

python3 -c "
import json, os
from datetime import datetime, timezone

meta = {
    'instance_id': '${AGENT_INSTANCE_ID}',
    'api_key': '${AGENT_API_KEY}',
    'api_port': ${API_SERVER_PORT:-8642},
    'host_port': '${AGENT_HOST_PORT:-0}',
    'model_name': '${MODEL_NAME:-hermes-agent}',
    'registered_at': datetime.now(timezone.utc).isoformat(),
}

# Write to shared dir (for node to read)
with open('${SHARED_DIR}/.agent_meta.json', 'w') as f:
    json.dump(meta, f)

# Write to shared volume registry (for inter-agent discovery)
reg_file = '${VOLUME_REGISTRY}/${AGENT_INSTANCE_ID}.json'
with open(reg_file, 'w') as f:
    json.dump(meta, f, indent=2)
print(f'[Registry] Registered agent #${AGENT_INSTANCE_ID} at {reg_file}')
" 2>/dev/null || true

# ─── Step 10: Launch hermes gateway ──────────────────────────────────

echo ""
echo "========================================="
echo "  Agent #${AGENT_INSTANCE_ID} - Gateway Mode"
echo "  Model:  ${MODEL_NAME:-default}"
echo "  API:    http://0.0.0.0:${API_SERVER_PORT:-8642}/v1"
echo "  Key:    ${AGENT_API_KEY:0:12}..."
echo "========================================="
echo ""

exec hermes gateway
