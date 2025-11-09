# Build and Transfer Workflow

Quick guide for building Docker images on a powerful dev machine and transferring to Raspberry Pi for testing.

## Why Use This?

- **Save Time**: Building on Pi takes 15-30 minutes, transferring takes 2-5 minutes
- **Dev Workflow**: Test code on Pi without waiting for slow ARM builds
- **Network Efficient**: Transfer compressed image once instead of pulling dependencies

## Quick Start

### On Your Dev Machine

```bash
# Build and transfer in one command
./scripts/build-and-transfer.sh <pi-ip-or-hostname> <username>

# Examples:
./scripts/build-and-transfer.sh 192.168.1.100 chiefgyk3d
./scripts/build-and-transfer.sh pi.local pi
./scripts/build-and-transfer.sh raspberrypi.local
```

### On Your Raspberry Pi

```bash
# After the transfer completes, load the image
./scripts/load-image.sh

# Or specify path
./scripts/load-image.sh ~/penguin-overlord.tar.gz

# Then install/update the bot
sudo bash scripts/install-systemd.sh
```

## Detailed Steps

### 1. Build on Dev Machine

The `build-and-transfer.sh` script will:
1. Build fresh Docker image with `--no-cache`
2. Save image to compressed tarball (~200-300MB)
3. Transfer via SCP to remote host
4. Optionally clean up local tarball

```bash
cd penguin-overlord
./scripts/build-and-transfer.sh 192.168.1.100 chiefgyk3d
```

**Output:**
```
=== Penguin Overlord - Build and Transfer ===
Project: /home/user/penguin-overlord
Target: chiefgyk3d@192.168.1.100

Step 1: Building Docker image...
[build output]
✓ Build complete

Step 2: Saving image to tarball...
✓ Saved to penguin-overlord.tar.gz (287M)

Step 3: Transferring to 192.168.1.100...
✓ Transfer complete
```

### 2. Load on Raspberry Pi

The `load-image.sh` script will:
1. Load the Docker image from tarball
2. Verify image is available
3. Optionally clean up tarball

```bash
ssh chiefgyk3d@192.168.1.100
cd penguin-overlord
./scripts/load-image.sh
```

**Output:**
```
=== Penguin Overlord - Load Docker Image ===
Tarball: /home/chiefgyk3d/penguin-overlord.tar.gz (287M)

Loading Docker image...
✓ Image loaded

Verifying image...
penguin-overlord    latest    abc123    2 hours ago    1.2GB
✓ Image verified
```

### 3. Install/Update Bot

```bash
sudo bash scripts/install-systemd.sh
```

When prompted about the image:
```
Image exists
Use existing? (Y/n) Y  # <-- Choose Yes
```

## Manual Method

If you prefer manual control:

**On dev machine:**
```bash
# Build
docker build --no-cache -t penguin-overlord .

# Save and compress
docker save penguin-overlord:latest | gzip > penguin-overlord.tar.gz

# Transfer
scp penguin-overlord.tar.gz chiefgyk3d@192.168.1.100:~/
```

**On Raspberry Pi:**
```bash
# Load
gunzip -c ~/penguin-overlord.tar.gz | docker load

# Verify
docker images | grep penguin-overlord

# Install
sudo bash scripts/install-systemd.sh
```

## Troubleshooting

### SSH Connection Issues

```bash
# Test SSH first
ssh chiefgyk3d@192.168.1.100

# If using hostname instead of IP, ensure it resolves
ping pi.local
```

### Transfer Fails

```bash
# Check available space on Pi
ssh chiefgyk3d@192.168.1.100 df -h

# The tarball is ~300MB, loaded image is ~1.2GB
# Ensure you have at least 2GB free space
```

### Image Not Loading

```bash
# Check tarball integrity
gzip -t ~/penguin-overlord.tar.gz

# Re-transfer if corrupted
```

### Docker Permission Denied

```bash
# Add user to docker group (on Pi)
sudo usermod -aG docker $USER

# Logout and login again
```

## Tips

- **First time**: Use `install-systemd.sh` to set everything up
- **Updates**: Just rebuild and transfer, then reinstall
- **Testing**: Transfer image, then make code changes on Pi directly for quick iteration
- **Cleanup**: Both scripts offer to delete tarballs after use

## Alternative: Multi-arch Build

For regular deployments, consider setting up multi-arch builds:

```bash
# One-time setup
docker buildx create --use

# Build for ARM64 and push to registry
docker buildx build --platform linux/arm64 \
  -t ghcr.io/chiefgyk3d/penguin-overlord:test --push .
```

Then on Pi:
```bash
docker pull ghcr.io/chiefgyk3d/penguin-overlord:test
docker tag ghcr.io/chiefgyk3d/penguin-overlord:test penguin-overlord:latest
```

## See Also

- [Production Deployment](../deployment/PRODUCTION.md)
- [Systemd Setup](SYSTEMD.md)
- [Docker Documentation](https://docs.docker.com/)
