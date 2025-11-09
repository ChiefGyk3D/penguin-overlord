#!/bin/bash
# Build Docker image locally and transfer to remote host (e.g., Raspberry Pi)
# Usage: ./build-and-transfer.sh [remote-host] [remote-user]
#   Example: ./build-and-transfer.sh 192.168.1.100 chiefgyk3d
#   Example: ./build-and-transfer.sh pi.local pi

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
IMAGE_NAME="penguin-overlord"
TARBALL="penguin-overlord.tar.gz"

# Parse arguments
REMOTE_HOST="${1}"
REMOTE_USER="${2:-$USER}"

if [ -z "$REMOTE_HOST" ]; then
    echo -e "${YELLOW}Usage: $0 <remote-host> [remote-user]${NC}"
    echo ""
    echo "Examples:"
    echo "  $0 192.168.1.100 chiefgyk3d"
    echo "  $0 pi.local pi"
    echo "  $0 raspberrypi.local"
    exit 1
fi

echo -e "${BLUE}=== Penguin Overlord - Build and Transfer ===${NC}"
echo "Project: $PROJECT_DIR"
echo "Target: $REMOTE_USER@$REMOTE_HOST"
echo ""

# Check if Docker is available
if ! command -v docker &> /dev/null; then
    echo -e "${RED}ERROR: Docker not found${NC}"
    exit 1
fi

# Check if Dockerfile exists
if [ ! -f "$PROJECT_DIR/Dockerfile" ]; then
    echo -e "${RED}ERROR: Dockerfile not found at $PROJECT_DIR/Dockerfile${NC}"
    exit 1
fi

# Build the image
echo -e "${BLUE}Step 1: Building Docker image...${NC}"
cd "$PROJECT_DIR"
docker build --no-cache --pull -t $IMAGE_NAME .
echo -e "${GREEN}✓${NC} Build complete"
echo ""

# Save to tarball
echo -e "${BLUE}Step 2: Saving image to tarball...${NC}"
echo "This may take a few minutes..."
docker save $IMAGE_NAME:latest | gzip > "$PROJECT_DIR/$TARBALL"
SIZE=$(du -h "$PROJECT_DIR/$TARBALL" | cut -f1)
echo -e "${GREEN}✓${NC} Saved to $TARBALL ($SIZE)"
echo ""

# Transfer to remote host
echo -e "${BLUE}Step 3: Transferring to $REMOTE_HOST...${NC}"
scp "$PROJECT_DIR/$TARBALL" "$REMOTE_USER@$REMOTE_HOST:~/"
echo -e "${GREEN}✓${NC} Transfer complete"
echo ""

# Generate load commands
echo -e "${GREEN}=== Next Steps on Remote Host ===${NC}"
echo ""
echo "SSH to your remote host:"
echo -e "  ${YELLOW}ssh $REMOTE_USER@$REMOTE_HOST${NC}"
echo ""
echo "Then load the image:"
echo -e "  ${YELLOW}gunzip -c ~/$TARBALL | docker load${NC}"
echo ""
echo "Verify the image:"
echo -e "  ${YELLOW}docker images | grep penguin-overlord${NC}"
echo ""
echo "Run the installer (it will detect and use existing image):"
echo -e "  ${YELLOW}cd ~/penguin-overlord${NC}"
echo -e "  ${YELLOW}sudo bash scripts/install-systemd.sh${NC}"
echo ""

# Ask if we should clean up local tarball
read -p "Delete local tarball? (Y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Nn]$ ]]; then
    rm "$PROJECT_DIR/$TARBALL"
    echo -e "${GREEN}✓${NC} Local tarball deleted"
else
    echo -e "${YELLOW}Tarball kept at: $PROJECT_DIR/$TARBALL${NC}"
fi

echo ""
echo -e "${GREEN}Done!${NC}"
