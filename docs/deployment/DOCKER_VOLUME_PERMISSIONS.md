# Docker Volume Permissions Fix

## Issue
If you see these errors in your Docker logs:

```
PermissionError: [Errno 13] Permission denied: '/app/data/xkcd_state.json'
PermissionError: [Errno 13] Permission denied: '/app/data/comic_state.json'
```

The bot will also show a detailed error message on startup with fix instructions.

## Root Cause
The `/app/data` directory needs write permissions for the `penguin` user (non-root user, UID 999). This happens when:

1. You're mounting `/app/data` from the host with incorrect permissions
2. An existing Docker volume was created with root ownership
3. SELinux or AppArmor is blocking write access

## Quick Fix

The bot's startup logs will show you the exact command to run. Typically:

```bash
# Fix named volume (recommended)
docker run --rm -v penguin-overlord_penguin-data:/data alpine:latest chown -R 999:999 /data
docker-compose restart

# OR fix bind mount
sudo chown -R 999:999 ./data
docker-compose restart
```

## Detailed Solutions

### Option 1: Named Volume (Recommended)

**For NEW deployments:**
The `docker-compose.yml` includes a named volume that will be created with correct permissions automatically.

**For EXISTING deployments with permission errors:**

```bash
# Stop container
docker-compose down

# Get the penguin user's UID/GID (usually 999:999)
docker run --rm ghcr.io/chiefgyk3d/penguin-overlord:latest id penguin

# Fix ownership of the existing volume
docker run --rm -v penguin-overlord_penguin-data:/data alpine:latest chown -R 999:999 /data

# Restart
docker-compose up -d
```

### Option 2: Bind Mount (Host Directory)

If you prefer mounting a host directory:

```bash
# Create directory
mkdir -p ./data

# Set ownership (999:999 is the penguin user in the container)
sudo chown -R 999:999 ./data

# Update docker-compose.yml to use bind mount
volumes:
  - ./data:/app/data

# Start container
docker-compose up -d
```

### Option 3: SELinux Systems (RHEL/Fedora/CentOS)

If you're on a system with SELinux:

```bash
# Fix SELinux context
sudo chcon -Rt container_file_t ./data

# OR disable SELinux for the volume
sudo semanage fcontext -a -t container_file_t "./data(/.*)?"
sudo restorecon -R ./data
```

## Verification

Check the startup logs - you should see:
```
[✓] /app/data is writable
```

Instead of:
```
[PERMISSION ERROR: /app/data NOT WRITABLE]
```

You can also check manually:
```bash
docker logs penguin-overlord 2>&1 | grep -A 5 "PERMISSION ERROR"
```

If no output, permissions are correct!

## Why This Happens

1. **Security First**: The bot runs as non-root user `penguin` (UID 999) for security
2. **Volume Mounts**: When you mount a volume, Docker may use the host's file ownership
3. **Container vs Host UIDs**: The host's UID 999 might be a different user than the container's

## Security Note

**Never run the container as root to "fix" permissions!**

Running as root defeats Docker's security isolation. Instead:
- Use the fixes above to give the `penguin` user (UID 999) ownership
- The bot will run safely as non-root with proper permissions

## Still Having Issues?

1. Check Docker logs: `docker logs penguin-overlord`
2. Verify volume: `docker volume inspect penguin-overlord_penguin-data`
3. Check host permissions: `ls -la ./data` (if using bind mount)
4. Open an issue with the error output
