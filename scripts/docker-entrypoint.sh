#!/bin/bash
set -e

# Entrypoint script for Penguin Overlord
# Checks data directory permissions before starting the bot

# Color codes for output
RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

echo -e "${GREEN}[Penguin Overlord] Starting entrypoint script...${NC}"

# Check if /app/data directory exists and is writable
if [ -d "/app/data" ]; then
    if [ ! -w "/app/data" ]; then
        echo -e "${RED}╔════════════════════════════════════════════════════════════════╗${NC}"
        echo -e "${RED}║           PERMISSION ERROR: /app/data NOT WRITABLE            ║${NC}"
        echo -e "${RED}╚════════════════════════════════════════════════════════════════╝${NC}"
        echo ""
        echo -e "${YELLOW}State persistence (XKCD, comics, news tracking) will fail!${NC}"
        echo ""
        echo -e "${CYAN}Container user:${NC}"
        id
        echo ""
        echo -e "${CYAN}/app/data ownership:${NC}"
        ls -ld /app/data
        echo ""
        echo -e "${GREEN}═══════════════════════════ FIX ════════════════════════════════${NC}"
        echo -e "${YELLOW}On the HOST machine, run:${NC}"
        echo ""
        
        # Get the numeric UID/GID
        PENGUIN_UID=$(id -u)
        PENGUIN_GID=$(id -g)
        
        if [ -n "$PENGUIN_UID" ] && [ -n "$PENGUIN_GID" ]; then
            echo -e "${CYAN}  # Fix permissions for existing volume:${NC}"
            echo -e "  docker run --rm -v penguin-overlord_penguin-data:/data alpine:latest chown -R ${PENGUIN_UID}:${PENGUIN_GID} /data"
            echo ""
            echo -e "${CYAN}  # OR if using bind mount (./data):${NC}"
            echo -e "  sudo chown -R ${PENGUIN_UID}:${PENGUIN_GID} ./data"
            echo ""
            echo -e "${CYAN}  # Then restart container:${NC}"
            echo -e "  docker-compose restart"
        fi
        
        echo ""
        echo -e "${YELLOW}See: docs/deployment/DOCKER_VOLUME_PERMISSIONS.md${NC}"
        echo -e "${GREEN}════════════════════════════════════════════════════════════════${NC}"
        echo ""
    else
        echo -e "${GREEN}[✓] /app/data is writable${NC}"
    fi
else
    echo -e "${YELLOW}[WARNING] /app/data directory does not exist, creating...${NC}"
    mkdir -p /app/data 2>/dev/null || {
        echo -e "${RED}[ERROR] Cannot create /app/data - permission denied${NC}"
    }
fi

# Start the bot
echo -e "${GREEN}[Penguin Overlord] Starting bot...${NC}"
echo ""
exec python -u penguin-overlord/bot.py "$@"
