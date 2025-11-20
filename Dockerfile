# Multi-stage Dockerfile for imbi-automations with Claude Code
FROM python:3.12-trixie AS builder

# Install build dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        git \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy source files needed for build
COPY pyproject.toml README.md /app/
COPY src/ /app/src/
WORKDIR /app

# Install imbi-automations and dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir .

# Final stage
FROM python:3.12-trixie

# Install runtime dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        git \
        openssh-client \
        curl \
        ca-certificates \
        gnupg \
    && rm -rf /var/lib/apt/lists/*

# Install Claude Code standalone using official installer
# Note: The installer requires bash, not sh
RUN curl -fsSL https://claude.ai/install.sh | bash

# Copy virtual environment from builder (already has imbi-automations installed)
COPY --from=builder /opt/venv /opt/venv

# Add both venv and claude to PATH
ENV PATH="/root/.local/bin:/opt/venv/bin:$PATH"

# Create directories for mounted volumes
RUN mkdir -p /config /workflows /cache /workspace /root/.ssh && \
    chmod 700 /root/.ssh

# Set up git configuration (can be overridden by environment variables)
RUN git config --global user.name "Imbi Automations" && \
    git config --global user.email "imbi-automations@example.com"

# Environment variables for configuration
ENV IMBI_AUTOMATIONS_CACHE_DIR=/cache
ENV IMBI_AUTOMATIONS_CONFIG=/config/config.toml

# Default working directory for temporary repo clones
WORKDIR /workspace

# Default entrypoint
ENTRYPOINT ["imbi-automations"]

# Default command (can be overridden)
CMD ["--help"]
