#!/bin/bash
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

#
# Deploy News Timers - Setup systemd timers for optimized news fetching
#
# Usage: sudo ./deploy-news-timers.sh
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
SYSTEMD_DIR="/etc/systemd/system"
USER="penguin"
GROUP="penguin"

echo "📰 Deploying Optimized News System Timers"
echo "=========================================="
echo

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "❌ Please run as root (use sudo)"
    exit 1
fi

# Verify project directory
if [ ! -f "$PROJECT_ROOT/bot.py" ] && [ ! -f "$PROJECT_ROOT/penguin-overlord/bot.py" ]; then
    echo "❌ Cannot find bot.py - are you in the correct directory?"
    exit 1
fi

# Determine correct path
if [ -f "$PROJECT_ROOT/penguin-overlord/bot.py" ]; then
    WORK_DIR="$PROJECT_ROOT/penguin-overlord"
else
    WORK_DIR="$PROJECT_ROOT"
fi

echo "📁 Project directory: $WORK_DIR"
echo "👤 Running as user: $USER"
echo

# Create systemd service template
create_service() {
    local category=$1
    local service_file="$SYSTEMD_DIR/penguin-news-${category}.service"
    
    cat > "$service_file" << EOF
[Unit]
Description=Penguin Bot News Fetcher - ${category}
After=network.target

[Service]
Type=oneshot
User=$USER
Group=$GROUP
WorkingDirectory=$WORK_DIR
ExecStart=/usr/bin/python3 $PROJECT_ROOT/scripts/news_runner.py --category ${category}
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
    
    echo "✅ Created service: $service_file"
}

# Create systemd timer
create_timer() {
    local category=$1
    local calendar=$2
    local timer_file="$SYSTEMD_DIR/penguin-news-${category}.timer"
    
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
    
    echo "✅ Created timer: $timer_file"
}

# Deploy all timers
echo "🔧 Creating systemd units..."
echo

# CVE - Every 6 hours at :00
create_service "cve"
create_timer "cve" "*-*-* 00,06,12,18:00:00"

# Cybersecurity - Every 3 hours at :01
create_service "cybersecurity"
create_timer "cybersecurity" "*-*-* 00,03,06,09,12,15,18,21:01:00"

# Tech - Every 4 hours at :30
create_service "tech"
create_timer "tech" "*-*-* 00,04,08,12,16,20:30:00"

# Gaming - Every 2 hours at :15
create_service "gaming"
create_timer "gaming" "*-*-* */2:15:00"

# Apple/Google - Every 3 hours at :45
create_service "apple_google"
create_timer "apple_google" "*-*-* 00,03,06,09,12,15,18,21:45:00"

# Vendor Alerts - Every 30 minutes at :25 and :55
create_service "vendor_alerts"
create_timer "vendor_alerts" "*-*-* *:25,55:00"

echo
echo "🔄 Reloading systemd daemon..."
systemctl daemon-reload

echo
echo "📋 Timer Status:"
echo "----------------"
systemctl list-timers penguin-news-* --no-pager

echo
echo "🚀 To enable timers on boot:"
echo "   systemctl enable penguin-news-cve.timer"
echo "   systemctl enable penguin-news-cybersecurity.timer"
echo "   systemctl enable penguin-news-tech.timer"
echo "   systemctl enable penguin-news-gaming.timer"
echo "   systemctl enable penguin-news-apple_google.timer"
echo "   systemctl enable penguin-news-vendor_alerts.timer"
echo
echo "▶️  To start timers now:"
echo "   systemctl start penguin-news-cve.timer"
echo "   systemctl start penguin-news-cybersecurity.timer"
echo "   systemctl start penguin-news-tech.timer"
echo "   systemctl start penguin-news-gaming.timer"
echo "   systemctl start penguin-news-apple_google.timer"
echo "   systemctl start penguin-news-vendor_alerts.timer"
echo
echo "📊 To view logs:"
echo "   journalctl -u penguin-news-cve -f"
echo "   journalctl -u penguin-news-cybersecurity -f"
echo
echo "🧪 To manually trigger a run:"
echo "   systemctl start penguin-news-cve.service"
echo

# Ask if user wants to enable and start now
read -p "Enable and start all timers now? [y/N] " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "🚀 Enabling and starting timers..."
    
    for category in cve cybersecurity tech gaming apple_google vendor_alerts; do
        systemctl enable "penguin-news-${category}.timer"
        systemctl start "penguin-news-${category}.timer"
        echo "✅ Started penguin-news-${category}.timer"
    done
    
    echo
    echo "✨ All timers are now active!"
    echo
    systemctl list-timers penguin-news-* --no-pager
else
    echo "⏭️  Skipped auto-start. Enable timers manually when ready."
fi

echo
echo "✅ Deployment complete!"
echo
echo "💡 Pro Tips:"
echo "   - Timers are staggered to distribute load"
echo "   - ETag caching reduces bandwidth by ~99%"
echo "   - Each run uses <150MB RAM and exits"
echo "   - Logs auto-rotate in systemd journal"
echo
