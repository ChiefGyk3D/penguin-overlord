# Penguin Overlord - CI/CD & Deployment

This document describes the CI/CD workflows and deployment options for Penguin Overlord.

## 🚀 CI/CD Workflows

### Python Testing (ci-tests.yml)

**Triggers:**
- Push to `main` branch
- Pull requests to `main`
- Manual workflow dispatch

**What it does:**
- ✅ Tests Python 3.10, 3.11, 3.12, 3.13, and 3.14
- ✅ Verifies bot structure and imports
- ✅ Tests all cog imports
- ✅ Validates requirements.txt compatibility
- ✅ Runs linting with Ruff
- ✅ Security scanning with Bandit
- ✅ Dependency vulnerability checking with Safety

### Docker Build & Publish (docker-build-publish.yml)

**Triggers:**
- Push to `main` branch (publishes)
- Version tags (`v*.*.*`) (publishes)
- Pull requests to `main` (build only)
- Manual workflow dispatch

**What it does:**
- 🐳 Builds multi-architecture images (amd64, arm64)
- 🔒 Scans images for vulnerabilities with Trivy
- 📦 Publishes to GitHub Container Registry
- ✅ Tests image imports before publishing
- 🏷️ Creates versioned and 'latest' tags

**Image location:** `ghcr.io/chiefgyk3d/penguin-overlord:latest`

## 🐳 Docker Deployment

### Using Docker Compose (Recommended)

```bash
# 1. Clone the repository
git clone https://github.com/ChiefGyk3D/penguin-overlord.git
cd penguin-overlord

# 2. Create .env file
./scripts/create-secrets.sh

# 3. Start with Docker Compose
docker compose up -d

# 4. View logs
docker compose logs -f

# 5. Stop
docker compose down
```

### Using Docker Directly

#### Option 1: Using .env file (Simple)

```bash
# Pull the image
docker pull ghcr.io/chiefgyk3d/penguin-overlord:latest

# Run with .env file
docker run -d \
  --name penguin-overlord \
  --restart unless-stopped \
  --env-file .env \
  -v $(pwd)/events:/app/events:ro \
  ghcr.io/chiefgyk3d/penguin-overlord:latest
```

#### Option 2: Using Doppler (Production)

```bash
# Pull the image
docker pull ghcr.io/chiefgyk3d/penguin-overlord:latest

# Run with Doppler
docker run -d \
  --name penguin-overlord \
  --restart unless-stopped \
  -e DOPPLER_TOKEN=dp.st.your_token_here \
  -e DOPPLER_PROJECT=penguin-overlord \
  -e DOPPLER_CONFIG=prd \
  -v $(pwd)/events:/app/events:ro \
  ghcr.io/chiefgyk3d/penguin-overlord:latest
```

#### Option 3: Direct environment variable

```bash
# Run with direct env var (not recommended for production)
docker run -d \
  --name penguin-overlord \
  --restart unless-stopped \
  -e DISCORD_BOT_TOKEN=your_token_here \
  -v $(pwd)/events:/app/events:ro \
  ghcr.io/chiefgyk3d/penguin-overlord:latest
```

#### Managing the container

```bash
# View logs
docker logs -f penguin-overlord

# Stop and remove
docker stop penguin-overlord
docker rm penguin-overlord
```

### Building Locally

```bash
# Build the image
docker build -t penguin-overlord:local -f Dockerfile .

# Run it
docker run -d \
  --name penguin-overlord \
  --restart unless-stopped \
  --env-file .env \
  -v $(pwd)/events:/app/events:ro \
  penguin-overlord:local
```

## 🐍 Python Deployment

### Manual Setup

```bash
# 1. Clone repository
git clone https://github.com/ChiefGyk3D/penguin-overlord.git
cd penguin-overlord

# 2. Create virtual environment (Python 3.10+)
python3 -m venv venv
source venv/bin/activate

# 3. Install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# 4. Create .env file
./scripts/create-secrets.sh

# 5. Run the bot
cd penguin-overlord
python bot.py
```

### systemd Service (Production)

```bash
# Install as systemd service
sudo ./scripts/install-systemd.sh

# Choose deployment mode:
# - Option 1: Python (uses venv)
# - Option 2: Docker (uses containers)

# Service management
sudo systemctl start penguin-overlord
sudo systemctl stop penguin-overlord
sudo systemctl restart penguin-overlord
sudo systemctl status penguin-overlord

# View logs
sudo journalctl -u penguin-overlord -f

# Uninstall
sudo ./scripts/uninstall-systemd.sh
```

## 🔐 Security Features

### Docker Image
- ✅ **Base**: Python 3.14-slim (latest security patches)
- ✅ **System Upgrades**: All packages upgraded during build
- ✅ **Non-root User**: Runs as dedicated `penguin` user
- ✅ **Minimal Attack Surface**: Only necessary packages installed
- ✅ **Multi-stage Build**: Optimized layer caching

### CI/CD
- ✅ **Trivy Scanning**: Vulnerability scanning for critical/high issues
- ✅ **Bandit**: Static security analysis for Python code
- ✅ **Safety**: Dependency vulnerability checking
- ✅ **CodeQL**: Advanced semantic code analysis
- ✅ **Dependency Review**: Automated dependency security checks

## 📋 Environment Variables

The bot supports multiple secret management methods (checked in priority order):

### 1. Doppler (Recommended for Production)

```bash
# Set these environment variables
DOPPLER_TOKEN=dp.st.your_token_here
DOPPLER_PROJECT=penguin-overlord  # Optional, default: stream-daemon
DOPPLER_CONFIG=prd                 # Optional, default: prd

# Bot will automatically fetch DISCORD_BOT_TOKEN from Doppler
```

### 2. AWS Secrets Manager

```bash
AWS_ACCESS_KEY_ID=your_key
AWS_SECRET_ACCESS_KEY=your_secret
AWS_REGION=us-east-1
SECRETS_MANAGER=aws
AWS_SECRET_NAME=penguin-overlord/discord
```

### 3. HashiCorp Vault

```bash
SECRETS_MANAGER=vault
SECRETS_VAULT_URL=https://vault.example.com
SECRETS_VAULT_TOKEN=your_vault_token
```

### 4. Direct Environment Variables (Simple)

```bash
# In .env file or as environment variable
DISCORD_BOT_TOKEN=your_discord_bot_token_here

# Optional
DISCORD_OWNER_ID=your_discord_user_id
DEBUG=true  # Enable debug logging
```

### Environment Variable Priority

The bot checks for credentials in this order:
1. Doppler (if `DOPPLER_TOKEN` is set)
2. AWS Secrets Manager (if `SECRETS_MANAGER=aws`)
3. HashiCorp Vault (if `SECRETS_MANAGER=vault`)
4. Direct `DISCORD_BOT_TOKEN` environment variable
5. `.env` file (via python-dotenv)

### Example .env file

```bash
# Penguin Overlord Configuration

# Option 1: Direct token (simple, for development)
DISCORD_BOT_TOKEN=your_token_here
DISCORD_OWNER_ID=your_user_id

# Option 2: Doppler (recommended for production)
# DOPPLER_TOKEN=dp.st.your_token_here
# DOPPLER_PROJECT=penguin-overlord
# DOPPLER_CONFIG=prd

# Optional settings
# DEBUG=true
```

## 🛠️ Development Workflow

### Local Development

```bash
# 1. Set up development environment
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 2. Create .env with test token
cp .env.example .env
# Edit .env with your test bot token

# 3. Run bot locally
cd penguin-overlord
python bot.py

# 4. Make changes to cogs
# Bot auto-loads all cogs from penguin-overlord/cogs/

# 5. Test changes
# Use Discord commands to verify functionality
```

### Creating a New Cog

```python
# penguin-overlord/cogs/mycog.py
import discord
from discord.ext import commands
import logging

logger = logging.getLogger(__name__)

class MyCog(commands.Cog):
    """Description of my cog"""
    
    def __init__(self, bot):
        self.bot = bot
    
    @commands.hybrid_command(name='mycommand')
    async def my_command(self, ctx: commands.Context):
        """Command description"""
        await ctx.send("Hello from my cog!")

async def setup(bot):
    await bot.add_cog(MyCog(bot))
    logger.info("MyCog loaded")
```

Bot will auto-load the cog on restart!

### Testing Before Commit

```bash
# Test imports
cd penguin-overlord
python -c "import bot; print('✓ Bot imports successfully')"

# Test cog imports
cd cogs
for cog in *.py; do
  python -c "import sys; sys.path.insert(0, '..'); import importlib; importlib.import_module('cogs.${cog%.py}')"
done

# Run linter
cd ../..
pip install ruff
ruff check penguin-overlord/
```

## 📦 Release Process

### Creating a Release

```bash
# 1. Update version in your code
# 2. Commit changes
git add .
git commit -m "Release v1.2.3"

# 3. Create and push tag
git tag v1.2.3
git push origin main
git push origin v1.2.3

# 4. GitHub Actions will automatically:
#    - Run all tests
#    - Build Docker images
#    - Push to GHCR with version tag
```

### Image Tags

- `latest` - Latest build from main branch
- `main` - Latest build from main branch
- `v1.2.3` - Specific version tag
- `v1.2` - Major.minor version
- `v1` - Major version
- `main-abc1234` - SHA-based tag

## 🐛 Troubleshooting

### Bot Won't Start

```bash
# Check logs
docker logs penguin-overlord
# or
sudo journalctl -u penguin-overlord -f

# Common issues:
# - Invalid Discord token
# - Missing .env file
# - Python version < 3.10
# - Missing dependencies
```

### Docker Build Fails

```bash
# Clean Docker cache
docker system prune -a

# Check Dockerfile syntax
docker build --no-cache -t test .

# Verify requirements.txt
pip check
```

### Service Won't Start

```bash
# Check service status
sudo systemctl status penguin-overlord

# Check service file
cat /etc/systemd/system/penguin-overlord.service

# Reload systemd
sudo systemctl daemon-reload

# View detailed logs
sudo journalctl -u penguin-overlord -n 100 --no-pager
```

## 📚 Additional Resources

- [Discord.py Documentation](https://discordpy.readthedocs.io/)
- [Docker Documentation](https://docs.docker.com/)
- [systemd Documentation](https://www.freedesktop.org/software/systemd/man/)
- [GitHub Actions Documentation](https://docs.github.com/en/actions)

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test locally
5. Submit a pull request

CI/CD will automatically test your PR!
