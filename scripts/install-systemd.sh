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

# Ask about news system optimization
echo ""
echo -e "${BLUE}News System Configuration:${NC}"
echo "The bot includes news aggregation for 73+ sources across 8 categories."
echo ""
echo "Choose news fetching strategy:"
echo -e "  1) ${GREEN}Integrated${NC} - News runs inside bot (simpler, 500MB RAM constant)"
echo -e "  2) ${GREEN}Optimized${NC}  - Separate systemd timers (99% less bandwidth, 0MB idle)"
echo ""
read -p "Select [1-2] (default: 1): " -n 1 -r NEWS_MODE
echo ""
NEWS_MODE="${NEWS_MODE:-1}"

[[ ! $NEWS_MODE =~ ^[1-2]$ ]] && echo -e "${YELLOW}Invalid option, using integrated mode${NC}" && NEWS_MODE="1"

if [ "$NEWS_MODE" = "2" ]; then
    echo -e "${GREEN}✓${NC} Will deploy optimized news timers"
    DEPLOY_NEWS_TIMERS=true
else
    echo -e "${GREEN}✓${NC} News will run integrated in bot"
    DEPLOY_NEWS_TIMERS=false
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
        # Stop and remove container if running (so we can remove image)
        if docker ps -a --format '{{.Names}}' | grep -q '^penguin-overlord$'; then
            echo "Stopping existing container..."
            docker stop penguin-overlord 2>/dev/null || true
            docker rm -f penguin-overlord 2>/dev/null || true
        fi
        
        # Remove ALL old images - local AND GHCR cached (with and without :latest tag)
        echo "Removing all old images..."
        $DOCKER_CMD rmi -f $IMAGE_NAME:latest 2>/dev/null || true
        $DOCKER_CMD rmi -f $IMAGE_NAME 2>/dev/null || true
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
ExecStart=/usr/bin/docker run -d --name penguin-overlord --restart unless-stopped --env-file $PROJECT_DIR/.env -v $PROJECT_DIR/events:/app/events:ro -v $PROJECT_DIR/data:/app/data $IMAGE_NAME
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

# Create data directory with proper permissions for cache files
if [ "$IS_DOCKER" = true ]; then
    mkdir -p "$PROJECT_DIR/data"
    chown -R $ACTUAL_USER:$ACTUAL_USER "$PROJECT_DIR/data"
    chmod -R 755 "$PROJECT_DIR/data"
    echo -e "${GREEN}✓${NC} Data directory prepared"
fi

# Deploy news timers if optimized mode selected
if [ "$DEPLOY_NEWS_TIMERS" = true ]; then
    echo ""
    echo -e "${BLUE}Deploying Optimized News Timers...${NC}"
    
    # Function to create news service
    create_news_service() {
        local category=$1
        local service_file="/etc/systemd/system/penguin-news-${category}.service"
        
        # Create service based on deployment mode
        if [ "$DEPLOYMENT_MODE" = "1" ]; then
            # Python deployment - use venv
            cat > "$service_file" << EOF
[Unit]
Description=Penguin Bot News Fetcher - ${category}
After=network.target

[Service]
Type=oneshot
User=$ACTUAL_USER
Group=$ACTUAL_USER
WorkingDirectory=$PROJECT_DIR/penguin-overlord
Environment="PATH=$PROJECT_DIR/venv/bin:/usr/local/bin:/usr/bin:/bin"
ExecStart=$PROJECT_DIR/venv/bin/python $PROJECT_DIR/penguin-overlord/news_runner.py --category ${category}
StandardOutput=journal
StandardError=journal
SyslogIdentifier=penguin-news-${category}

# Resource limits
MemoryMax=256M
CPUQuota=50%
TasksMax=50
TimeoutStartSec=120

[Install]
WantedBy=multi-user.target
EOF
        else
            # Docker deployment - use container
            cat > "$service_file" << EOF
[Unit]
Description=Penguin Bot News Fetcher - ${category} (Docker)
After=docker.service network.target
Requires=docker.service

[Service]
Type=oneshot
User=$ACTUAL_USER
Group=$ACTUAL_USER
WorkingDirectory=$PROJECT_DIR
ExecStart=/usr/bin/docker run --rm --name penguin-news-${category} --user $(id -u):$(id -g) --env-file $PROJECT_DIR/.env -v $PROJECT_DIR/data:/app/data $IMAGE_NAME python3 /app/penguin-overlord/news_runner.py --category ${category}
StandardOutput=journal
StandardError=journal
SyslogIdentifier=penguin-news-${category}

# Resource limits
MemoryMax=300M
CPUQuota=50%
TasksMax=50
TimeoutStartSec=180

[Install]
WantedBy=multi-user.target
EOF
        fi
        echo "  ✓ Created penguin-news-${category}.service"
    }
    
    # Function to create news timer
    create_news_timer() {
        local category=$1
        local calendar=$2
        local timer_file="/etc/systemd/system/penguin-news-${category}.timer"
        
        cat > "$timer_file" << EOF
[Unit]
Description=Penguin Bot ${category^} News Fetcher Timer
Requires=penguin-news-${category}.service

[Timer]
OnCalendar=$calendar
Persistent=true
AccuracySec=1min

[Install]
WantedBy=timers.target
EOF
        echo "  ✓ Created penguin-news-${category}.timer"
    }
    
    # Create all news services and timers
    create_news_service "cve"
    create_news_timer "cve" "*-*-* 00,08,16:00:00"
    
    create_news_service "kev"
    create_news_timer "kev" "*-*-* 00,04,08,12,16,20:30:00"
    
    create_news_service "cybersecurity"
    create_news_timer "cybersecurity" "*-*-* 00,03,06,09,12,15,18,21:01:00"
    
    create_news_service "tech"
    create_news_timer "tech" "*-*-* 00,04,08,12,16,20:30:00"
    
    create_news_service "gaming"
    create_news_timer "gaming" "*-*-* 00,02,04,06,08,10,12,14,16,18,20,22:15:00"
    
    create_news_service "apple_google"
    create_news_timer "apple_google" "*-*-* 00,03,06,09,12,15,18,21:45:00"
    
    create_news_service "us_legislation"
    create_news_timer "us_legislation" "*-*-* *:05:00"
    
    create_news_service "eu_legislation"
    create_news_timer "eu_legislation" "*-*-* *:10:00"
    
    create_news_service "uk_legislation"
    create_news_timer "uk_legislation" "*-*-* *:15:00"
    
    create_news_service "general_news"
    create_news_timer "general_news" "*-*-* 00,02,04,06,08,10,12,14,16,18,20,22:20:00"
    
    echo -e "${GREEN}✓${NC} All news timers created"
    
    # Create background task services (solar, xkcd, comics)
    echo ""
    echo -e "${BLUE}Creating Background Task Timers...${NC}"
    
    # Function to create background task service
    create_background_service() {
        local task_name=$1
        local script_name=$2
        local service_file="/etc/systemd/system/penguin-${task_name}.service"
        
        if [ "$DEPLOYMENT_MODE" = "1" ]; then
            # Python deployment
            cat > "$service_file" << EOF
[Unit]
Description=Penguin Bot ${task_name^} Poster
After=network.target

[Service]
Type=oneshot
User=$ACTUAL_USER
Group=$ACTUAL_USER
WorkingDirectory=$PROJECT_DIR/penguin-overlord
Environment="PATH=$PROJECT_DIR/venv/bin:/usr/local/bin:/usr/bin:/bin"
ExecStart=$PROJECT_DIR/venv/bin/python $PROJECT_DIR/penguin-overlord/${script_name}
StandardOutput=journal
StandardError=journal
SyslogIdentifier=penguin-${task_name}

# Resource limits
MemoryMax=256M
CPUQuota=50%
TasksMax=50
TimeoutStartSec=60

[Install]
WantedBy=multi-user.target
EOF
        else
            # Docker deployment
            cat > "$service_file" << EOF
[Unit]
Description=Penguin Bot ${task_name^} Poster (Docker)
After=docker.service network.target
Requires=docker.service

[Service]
Type=oneshot
User=$ACTUAL_USER
Group=$ACTUAL_USER
WorkingDirectory=$PROJECT_DIR
ExecStart=/usr/bin/docker run --rm --name penguin-${task_name} --user $(id -u):$(id -g) --env-file $PROJECT_DIR/.env -v $PROJECT_DIR/data:/app/data $IMAGE_NAME python3 /app/penguin-overlord/${script_name}
StandardOutput=journal
StandardError=journal
SyslogIdentifier=penguin-${task_name}

# Resource limits
MemoryMax=300M
CPUQuota=50%
TasksMax=50
TimeoutStartSec=90

[Install]
WantedBy=multi-user.target
EOF
        fi
        echo "  ✓ Created penguin-${task_name}.service"
    }
    
    # Function to create background task timer
    create_background_timer() {
        local task_name=$1
        local calendar=$2
        local timer_file="/etc/systemd/system/penguin-${task_name}.timer"
        
        cat > "$timer_file" << EOF
[Unit]
Description=Penguin Bot ${task_name^} Poster Timer
Requires=penguin-${task_name}.service

[Timer]
OnCalendar=$calendar
Persistent=true
AccuracySec=1min

[Install]
WantedBy=timers.target
EOF
        echo "  ✓ Created penguin-${task_name}.timer"
    }
    
    # Create solar/propagation service and timer (every 6 hours)
    create_background_service "solar" "solar_runner.py"
    create_background_timer "solar" "*-*-* 00,06,12,18:00:00"
    
    # Create XKCD service and timer (every 30 minutes)
    create_background_service "xkcd" "xkcd_runner.py"
    create_background_timer "xkcd" "*-*-* *:00,30:00"
    
    # Create comics service and timer (once daily at 10:00 UTC)
    create_background_service "comics" "comics_runner.py"
    create_background_timer "comics" "*-*-* 10:00:00"
    
    echo -e "${GREEN}✓${NC} Background task timers created"
    
    # Enable and start timers
    echo ""
    read -p "Enable and start all timers? (Y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Nn]$ ]]; then
        # News timers
        for category in cve kev cybersecurity tech gaming apple_google us_legislation eu_legislation uk_legislation general_news; do
            systemctl enable penguin-news-${category}.timer 2>/dev/null || true
            systemctl start penguin-news-${category}.timer 2>/dev/null || true
        done
        # Background task timers
        for task in solar xkcd comics; do
            systemctl enable penguin-${task}.timer 2>/dev/null || true
            systemctl start penguin-${task}.timer 2>/dev/null || true
        done
        echo -e "${GREEN}✓${NC} All timers enabled and started"
    else
        echo "Skipping timer activation"
    fi
fi

systemctl daemon-reload
echo -e "${GREEN}✓${NC} systemd reloaded"

echo ""
echo -e "${BLUE}Main Bot Service Configuration:${NC}"

# Check if service was previously enabled
WAS_ENABLED=false
if systemctl is-enabled --quiet penguin-overlord.service 2>/dev/null; then
    WAS_ENABLED=true
    echo -e "${GREEN}✓${NC} Service already enabled"
else
    echo ""
    read -p "Enable penguin-overlord.service on boot? (Y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Nn]$ ]]; then
        systemctl enable penguin-overlord.service
        echo -e "${GREEN}✓${NC} Enabled"
        WAS_ENABLED=true
    else
        echo "Service will not auto-start on boot"
    fi
fi

# If we stopped the service earlier or it wasn't running, ask about starting
echo ""
read -p "Start/restart penguin-overlord.service now? (Y/n) " -n 1 -r
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
echo "Main Bot Commands:"
echo "  sudo systemctl start|stop|restart|status penguin-overlord"
echo "  sudo journalctl -u penguin-overlord -f"

if [ "$DEPLOY_NEWS_TIMERS" = true ]; then
    echo ""
    echo -e "${BLUE}Timer Commands:${NC}"
    echo "  sudo systemctl list-timers 'penguin-*'             # View all schedules"
    echo "  sudo systemctl status penguin-news-cybersecurity   # Check status"
    echo "  sudo journalctl -u penguin-solar -f                # View logs"
    echo "  sudo systemctl start penguin-news-cve.service      # Manual run"
    echo ""
    if [ "$DEPLOYMENT_MODE" = "2" ]; then
        echo -e "${YELLOW}All timers use Docker (each run starts fresh container, auto-cleanup)${NC}"
        echo ""
    fi
    echo -e "${YELLOW}Configure channels in Discord or .env:${NC}"
    echo "  /news set_channel cybersecurity #security-news"
    echo "  /news set_channel tech #tech-news"
    echo "  /news set_channel gaming #gaming-news"
    echo "  /news set_channel cve #security-alerts"
    echo "  SOLAR_POST_CHANNEL_ID=123456789"
    echo "  XKCD_POST_CHANNEL_ID=123456789"
    echo "  COMIC_POST_CHANNEL_ID=123456789"
    echo ""
    echo -e "${GREEN}News Schedule:${NC}"
    echo "  CVE:            Every 8 hours at :00       (00:00, 08:00, 16:00)"
    echo "  KEV:            Every 4 hours at :30       (00:30, 04:30, 08:30, 12:30, 16:30, 20:30)"
    echo "  Cybersecurity:  Every 3 hours at :01       (00:01, 03:01, 06:01, 09:01, 12:01, 15:01, 18:01, 21:01)"
    echo "  Tech:           Every 4 hours at :30       (00:30, 04:30, 08:30, 12:30, 16:30, 20:30)"
    echo "  Gaming:         Every 2 hours at :15       (every even hour + :15)"
    echo "  Apple/Google:   Every 3 hours at :45       (00:45, 03:45, 06:45, 09:45, 12:45, 15:45, 18:45, 21:45)"
    echo "  US Legislation: Every hour at :05          (hourly)"
    echo "  EU Legislation: Every hour at :10          (hourly)"
    echo "  UK Legislation: Every hour at :15          (hourly)"
    echo "  General News:   Every 2 hours at :20       (every even hour + :20)"
    echo ""
    echo -e "${GREEN}Background Tasks Schedule:${NC}"
    echo "  Solar/Propagation: Every 6 hours at :00    (00:00, 06:00, 12:00, 18:00)"
    echo "  XKCD:              Every 30 minutes         (:00 and :30)"
    echo "  Comics (Daily):    Once daily at 10:00 UTC (10:00)"
fi
