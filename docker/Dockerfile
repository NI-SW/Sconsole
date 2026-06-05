# Sconsole Agent Docker Image
# Based on hermes-agent, starts gateway API server on container port 8642
FROM docker.io/nousresearch/hermes-agent:latest

LABEL org.sconsole.agent="true"
LABEL description="Sconsole Agent - Hermes Gateway Runtime"

# Switch to root for setup
USER root

# Create directories with proper permissions
RUN mkdir -p /agent/shared /agent/skills /agent/config /agent/logs /agent/volume; \
    mkdir -p /root/.hermes /root/.hermes/skills /root/.hermes/logs; \
    chmod 777 /agent/shared /agent/volume

# Fix hermes data directory permissions
RUN chown -R root:root /opt/data 2>/dev/null; \
    chmod -R 777 /opt/data 2>/dev/null; \
    mkdir -p /opt/data/logs /opt/data/memories /opt/data/skills; \
    chmod 777 /opt/data/logs;\
    chown hermes: -R /opt/data

# Install pip for agent-side package management
RUN apt-get update && apt-get install -y python3-pip sudo && \
    rm -rf /var/lib/apt/lists/* && \
    echo "hermes ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/hermes && \
    chmod 440 /etc/sudoers.d/hermes

# Copy entrypoint
COPY docker/scripts/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Copy built-in intercom skill
RUN mkdir -p /agent/skills/sconsole-intercom/scripts
COPY skills/sconsole-intercom/ /agent/skills/sconsole-intercom/
COPY skills/task-planner/ /agent/skills/task-planner/
RUN chmod +x /agent/skills/sconsole-intercom/scripts/*.py

# Run as root (hermes-agent requires access to /opt/data)
USER root
WORKDIR /agent

# Container ports
# 8642 = hermes gateway API server
EXPOSE 8642

# Volume for shared files with host
VOLUME ["/agent/shared"]

# Environment defaults
ENV AGENT_INSTANCE_ID=0
ENV AGENT_SHARED_DIR=/agent/shared
ENV AGENT_SKILLS_DIR=/agent/skills
ENV AGENT_CONFIG_DIR=/agent/config
ENV AGENT_LOG_DIR=/agent/logs
ENV AGENT_VOLUME_DIR=/agent/volume
ENV HOME=/root
ENV PIP_BREAK_SYSTEM_PACKAGES=1
ENV HERMES_HOME=/opt/data
ENV API_SERVER_PORT=8642
ENV API_SERVER_HOST=0.0.0.0

ENTRYPOINT ["/entrypoint.sh"]
