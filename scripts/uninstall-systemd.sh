#!/bin/bash
# Penguin Overlord - systemd Service Uninstaller

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}ERROR: Run as root (use sudo)${NC}"
    exit 1
fi

SERVICE_FILE="/etc/systemd/system/penguin-overlord.service"

echo -e "${YELLOW}Penguin Overlord - Uninstaller${NC}"
echo ""

[ ! -f "$SERVICE_FILE" ] && echo -e "${YELLOW}Service not installed${NC}" && exit 0

IS_DOCKER=$(grep -q "docker run" "$SERVICE_FILE" && echo true || echo false)
echo "Deployment: $([ "$IS_DOCKER" = true ] && echo Docker || echo Python)"

if systemctl is-active --quiet penguin-overlord.service; then
    systemctl stop penguin-overlord.service
    echo -e "${GREEN}✓${NC} Service stopped"
fi

if [ "$IS_DOCKER" = true ] && command -v docker &> /dev/null; then
    if docker ps -a --format '{{.Names}}' | grep -q '^penguin-overlord$'; then
        docker rm -f penguin-overlord 2>/dev/null || true
        echo -e "${GREEN}✓${NC} Container removed"
    fi
    
    if docker images --format "{{.Repository}}" | grep -q "^penguin-overlord$"; then
        read -p "Remove Docker image? (y/N) " -n 1 -r
        echo
        [[ $REPLY =~ ^[Yy]$ ]] && docker rmi penguin-overlord && echo -e "${GREEN}✓${NC} Image removed"
    fi
fi

systemctl is-enabled --quiet penguin-overlord.service 2>/dev/null && systemctl disable penguin-overlord.service && echo -e "${GREEN}✓${NC} Service disabled"

rm -f "$SERVICE_FILE"
echo -e "${GREEN}✓${NC} Service file removed"

systemctl daemon-reload
systemctl reset-failed
echo -e "${GREEN}✓${NC} systemd reloaded"

echo ""
echo -e "${GREEN}Uninstallation complete!${NC}"
echo ""
echo -e "${YELLOW}Note: Project files, venv, and .env not removed${NC}"
echo "To remove manually:"
echo "  rm -rf /path/to/penguin-overlord"
