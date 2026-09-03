#!/bin/bash
# Penguin Overlord - systemd Service Installation Script
# Installs Penguin Overlord Discord Bot as a systemd service

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
ACTUAL_USER="$USER"
ACTUAL_USER_UID=$(id -u)
ACTUAL_USER_GID=$(id -g)

# systemd OnCalendar expressions for every timer this script writes. The
# end-of-run summary is generated from these, so it cannot drift from the
# units. tests/unit/test_news_config_example.py checks the news ones against
# data/news_config.example.json.
CVE_CALENDAR="*-*-* 00,08,16:00:00"
CYBERSECURITY_CALENDAR="*-*-* 00,03,06,09,12,15,18,21:01:00"
TECH_CALENDAR="*-*-* 00,04,08,12,16,20:30:00"
GAMING_CALENDAR="*-*-* 00,02,04,06,08,10,12,14,16,18,20,22:15:00"
APPLE_GOOGLE_CALENDAR="*-*-* 00,03,06,09,12,15,18,21:45:00"
US_LEGISLATION_CALENDAR="*-*-* *:05:00"
EU_LEGISLATION_CALENDAR="*-*-* *:10:00"
UK_LEGISLATION_CALENDAR="*-*-* *:15:00"
GENERAL_NEWS_CALENDAR="*-*-* 00,02,04,06,08,10,12,14,16,18,20,22:20:00"
VENDOR_ALERTS_CALENDAR="*-*-* *:25,55:00"
KEV_CALENDAR="*-*-* 00,04,08,12,16,20:00:00"
SOLAR_CALENDAR="*-*-* *:00,30:00"
XKCD_CALENDAR="*-*-* *:00,30:00"
COMICS_CALENDAR="*-*-* 10:00:00"

# Turn an OnCalendar expression into a sentence for the summary.
#   "*-*-* 00,08,16:00:00" -> "every 8 hours at :00 (00:00, 08:00, 16:00)"
#   "*-*-* *:25,55:00"     -> "every hour at :25 and :55"
#   "*-*-* 10:00:00"       -> "daily at 10:00 UTC"
describe_calendar() {
    local cal=$1
    local time=${cal#* }
    local hours=${time%%:*}
    local minutes=${time#*:}
    minutes=${minutes%%:*}

    if [ "$hours" = "*" ]; then
        echo "every hour at :${minutes//,/ and :}"
        return
    fi

    local -a hour_list run_list
    IFS=',' read -r -a hour_list <<< "$hours"
    if [ "${#hour_list[@]}" -eq 1 ]; then
        echo "daily at ${hour_list[0]}:${minutes} UTC"
        return
    fi
    for h in "${hour_list[@]}"; do
        run_list+=("$h:$minutes")
    done
    local runs
    runs=$(printf '%s, ' "${run_list[@]}")
    echo "every $((24 / ${#hour_list[@]})) hours at :${minutes} (${runs%, })"
}

echo -e "${GREEN}Penguin Overlord - systemd Installer${NC}"
echo "Project: $PROJECT_DIR"
echo "User: $ACTUAL_USER"
echo ""

[ ! -f "$PROJECT_DIR/penguin-overlord/bot.py" ] && echo -e "${RED}ERROR: bot.py not found${NC}" && exit 1
[ ! -d "$PROJECT_DIR/penguin-overlord/cogs" ] && echo -e "${RED}ERROR: cogs/ not found${NC}" && exit 1

# Check if service already exists and is running
SERVICE_EXISTS=false
if sudo systemctl list-units --full --all | grep -q "penguin-overlord.service"; then
    SERVICE_EXISTS=true
    echo -e "${YELLOW}Service already exists${NC}"

    if sudo systemctl is-active --quiet penguin-overlord.service; then
        echo -e "${YELLOW}Bot is currently running${NC}"
        read -p "Stop bot before reinstalling? (Y/n) " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Nn]$ ]]; then
            echo "Stopping penguin-overlord service..."
            sudo systemctl stop penguin-overlord.service
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

IS_DOCKER=false
[ "$DEPLOYMENT_MODE" = "2" ] && IS_DOCKER=true

# Ask about news system optimization
echo ""
echo -e "${BLUE}News System Configuration:${NC}"
echo "The bot includes news aggregation for 220+ sources across 11 categories."
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

# Ask about background task timers (solar, xkcd, comics)
echo ""
echo -e "${BLUE}Background Task Configuration:${NC}"
echo "The bot includes auto-posting for Solar/Propagation, XKCD, and Comics."
echo ""
echo "Deploy as external systemd timers? (Recommended for reliability)"
echo -e "  ${GREEN}Yes${NC} - Systemd timers (reliable, independent of bot restarts)"
echo -e "  ${GREEN}No${NC}  - Internal schedulers (simpler, but can miss posts on restart)"
echo ""
read -p "Deploy background task timers? (Y/n): " -n 1 -r BACKGROUND_MODE
echo ""
BACKGROUND_MODE="${BACKGROUND_MODE:-Y}"

if [[ $BACKGROUND_MODE =~ ^[Yy]$ ]]; then
    echo -e "${GREEN}✓${NC} Will deploy background task timers"
    DEPLOY_BACKGROUND_TIMERS=true
else
    echo -e "${GREEN}✓${NC} Background tasks will use internal schedulers"
    DEPLOY_BACKGROUND_TIMERS=false
fi

if [ ! -f "$PROJECT_DIR/.env" ]; then
    echo -e "${YELLOW}WARNING: .env not found!${NC}"
    echo "Create .env with DISCORD_BOT_TOKEN before starting"
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
    
    "$PROJECT_DIR/venv/bin/python" -c "import discord" &> /dev/null || { echo -e "${RED}discord.py failed${NC}"; exit 1; }
    echo -e "${GREEN}✓${NC} discord.py verified"
    
    sudo tee /etc/systemd/system/penguin-overlord.service > /dev/null << EOF
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
EnvironmentFile=$PROJECT_DIR/.env
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
    
    command -v docker &> /dev/null || { echo -e "${RED}Docker not installed${NC}"; exit 1; }
    echo -e "${GREEN}✓${NC} Docker: $(docker --version)"

    if ! groups "$ACTUAL_USER" | grep -q docker; then
        sudo usermod -aG docker "$ACTUAL_USER"
        echo -e "${GREEN}✓${NC} Added $ACTUAL_USER to the docker group"
        echo -e "${YELLOW}The new group takes effect at your next login. This run falls back to 'sudo docker';${NC}"
        echo -e "${YELLOW}log out and back in before running docker commands by hand.${NC}"
    fi

    DOCKER_CMD=$(groups | grep -q docker && echo "docker" || echo "sudo docker")
    IMAGE_NAME="penguin-overlord"
    
    if $DOCKER_CMD images --format "{{.Repository}}" | grep -q "^${IMAGE_NAME}$"; then
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
        # Stop and remove ALL penguin containers (main bot, timers, news services)
        echo "Cleaning up existing containers..."
        for container in $($DOCKER_CMD ps -a --format '{{.Names}}' | grep '^penguin-'); do
            echo "  Removing container: $container"
            $DOCKER_CMD stop "$container" 2>/dev/null || true
            $DOCKER_CMD rm -f "$container" 2>/dev/null || true
        done
        
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
    
    sudo tee /etc/systemd/system/penguin-overlord.service > /dev/null << EOF
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
ExecStart=/usr/bin/docker run -d --name penguin-overlord --restart unless-stopped --log-driver json-file --log-opt max-size=20m --log-opt max-file=5 --env-file $PROJECT_DIR/.env -v $PROJECT_DIR/events:/app/events:ro -v $PROJECT_DIR/data:/app/data $IMAGE_NAME
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
    # The bot container runs as root, so files it wrote are root-owned.
    sudo chown -R "$ACTUAL_USER:$ACTUAL_USER" "$PROJECT_DIR/data"
    sudo chmod -R 755 "$PROJECT_DIR/data"
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
            sudo tee "$service_file" > /dev/null << EOF
[Unit]
Description=Penguin Bot News Fetcher - ${category}
After=network.target

[Service]
Type=oneshot
User=$ACTUAL_USER
Group=$ACTUAL_USER
WorkingDirectory=$PROJECT_DIR/penguin-overlord
Environment="PATH=$PROJECT_DIR/venv/bin:/usr/local/bin:/usr/bin:/bin"
EnvironmentFile=$PROJECT_DIR/.env
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
            sudo tee "$service_file" > /dev/null << EOF
[Unit]
Description=Penguin Bot News Fetcher - ${category} (Docker)
After=docker.service network.target
Requires=docker.service

[Service]
Type=oneshot
User=$ACTUAL_USER
Group=$ACTUAL_USER
WorkingDirectory=$PROJECT_DIR
ExecStart=/usr/bin/docker run --rm --name penguin-news-${category} --user $ACTUAL_USER_UID:$ACTUAL_USER_GID --env-file $PROJECT_DIR/.env -v $PROJECT_DIR/data:/app/data $IMAGE_NAME python3 /app/penguin-overlord/news_runner.py --category ${category}
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
        
        sudo tee "$timer_file" > /dev/null << EOF
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
    # KEV is not here: it runs from kev_runner.py as a background timer below.
    create_news_service "cve"
    create_news_timer "cve" "$CVE_CALENDAR"

    create_news_service "cybersecurity"
    create_news_timer "cybersecurity" "$CYBERSECURITY_CALENDAR"

    create_news_service "tech"
    create_news_timer "tech" "$TECH_CALENDAR"

    create_news_service "gaming"
    create_news_timer "gaming" "$GAMING_CALENDAR"

    create_news_service "apple_google"
    create_news_timer "apple_google" "$APPLE_GOOGLE_CALENDAR"

    create_news_service "us_legislation"
    create_news_timer "us_legislation" "$US_LEGISLATION_CALENDAR"

    create_news_service "eu_legislation"
    create_news_timer "eu_legislation" "$EU_LEGISLATION_CALENDAR"

    create_news_service "uk_legislation"
    create_news_timer "uk_legislation" "$UK_LEGISLATION_CALENDAR"

    create_news_service "general_news"
    create_news_timer "general_news" "$GENERAL_NEWS_CALENDAR"

    create_news_service "vendor_alerts"
    create_news_timer "vendor_alerts" "$VENDOR_ALERTS_CALENDAR"

    echo -e "${GREEN}✓${NC} All news timers created"

    # Enable and start news timers
    echo ""
    read -p "Enable and start news timers? (Y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Nn]$ ]]; then
        # News timers
        for category in cve cybersecurity tech gaming apple_google us_legislation eu_legislation uk_legislation general_news vendor_alerts; do
            sudo systemctl enable penguin-news-${category}.timer 2>/dev/null || true
            sudo systemctl start penguin-news-${category}.timer 2>/dev/null || true
        done
        echo -e "${GREEN}✓${NC} News timers enabled and started"
    else
        echo "Skipping news timer activation"
    fi
fi

# ==============================================================================
# BACKGROUND TASK TIMERS (solar, xkcd, comics)
# ==============================================================================
if [ "$DEPLOY_BACKGROUND_TIMERS" = true ]; then
    echo ""
    echo -e "${BLUE}Creating Background Task Timers...${NC}"

    # Function to create background task service
    create_background_service() {
        local task_name=$1
        local script_name=$2
        local service_file="/etc/systemd/system/penguin-${task_name}.service"
        
        if [ "$DEPLOYMENT_MODE" = "1" ]; then
            # Python deployment
            sudo tee "$service_file" > /dev/null << EOF
[Unit]
Description=Penguin Bot ${task_name^} Poster
After=network.target

[Service]
Type=oneshot
User=$ACTUAL_USER
Group=$ACTUAL_USER
WorkingDirectory=$PROJECT_DIR/penguin-overlord
Environment="PATH=$PROJECT_DIR/venv/bin:/usr/local/bin:/usr/bin:/bin"
EnvironmentFile=$PROJECT_DIR/.env
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
            sudo tee "$service_file" > /dev/null << EOF
[Unit]
Description=Penguin Bot ${task_name^} Poster (Docker)
After=docker.service network.target
Requires=docker.service

[Service]
Type=oneshot
User=$ACTUAL_USER
Group=$ACTUAL_USER
WorkingDirectory=$PROJECT_DIR
ExecStart=/usr/bin/docker run --rm --name penguin-${task_name} --user $ACTUAL_USER_UID:$ACTUAL_USER_GID --env-file $PROJECT_DIR/.env -v $PROJECT_DIR/data:/app/data $IMAGE_NAME python3 /app/penguin-overlord/${script_name}
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
        
        sudo tee "$timer_file" > /dev/null << EOF
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
    
    # KEV (CISA Known Exploited Vulnerabilities)
    create_background_service "kev" "kev_runner.py"
    create_background_timer "kev" "$KEV_CALENDAR"

    # Solar/propagation report (includes X-ray, D-RAP and Aurora charts)
    create_background_service "solar" "solar_runner.py"
    create_background_timer "solar" "$SOLAR_CALENDAR"

    # XKCD
    create_background_service "xkcd" "xkcd_runner.py"
    create_background_timer "xkcd" "$XKCD_CALENDAR"

    # Daily comics
    create_background_service "comics" "comics_runner.py"
    create_background_timer "comics" "$COMICS_CALENDAR"
    
    echo -e "${GREEN}✓${NC} Background task timers created"
    
    # Enable and start background task timers
    echo ""
    read -p "Enable and start background task timers (KEV, solar, xkcd, comics)? (Y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Nn]$ ]]; then
        for task in kev solar xkcd comics; do
            sudo systemctl enable penguin-${task}.timer 2>/dev/null || true
            sudo systemctl start penguin-${task}.timer 2>/dev/null || true
        done
        echo -e "${GREEN}✓${NC} Background task timers enabled and started"
    else
        echo "Skipping background task timer activation"
    fi
fi

sudo systemctl daemon-reload
echo -e "${GREEN}✓${NC} systemd reloaded"

echo ""
echo -e "${BLUE}Main Bot Service Configuration:${NC}"

# Check if service was previously enabled
WAS_ENABLED=false
if sudo systemctl is-enabled --quiet penguin-overlord.service 2>/dev/null; then
    WAS_ENABLED=true
    echo -e "${GREEN}✓${NC} Service already enabled"
else
    echo ""
    read -p "Enable penguin-overlord.service on boot? (Y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Nn]$ ]]; then
        sudo systemctl enable penguin-overlord.service
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
    sudo systemctl restart penguin-overlord.service
    sleep 3
    
    if sudo systemctl is-active --quiet penguin-overlord.service; then
        echo -e "${GREEN}✓${NC} Service is running!"
        
        # Show last few log lines
        echo ""
        echo "Recent logs:"
        sudo journalctl -u penguin-overlord -n 5 --no-pager
    else
        echo -e "${RED}✗ Service failed to start${NC}"
        echo ""
        echo "Error details:"
        sudo systemctl status penguin-overlord.service --no-pager | tail -10
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

if [ "$DEPLOY_NEWS_TIMERS" = true ] || [ "$DEPLOY_BACKGROUND_TIMERS" = true ]; then
    echo ""
    echo -e "${BLUE}Timer Commands:${NC}"
    echo "  sudo systemctl list-timers 'penguin-*'             # View all schedules"
    if [ "$DEPLOY_BACKGROUND_TIMERS" = true ]; then
        echo "  sudo systemctl status penguin-solar                 # Check status"
        echo "  sudo journalctl -u penguin-solar -f                 # View logs"
        echo "  sudo systemctl start penguin-solar.service          # Manual run"
    fi
    if [ "$DEPLOY_NEWS_TIMERS" = true ]; then
        echo "  sudo systemctl status penguin-news-cybersecurity   # Check status"
        echo "  sudo journalctl -u penguin-news-tech -f             # View logs"
        echo "  sudo systemctl start penguin-news-cve.service       # Manual run"
    fi

    if [ "$DEPLOYMENT_MODE" = "2" ]; then
        echo ""
        echo -e "${YELLOW}Timers use Docker (each run starts fresh container, auto-cleanup)${NC}"
    fi

    echo ""
    echo -e "${YELLOW}Configure channels in Discord or .env:${NC}"
    if [ "$DEPLOY_BACKGROUND_TIMERS" = true ]; then
        echo "  SOLAR_POST_CHANNEL_ID=123456789"
        echo "  XKCD_POST_CHANNEL_ID=123456789"
        echo "  COMIC_POST_CHANNEL_ID=123456789"
    fi
    if [ "$DEPLOY_NEWS_TIMERS" = true ]; then
        echo "  /news set_channel cybersecurity #security-news"
        echo "  /news set_channel tech #tech-news"
        echo "  /news set_channel gaming #gaming-news"
        echo "  /news set_channel cve #security-alerts"
        echo "  /news set_channel vendor_alerts #vendor-alerts"
    fi
fi

# Schedules below are rendered from the same OnCalendar strings written into
# the timer units, so what is printed is what systemd will do.
print_schedule() {
    printf '  %-19s %s\n' "$1:" "$(describe_calendar "$2")"
}

if [ "$DEPLOY_BACKGROUND_TIMERS" = true ]; then
    echo ""
    echo -e "${GREEN}Background Tasks Schedule:${NC}"
    print_schedule "KEV"               "$KEV_CALENDAR"
    print_schedule "Solar/Propagation" "$SOLAR_CALENDAR"
    print_schedule "XKCD"              "$XKCD_CALENDAR"
    print_schedule "Comics"            "$COMICS_CALENDAR"
fi

if [ "$DEPLOY_NEWS_TIMERS" = true ]; then
    echo ""
    echo -e "${GREEN}News Schedule:${NC}"
    print_schedule "CVE"            "$CVE_CALENDAR"
    print_schedule "Cybersecurity"  "$CYBERSECURITY_CALENDAR"
    print_schedule "Tech"           "$TECH_CALENDAR"
    print_schedule "Gaming"         "$GAMING_CALENDAR"
    print_schedule "Apple/Google"   "$APPLE_GOOGLE_CALENDAR"
    print_schedule "US Legislation" "$US_LEGISLATION_CALENDAR"
    print_schedule "EU Legislation" "$EU_LEGISLATION_CALENDAR"
    print_schedule "UK Legislation" "$UK_LEGISLATION_CALENDAR"
    print_schedule "General News"   "$GENERAL_NEWS_CALENDAR"
    print_schedule "Vendor Alerts"  "$VENDOR_ALERTS_CALENDAR"
fi

# Fresh pull option - run services immediately to populate channels
echo ""
echo -e "${CYAN}═══════════════════════════════════════════════════════════════${NC}"
echo -e "${CYAN}                    INITIAL FEED POPULATION${NC}"
echo -e "${CYAN}═══════════════════════════════════════════════════════════════${NC}"
echo ""
echo "Would you like to perform an initial fresh pull to populate your channels?"
echo "This will run each enabled service once immediately."
echo ""
read -p "Perform fresh pull? (Y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Nn]$ ]]; then
    echo ""
    
    # Ask about cache clearing
    echo "Clear all existing cache and state files for a completely fresh start?"
    echo "This will remove all stored feed GUIDs, posted CVEs, and last-posted timestamps."
    echo ""
    read -p "Clear cache? (y/N) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo ""
        echo -e "${YELLOW}Clearing cache and state files...${NC}"
        if [ -d "$PROJECT_DIR/data" ]; then
            rm -f "$PROJECT_DIR/data/feed_cache_"*.json
            rm -f "$PROJECT_DIR/data/"*"_state.json"
            echo -e "${GREEN}✓${NC} Cache cleared"
        else
            echo -e "${YELLOW}No data directory found (will be created on first run)${NC}"
        fi
    else
        echo -e "${YELLOW}Keeping existing cache${NC}"
    fi
    
    echo ""
    read -p "Run all feeds automatically (A) or choose individually (I)? (A/i) " -n 1 -r
    echo
    
    if [[ $REPLY =~ ^[Ii]$ ]]; then
        # Individual selection mode
        echo ""
        echo -e "${YELLOW}Individually select feeds to populate:${NC}"
        echo ""
        
        # Background tasks
        if [ "$DEPLOY_BACKGROUND_TIMERS" = true ]; then
            echo -e "${CYAN}Background Tasks:${NC}"
            
            read -p "  KEV (CISA Known Exploited Vulnerabilities)? (Y/n) " -n 1 -r
            echo
            if [[ ! $REPLY =~ ^[Nn]$ ]]; then
                echo -e "    ${GREEN}Running KEV...${NC}"
                sudo systemctl start penguin-kev.service
                sleep 2
            fi
            
            read -p "  Solar/Propagation Report? (Y/n) " -n 1 -r
            echo
            if [[ ! $REPLY =~ ^[Nn]$ ]]; then
                echo -e "    ${GREEN}Running Solar...${NC}"
                sudo systemctl start penguin-solar.service
                sleep 2
            fi
            
            read -p "  XKCD Comic? (Y/n) " -n 1 -r
            echo
            if [[ ! $REPLY =~ ^[Nn]$ ]]; then
                echo -e "    ${GREEN}Running XKCD...${NC}"
                sudo systemctl start penguin-xkcd.service
                sleep 2
            fi
            
            read -p "  Daily Comics? (Y/n) " -n 1 -r
            echo
            if [[ ! $REPLY =~ ^[Nn]$ ]]; then
                echo -e "    ${GREEN}Running Comics...${NC}"
                sudo systemctl start penguin-comics.service
                sleep 2
            fi
        fi
        
        # News categories
        if [ "$DEPLOY_NEWS_TIMERS" = true ]; then
            echo ""
            echo -e "${CYAN}News Categories:${NC}"
            
            read -p "  CVE (Common Vulnerabilities and Exposures)? (Y/n) " -n 1 -r
            echo
            if [[ ! $REPLY =~ ^[Nn]$ ]]; then
                echo -e "    ${GREEN}Running CVE...${NC}"
                sudo systemctl start penguin-news-cve.service
                sleep 2
            fi
            
            read -p "  Cybersecurity News? (Y/n) " -n 1 -r
            echo
            if [[ ! $REPLY =~ ^[Nn]$ ]]; then
                echo -e "    ${GREEN}Running Cybersecurity...${NC}"
                sudo systemctl start penguin-news-cybersecurity.service
                sleep 2
            fi
            
            read -p "  Tech News? (Y/n) " -n 1 -r
            echo
            if [[ ! $REPLY =~ ^[Nn]$ ]]; then
                echo -e "    ${GREEN}Running Tech...${NC}"
                sudo systemctl start penguin-news-tech.service
                sleep 2
            fi
            
            read -p "  Gaming News? (Y/n) " -n 1 -r
            echo
            if [[ ! $REPLY =~ ^[Nn]$ ]]; then
                echo -e "    ${GREEN}Running Gaming...${NC}"
                sudo systemctl start penguin-news-gaming.service
                sleep 2
            fi
            
            read -p "  Apple/Google News? (Y/n) " -n 1 -r
            echo
            if [[ ! $REPLY =~ ^[Nn]$ ]]; then
                echo -e "    ${GREEN}Running Apple/Google...${NC}"
                sudo systemctl start penguin-news-apple_google.service
                sleep 2
            fi
            
            read -p "  US Legislation? (Y/n) " -n 1 -r
            echo
            if [[ ! $REPLY =~ ^[Nn]$ ]]; then
                echo -e "    ${GREEN}Running US Legislation...${NC}"
                sudo systemctl start penguin-news-us_legislation.service
                sleep 2
            fi
            
            read -p "  EU Legislation? (Y/n) " -n 1 -r
            echo
            if [[ ! $REPLY =~ ^[Nn]$ ]]; then
                echo -e "    ${GREEN}Running EU Legislation...${NC}"
                sudo systemctl start penguin-news-eu_legislation.service
                sleep 2
            fi
            
            read -p "  UK Legislation? (Y/n) " -n 1 -r
            echo
            if [[ ! $REPLY =~ ^[Nn]$ ]]; then
                echo -e "    ${GREEN}Running UK Legislation...${NC}"
                sudo systemctl start penguin-news-uk_legislation.service
                sleep 2
            fi
            
            read -p "  General News? (Y/n) " -n 1 -r
            echo
            if [[ ! $REPLY =~ ^[Nn]$ ]]; then
                echo -e "    ${GREEN}Running General News...${NC}"
                sudo systemctl start penguin-news-general_news.service
                sleep 2
            fi
            
            read -p "  Vendor Service Alerts? (Y/n) " -n 1 -r
            echo
            if [[ ! $REPLY =~ ^[Nn]$ ]]; then
                echo -e "    ${GREEN}Running Vendor Alerts...${NC}"
                sudo systemctl start penguin-news-vendor_alerts.service
                sleep 2
            fi
        fi
        
    else
        # Run all mode
        echo ""
        echo -e "${GREEN}Running all enabled feeds...${NC}"
        echo ""
        
        if [ "$DEPLOY_BACKGROUND_TIMERS" = true ]; then
            echo -e "${CYAN}Starting background tasks...${NC}"
            sudo systemctl start penguin-kev.service
            sudo systemctl start penguin-solar.service
            sudo systemctl start penguin-xkcd.service
            sudo systemctl start penguin-comics.service
            sleep 3
        fi
        
        if [ "$DEPLOY_NEWS_TIMERS" = true ]; then
            echo -e "${CYAN}Starting news feeds...${NC}"
            sudo systemctl start penguin-news-cve.service
            sudo systemctl start penguin-news-cybersecurity.service
            sudo systemctl start penguin-news-tech.service
            sudo systemctl start penguin-news-gaming.service
            sudo systemctl start penguin-news-apple_google.service
            sudo systemctl start penguin-news-us_legislation.service
            sudo systemctl start penguin-news-eu_legislation.service
            sudo systemctl start penguin-news-uk_legislation.service
            sudo systemctl start penguin-news-general_news.service
            sudo systemctl start penguin-news-vendor_alerts.service
            sleep 3
        fi
    fi
    
    echo ""
    echo -e "${GREEN}✓${NC} Fresh pull initiated!"
    echo ""
    echo -e "${YELLOW}Monitor progress with:${NC}"
    echo "  sudo journalctl -f -u 'penguin-*'"
    echo ""
    echo -e "${YELLOW}Or check individual services:${NC}"
    echo "  sudo systemctl status penguin-kev.service"
    echo "  sudo systemctl status penguin-news-cybersecurity.service"
    echo ""
    echo -e "${YELLOW}View recent logs:${NC}"
    echo "  sudo journalctl -u penguin-kev -n 50"
    echo "  sudo journalctl -u penguin-news-cybersecurity -n 50"
else
    echo ""
    echo "Skipping fresh pull. Services will run according to their timer schedules."
fi

