#!/bin/bash
# Penguin Overlord - systemd Service Installation Script
# Installs Penguin Overlord Discord Bot as a systemd service

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}ERROR: Run as root (use sudo)${NC}"
    exit 1
fi

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
ACTUAL_USER="${SUDO_USER:-$USER}"

echo -e "${GREEN}Penguin Overlord - systemd Installer${NC}"
echo "Project: $PROJECT_DIR"
echo "User: $ACTUAL_USER"
echo ""

[ ! -f "$PROJECT_DIR/penguin-overlord/bot.py" ] && echo -e "${RED}ERROR: bot.py not found${NC}" && exit 1
[ ! -d "$PROJECT_DIR/penguin-overlord/cogs" ] && echo -e "${RED}ERROR: cogs/ not found${NC}" && exit 1

# Check if service already exists and is running
if systemctl list-units --full --all | grep -q "penguin-overlord.service"; then
    echo -e "${YELLOW}Service already exists${NC}"
    
    if systemctl is-active --quiet penguin-overlord.service; then
        echo -e "${YELLOW}Bot is currently running${NC}"
        read -p "Stop bot before reinstalling? (Y/n) " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Nn]$ ]]; then
            echo "Stopping penguin-overlord service..."
            systemctl stop penguin-overlord.service
            sleep 2
            echo -e "${GREEN}✓${NC} Service stopped"
        else
            echo -e "${YELLOW}WARNING: Service is still running. Installation may conflict.${NC}"
            read -p "Continue anyway? (y/N) " -n 1 -r
            echo
            [[ ! $REPLY =~ ^[Yy]$ ]] && exit 1
        fi
    else
        echo "Service exists but is not running"
    fi
    
    # Ask if they want to keep the same deployment mode
    echo ""
    read -p "Reinstall with same configuration? (Y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Nn]$ ]]; then
        # Try to detect current deployment mode from service file
        if [ -f "/etc/systemd/system/penguin-overlord.service" ]; then
            if grep -q "docker" /etc/systemd/system/penguin-overlord.service; then
                DETECTED_MODE="Docker"
                AUTO_MODE="2"
            else
                DETECTED_MODE="Python"
                AUTO_MODE="1"
            fi
            echo -e "${GREEN}Detected: $DETECTED_MODE deployment${NC}"
            DEPLOYMENT_MODE="$AUTO_MODE"
            SKIP_MODE_PROMPT=true
        fi
    fi
fi
echo ""

if [ "$SKIP_MODE_PROMPT" != "true" ]; then
    echo "Choose deployment mode:"
    echo "  1) Python (virtual environment)"
    echo "  2) Docker (container)"
    read -p "Select [1-2]: " -n 1 -r DEPLOYMENT_MODE
    echo ""
    
    [[ ! $DEPLOYMENT_MODE =~ ^[1-2]$ ]] && echo -e "${RED}Invalid option${NC}" && exit 1
fi

if [ ! -f "$PROJECT_DIR/.env" ]; then
    echo -e "${YELLOW}WARNING: .env not found!${NC}"
    echo "Create .env with DISCORD_TOKEN before starting"
    read -p "Continue? (y/N) " -n 1 -r
    echo
    [[ ! $REPLY =~ ^[Yy]$ ]] && exit 1
fi

if [ "$DEPLOYMENT_MODE" = "1" ]; then
    echo -e "${GREEN}Python deployment...${NC}"
    
    PYTHON_CMD=""
    for v in python3.14 python3.13 python3.12 python3.11 python3.10 python3; do
        command -v $v &> /dev/null && PYTHON_CMD=$v && break
    done
    
    [ -z "$PYTHON_CMD" ] && echo -e "${RED}Python 3.10+ required${NC}" && exit 1
    
    echo -e "${GREEN}✓${NC} Found: $($PYTHON_CMD --version)"
    
    if [ ! -d "$PROJECT_DIR/venv" ]; then
        sudo -u $ACTUAL_USER $PYTHON_CMD -m venv "$PROJECT_DIR/venv"
        echo -e "${GREEN}✓${NC} venv created"
    fi
    
    sudo -u $ACTUAL_USER "$PROJECT_DIR/venv/bin/pip" install --upgrade pip > /dev/null 2>&1
    sudo -u $ACTUAL_USER "$PROJECT_DIR/venv/bin/pip" install -r "$PROJECT_DIR/requirements.txt" > /dev/null 2>&1
    echo -e "${GREEN}✓${NC} Dependencies installed"
    
    sudo -u $ACTUAL_USER "$PROJECT_DIR/venv/bin/python" -c "import discord" &> /dev/null || (echo -e "${RED}discord.py failed${NC}" && exit 1)
    echo -e "${GREEN}✓${NC} discord.py verified"
    
    cat > /etc/systemd/system/penguin-overlord.service << EOF
[Unit]
Description=Penguin Overlord Discord Bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$ACTUAL_USER
Group=$ACTUAL_USER
WorkingDirectory=$PROJECT_DIR/penguin-overlord
Environment="PATH=$PROJECT_DIR/venv/bin:/usr/local/bin:/usr/bin:/bin"
ExecStart=$PROJECT_DIR/venv/bin/python $PROJECT_DIR/penguin-overlord/bot.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=penguin-overlord
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths=$PROJECT_DIR

[Install]
WantedBy=multi-user.target
EOF

elif [ "$DEPLOYMENT_MODE" = "2" ]; then
    echo -e "${GREEN}Docker deployment...${NC}"
    
    command -v docker &> /dev/null || (echo -e "${RED}Docker not installed${NC}" && exit 1)
    echo -e "${GREEN}✓${NC} Docker: $(docker --version)"
    
    if ! groups $ACTUAL_USER | grep -q docker; then
        usermod -aG docker $ACTUAL_USER
        echo -e "${GREEN}✓${NC} Added to docker group (logout required)"
    fi
    
    DOCKER_CMD=$(groups $ACTUAL_USER | grep -q docker && echo "sudo -u $ACTUAL_USER docker" || echo "docker")
    IMAGE_NAME="penguin-overlord"
    
    if docker images --format "{{.Repository}}" | grep -q "^${IMAGE_NAME}$"; then
        echo -e "${GREEN}✓${NC} Image exists"
        if [ "$SERVICE_EXISTS" = true ]; then
            # If service exists, default to rebuilding to get latest code
            read -p "Rebuild/pull latest image? (Y/n) " -n 1 -r
            echo
            [[ $REPLY =~ ^[Nn]$ ]] && BUILD=false || BUILD=true
        else
            # New install, ask if they want to use existing
            read -p "Use existing? (Y/n) " -n 1 -r
            echo
            [[ $REPLY =~ ^[Nn]$ ]] && BUILD=true || BUILD=false
        fi
    else
        BUILD=true
    fi
    
    if [ "$BUILD" = true ]; then
        # Remove ALL old images - local AND GHCR cached
        echo "Removing all old images..."
        $DOCKER_CMD rmi -f $IMAGE_NAME:latest 2>/dev/null || true
        $DOCKER_CMD rmi -f ghcr.io/chiefgyk3d/penguin-overlord:latest 2>/dev/null || true
        
        echo "1) Build local  2) Pull from GHCR"
        echo -e "${YELLOW}Note: GHCR only has code from 'main' branch. Use option 1 for dev branches.${NC}"
        read -p "Select [1-2]: " -n 1 -r SRC
        echo ""
        
        if [ "$SRC" = "2" ]; then
            echo "Pulling fresh image from GHCR (main branch only)..."
            $DOCKER_CMD pull ghcr.io/chiefgyk3d/penguin-overlord:latest && \
            $DOCKER_CMD tag ghcr.io/chiefgyk3d/penguin-overlord:latest $IMAGE_NAME:latest
        else
            [ ! -f "$PROJECT_DIR/Dockerfile" ] && echo -e "${RED}Dockerfile not found${NC}" && exit 1
            echo "Building fresh image with --no-cache..."
            cd "$PROJECT_DIR" && $DOCKER_CMD build --no-cache --pull -t $IMAGE_NAME -f Dockerfile .
        fi
        echo -e "${GREEN}✓${NC} Image ready"
    fi
    
    cat > /etc/systemd/system/penguin-overlord.service << EOF
[Unit]
Description=Penguin Overlord Discord Bot (Docker)
After=docker.service network-online.target
Requires=docker.service
Wants=network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
User=$ACTUAL_USER
Group=$ACTUAL_USER
WorkingDirectory=$PROJECT_DIR
ExecStart=/usr/bin/docker run -d --name penguin-overlord --restart unless-stopped --env-file $PROJECT_DIR/.env -v $PROJECT_DIR/events:/app/events:ro $IMAGE_NAME
ExecStop=/usr/bin/docker stop penguin-overlord
ExecStopPost=/usr/bin/docker rm -f penguin-overlord
StandardOutput=journal
StandardError=journal
SyslogIdentifier=penguin-overlord

[Install]
WantedBy=multi-user.target
EOF
fi

echo -e "${GREEN}✓${NC} Service file created"

systemctl daemon-reload
echo -e "${GREEN}✓${NC} systemd reloaded"

# Check if service was previously enabled
WAS_ENABLED=false
if systemctl is-enabled --quiet penguin-overlord.service 2>/dev/null; then
    WAS_ENABLED=true
    echo -e "${GREEN}✓${NC} Service already enabled"
else
    read -p "Enable on boot? (Y/n) " -n 1 -r
    echo
    [[ ! $REPLY =~ ^[Nn]$ ]] && systemctl enable penguin-overlord.service && echo -e "${GREEN}✓${NC} Enabled" && WAS_ENABLED=true
fi

# If we stopped the service earlier or it wasn't running, ask about starting
read -p "Start/restart service now? (Y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Nn]$ ]]; then
    echo "Starting penguin-overlord service..."
    systemctl restart penguin-overlord.service
    sleep 3
    
    if systemctl is-active --quiet penguin-overlord.service; then
        echo -e "${GREEN}✓${NC} Service is running!"
        
        # Show last few log lines
        echo ""
        echo "Recent logs:"
        journalctl -u penguin-overlord -n 5 --no-pager
    else
        echo -e "${RED}✗ Service failed to start${NC}"
        echo ""
        echo "Error details:"
        systemctl status penguin-overlord.service --no-pager | tail -10
        echo ""
        echo -e "${YELLOW}Check logs: sudo journalctl -u penguin-overlord -n 50${NC}"
    fi
fi

echo ""
echo -e "${GREEN}Installation Complete!${NC}"
echo ""
echo "Commands:"
echo "  sudo systemctl start|stop|restart|status penguin-overlord"
echo "  sudo journalctl -u penguin-overlord -f"
