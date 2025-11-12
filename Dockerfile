# Penguin Overlord Discord Bot - Dockerfile
# Multi-stage build for optimized production image
# Python 3.14-slim with security updates

# Build stage
FROM python:3.14-slim AS builder

# Set working directory
WORKDIR /build

# Install build dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    make \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better layer caching
COPY requirements.txt .

# Create virtual environment and install dependencies
RUN python -m venv /opt/venv && \
    /opt/venv/bin/pip install --upgrade pip setuptools wheel && \
    /opt/venv/bin/pip install --no-cache-dir -r requirements.txt

# Production stage
FROM python:3.14-slim

# Metadata
LABEL maintainer="ChiefGyk3D <https://github.com/ChiefGyk3D>"
LABEL description="Penguin Overlord - A feature-rich Discord bot for tech communities"
LABEL org.opencontainers.image.source="https://github.com/ChiefGyk3D/penguin-overlord"
LABEL org.opencontainers.image.licenses="MPL-2.0"

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH" \
    DEBIAN_FRONTEND=noninteractive

# Create non-root user for security
RUN groupadd -r penguin && \
    useradd -r -g penguin -d /app -s /bin/bash penguin

# CRITICAL: Upgrade ALL system packages for security remediation
# This ensures all CVEs and security issues are patched
RUN apt-get update && \
    apt-get upgrade -y --no-install-recommends && \
    apt-get dist-upgrade -y --no-install-recommends && \
    apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    && apt-get autoremove -y && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Set working directory
WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv

# Copy application code
COPY --chown=penguin:penguin penguin-overlord/ ./penguin-overlord/
COPY --chown=penguin:penguin events/ ./events/
COPY --chown=penguin:penguin .env.example ./.env.example

# Copy entrypoint script
COPY scripts/docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Create data directory for cog state persistence with proper permissions
RUN mkdir -p /app/data && chown -R penguin:penguin /app/data

# Declare volume for state persistence
VOLUME ["/app/data"]

# Switch to non-root user
USER penguin

# Environment Variables Documentation:
# 
# The bot supports multiple secret management methods (checked in order):
#
# 1. DOPPLER (Recommended for production):
#    - Set DOPPLER_TOKEN environment variable
#    - Optional: DOPPLER_PROJECT (default: stream-daemon)
#    - Optional: DOPPLER_CONFIG (default: prd)
#    - Bot will fetch DISCORD_BOT_TOKEN from Doppler automatically
#
# 2. AWS Secrets Manager:
#    - Set AWS credentials (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY)
#    - Set SECRETS_MANAGER=aws
#    - Configure secret name with AWS_SECRET_NAME
#
# 3. HashiCorp Vault:
#    - Set SECRETS_MANAGER=vault
#    - Set SECRETS_VAULT_URL and SECRETS_VAULT_TOKEN
#
# 4. Environment Variables (Simple, for development):
#    - Set DISCORD_BOT_TOKEN directly as environment variable
#    - Can be passed via docker run -e or in .env file mounted to container
#
# 5. .env File (Fallback):
#    - Mount .env file: -v /path/to/.env:/app/.env:ro
#    - File should contain: DISCORD_BOT_TOKEN=your_token_here
#
# Example Docker runs:
#
# With Doppler:
#   docker run -e DOPPLER_TOKEN=dp.st.xxx ghcr.io/chiefgyk3d/penguin-overlord
#
# With .env file:
#   docker run --env-file .env ghcr.io/chiefgyk3d/penguin-overlord
#
# With direct env var:
#   docker run -e DISCORD_BOT_TOKEN=your_token ghcr.io/chiefgyk3d/penguin-overlord

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import sys; sys.exit(0)"

# Set entrypoint
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]

# Default command (can be overridden)
# Note: Bot will load .env automatically via python-dotenv if present in /app/
CMD []
