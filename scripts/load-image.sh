#!/bin/bash
# Load transferred Docker image on remote host (e.g., Raspberry Pi)
# Usage: ./load-image.sh [tarball-path]
#   Example: ./load-image.sh ~/penguin-overlord.tar.gz
#   Example: ./load-image.sh (will look for penguin-overlord.tar.gz in ~)

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

TARBALL="${1:-$HOME/penguin-overlord.tar.gz}"

echo -e "${BLUE}=== Penguin Overlord - Load Docker Image ===${NC}"
echo ""

# Check if tarball exists
if [ ! -f "$TARBALL" ]; then
    echo -e "${RED}ERROR: Tarball not found: $TARBALL${NC}"
    echo ""
    echo "Usage: $0 [tarball-path]"
    echo "  Default: ~/penguin-overlord.tar.gz"
    exit 1
fi

SIZE=$(du -h "$TARBALL" | cut -f1)
echo "Tarball: $TARBALL ($SIZE)"
echo ""

# Check if Docker is available
if ! command -v docker &> /dev/null; then
    echo -e "${RED}ERROR: Docker not found${NC}"
    exit 1
fi

# Load the image
echo -e "${BLUE}Loading Docker image...${NC}"
echo "This may take a few minutes..."
gunzip -c "$TARBALL" | docker load
echo -e "${GREEN}✓${NC} Image loaded"
echo ""

# Verify
echo -e "${BLUE}Verifying image...${NC}"
if docker images | grep -q "penguin-overlord"; then
    docker images | grep "penguin-overlord"
    echo -e "${GREEN}✓${NC} Image verified"
else
    echo -e "${YELLOW}WARNING: penguin-overlord image not found in docker images${NC}"
fi
echo ""

# Clean up tarball
read -p "Delete tarball? (Y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Nn]$ ]]; then
    rm "$TARBALL"
    echo -e "${GREEN}✓${NC} Tarball deleted"
else
    echo -e "${YELLOW}Tarball kept at: $TARBALL${NC}"
fi

echo ""
echo -e "${GREEN}=== Next Steps ===${NC}"
echo ""
echo "Run the installer:"
echo -e "  ${YELLOW}cd ~/penguin-overlord${NC}"
echo -e "  ${YELLOW}sudo bash scripts/install-systemd.sh${NC}"
echo ""
echo "When prompted, choose to use existing image."
echo ""
echo -e "${GREEN}Done!${NC}"
