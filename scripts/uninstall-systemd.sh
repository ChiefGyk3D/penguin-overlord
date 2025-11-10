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
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            docker rmi -f penguin-overlord 2>/dev/null || true
            echo -e "${GREEN}✓${NC} Image removed"
        fi
    fi
fi

systemctl is-enabled --quiet penguin-overlord.service 2>/dev/null && systemctl disable penguin-overlord.service && echo -e "${GREEN}✓${NC} Service disabled"

rm -f "$SERVICE_FILE"
echo -e "${GREEN}✓${NC} Service file removed"

# Check for and remove news timer services
NEWS_CATEGORIES=("cve" "cybersecurity" "tech" "gaming" "apple_google" "us_legislation" "eu_legislation" "uk_legislation" "general_news")
TIMER_COUNT=0

for category in "${NEWS_CATEGORIES[@]}"; do
    TIMER_FILE="/etc/systemd/system/penguin-news-${category}.timer"
    SERVICE_FILE_NEWS="/etc/systemd/system/penguin-news-${category}.service"
    
    if [ -f "$TIMER_FILE" ] || [ -f "$SERVICE_FILE_NEWS" ]; then
        # Stop and disable timer if running
        if systemctl is-active --quiet "penguin-news-${category}.timer" 2>/dev/null; then
            systemctl stop "penguin-news-${category}.timer" 2>/dev/null || true
        fi
        
        if systemctl is-enabled --quiet "penguin-news-${category}.timer" 2>/dev/null; then
            systemctl disable "penguin-news-${category}.timer" 2>/dev/null || true
        fi
        
        # Remove files
        rm -f "$TIMER_FILE" "$SERVICE_FILE_NEWS"
        TIMER_COUNT=$((TIMER_COUNT + 1))
    fi
done

if [ $TIMER_COUNT -gt 0 ]; then
    echo -e "${GREEN}✓${NC} Removed $TIMER_COUNT news timer(s)"
fi

# Check for and remove background task timers (KEV, Solar, XKCD, Comics)
BACKGROUND_TASKS=("kev" "solar" "xkcd" "comics")
BACKGROUND_COUNT=0

for task in "${BACKGROUND_TASKS[@]}"; do
    TIMER_FILE="/etc/systemd/system/penguin-${task}.timer"
    SERVICE_FILE_TASK="/etc/systemd/system/penguin-${task}.service"
    
    if [ -f "$TIMER_FILE" ] || [ -f "$SERVICE_FILE_TASK" ]; then
        # Stop and disable timer if running
        if systemctl is-active --quiet "penguin-${task}.timer" 2>/dev/null; then
            systemctl stop "penguin-${task}.timer" 2>/dev/null || true
        fi
        
        if systemctl is-enabled --quiet "penguin-${task}.timer" 2>/dev/null; then
            systemctl disable "penguin-${task}.timer" 2>/dev/null || true
        fi
        
        # Remove files
        rm -f "$TIMER_FILE" "$SERVICE_FILE_TASK"
        BACKGROUND_COUNT=$((BACKGROUND_COUNT + 1))
    fi
done

if [ $BACKGROUND_COUNT -gt 0 ]; then
    echo -e "${GREEN}✓${NC} Removed $BACKGROUND_COUNT background task timer(s)"
fi

systemctl daemon-reload
systemctl reset-failed
echo -e "${GREEN}✓${NC} systemd reloaded"

echo ""
echo -e "${GREEN}Uninstallation complete!${NC}"
echo ""
echo -e "${YELLOW}Note: Project files, venv, and .env not removed${NC}"
echo "To remove manually:"
echo "  rm -rf /path/to/penguin-overlord"
