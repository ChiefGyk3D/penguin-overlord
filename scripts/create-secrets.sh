#!/bin/bash
# Penguin Overlord - .env File Creator
# Creates .env file with Discord token

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo -e "${GREEN}Penguin Overlord - Environment Setup${NC}"
echo ""

if [ -f "$PROJECT_DIR/.env" ]; then
    echo -e "${YELLOW}WARNING: .env already exists!${NC}"
    read -p "Overwrite? (y/N) " -n 1 -r
    echo
    [[ ! $REPLY =~ ^[Yy]$ ]] && exit 0
fi

echo -e "${BLUE}Discord Token Setup${NC}"
echo ""
echo "Get your bot token from:"
echo "  https://discord.com/developers/applications"
echo ""
read -p "Enter Discord token: " DISCORD_TOKEN

if [ -z "$DISCORD_TOKEN" ]; then
    echo "Token cannot be empty"
    exit 1
fi

cat > "$PROJECT_DIR/.env" << EOF
# Penguin Overlord Discord Bot Configuration
# Created: $(date)

# Discord Bot Token (REQUIRED)
# Get from: https://discord.com/developers/applications
DISCORD_TOKEN=$DISCORD_TOKEN

# Optional: Doppler Integration
# DOPPLER_TOKEN=your_doppler_token_here

# Optional: Debug Mode (uncomment to enable)
# DEBUG=true
EOF

chmod 600 "$PROJECT_DIR/.env"

echo ""
echo -e "${GREEN}✓${NC} Created: $PROJECT_DIR/.env"
echo ""
echo "Next steps:"
echo "  1. Review .env file"
echo "  2. Run: sudo ./scripts/install-systemd.sh"
