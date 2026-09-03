# Penguin Overlord - CI/CD & Deployment

This document describes the CI/CD workflows and deployment options for Penguin Overlord.

## 🚀 CI/CD Workflows

### Python Testing (ci-tests.yml)

**Triggers:**
- Push to `main` branch
- Pull requests to `main`
- Manual workflow dispatch

**What it does** (three jobs, see `.github/workflows/ci-tests.yml`):

- `test`: a matrix over Python 3.10, 3.11, 3.12 and 3.13 (required), plus
  3.14 marked experimental (`continue-on-error`). Each leg installs
  `requirements-dev.txt`, runs
  `pytest tests/ -m "not network" --cov=penguin-overlord --cov-fail-under=29`,
  then `pip check`.
- `lint`: `ruff check . --output-format=github` on Python 3.12. Required.
- `security-advisory`: `bandit -r penguin-overlord/ -lll` is a required gate
  (high-severity findings fail the job); the full Bandit report and
  `pip-audit -r requirements.txt` run as advisory (`continue-on-error`) and
  the Bandit JSON report is uploaded as an artifact.

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

The image ships the events CSV baked in for the one-time import (see
[Events Guide](../features/EVENTS.md)); `docker-compose.yml` mounts only the
named `penguin-data` volume at `/app/data`, caps the container at 1 CPU /
512 MB, rotates logs with the json-file driver (20m x 5), and declares a
healthcheck that runs `scripts/healthcheck.py` every 30 s.

**Static IP / VLAN placement:** `docker-compose.macvlan.example.yml` is an
override that puts the bot container on an existing macvlan network with a
fixed address and DNS server. Copy it to `docker-compose.override.yml`
(gitignored), edit the network name, address and DNS, and `docker compose
up -d` picks it up. It only affects the compose-managed bot container; the
timer containers written by `scripts/install-systemd.sh` in Docker mode use
plain `docker run` and need `--network` / `--dns` added to each unit's
`ExecStart` by hand.

**Healthcheck:** `scripts/healthcheck.py` (also baked into the image as the
Dockerfile `HEALTHCHECK`) is a no-op unless `METRICS_ENABLED=true`. With
metrics on it fetches `http://127.0.0.1:${METRICS_PORT:-9200}/metrics` and
reports unhealthy unless `penguin_bot_connected 1` is present, so the
container goes unhealthy when the Discord gateway drops rather than only
when the process dies.

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
  -v penguin-data:/app/data \
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
  -v penguin-data:/app/data \
  ghcr.io/chiefgyk3d/penguin-overlord:latest
```

#### Option 3: Direct environment variable

```bash
# Run with direct env var (not recommended for production)
docker run -d \
  --name penguin-overlord \
  --restart unless-stopped \
  -e DISCORD_BOT_TOKEN=your_token_here \
  -v penguin-data:/app/data \
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
  -v penguin-data:/app/data \
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
# Install as systemd service. Run as your own user, NOT with sudo:
# the script reads $USER for User= and --user UID:GID, and calls sudo
# itself where root is needed. Under sudo everything installs as root.
./scripts/install-systemd.sh

# Choose deployment mode:
# - Option 1: Python (uses venv)
# - Option 2: Docker (uses containers)
# Then choose whether news and the background posters run as systemd timers.

# Service management
sudo systemctl start penguin-overlord
sudo systemctl stop penguin-overlord
sudo systemctl restart penguin-overlord
sudo systemctl status penguin-overlord

# View logs
sudo journalctl -u penguin-overlord -f

# Uninstall (this one does run as root)
sudo ./scripts/uninstall-systemd.sh
```

#### Standalone runner entrypoints

Besides `bot.py`, `penguin-overlord/` ships five one-shot entrypoints that
fetch, post and exit, meant to be driven by systemd timers (or cron):

| Script | Posts |
|--------|-------|
| `news_runner.py --category <name>` | one of the 11 news categories |
| `kev_runner.py` | CISA Known Exploited Vulnerabilities |
| `solar_runner.py` | NOAA space weather / HF propagation |
| `xkcd_runner.py` | new XKCD comics |
| `comics_runner.py` | daily tech comics |

The installer writes and schedules units for all of them. Unit names,
schedules, and the `NEWS_AUTO_POST=false` setting that stops the bot from
posting the same items itself are documented in
[SYSTEMD.md](SYSTEMD.md).

## 🔐 Security Features

### Docker Image
- ✅ **Base**: Python 3.14-slim (latest security patches)
- ✅ **System Upgrades**: All packages upgraded during build
- ✅ **Non-root User**: Runs as dedicated `penguin` user
- ✅ **Minimal Attack Surface**: Only necessary packages installed
- ✅ **Multi-stage Build**: Optimized layer caching

### CI/CD
- ✅ **Trivy Scanning**: Vulnerability scanning for critical/high issues (docker-build-publish.yml)
- ✅ **Bandit**: Static security analysis; high-severity findings block the build
- ✅ **pip-audit**: Dependency vulnerability checking (advisory)
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
SECRETS_MANAGER=aws
# One secret per prefix, named by a <PREFIX>_SECRET_NAME variable. The
# secret's body is JSON keyed by the bare key name, so
# get_secret('DISCORD', 'BOT_TOKEN') fetches the secret named in
# DISCORD_SECRET_NAME and reads its "BOT_TOKEN" field.
DISCORD_SECRET_NAME=penguin-overlord/discord   # {"BOT_TOKEN": "...", "OWNER_ID": "..."}
NEWS_SECRET_NAME=penguin-overlord/news         # {"CVE_CHANNEL_ID": "...", "KEV_CHANNEL_ID": "..."}
```

There is no single `AWS_SECRET_NAME`. `utils/secrets.py` calls
`boto3.client('secretsmanager')` with no explicit credentials, so boto3's
own chain applies: `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` /
`AWS_REGION` env vars, `~/.aws/credentials` and `config`, an instance or
task role, or SSO. Prefer a role over static keys in `.env`. `boto3` is
pinned in `requirements.txt` and imported lazily, so the other backends do
not pay for it.

Caveat: `get_secret()` only consults AWS when the caller passes
`secret_name_env` (the `<PREFIX>_SECRET_NAME` variable to read). The call
sites in the current tree do not pass it, so with `SECRETS_MANAGER=aws` the
lookup falls through to plain environment variables today. Doppler and `.env`
are the paths exercised in production.

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
```

### Logging

All entrypoints (the bot and the five runners) share one configuration in
`penguin-overlord/utils/logging_setup.py`. There is no `DEBUG` flag; use:

| Variable | Default | Meaning |
|----------|---------|---------|
| `LOG_LEVEL` | `INFO` | Root log level: `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `LOG_FILE` | unset | Path to also write to. Setting it turns on an in-process `RotatingFileHandler`; stdout logging stays on regardless so `docker logs` / journald are never empty |
| `LOG_MAX_BYTES` | `10485760` (10 MB) | Rotate the file at this size |
| `LOG_BACKUPS` | `5` | Rotated files to keep (about 60 MB ceiling at the default size) |

In containers, leave `LOG_FILE` unset and let the Docker json-file driver
rotate (configured in `docker-compose.yml` and in the systemd unit). Set
`LOG_FILE` for bare-metal runs where nothing else rotates. An unwritable
`LOG_FILE` logs a warning and falls back to stdout only; it never stops the
bot from starting. `news_runner.py --verbose` is the per-run equivalent of
`LOG_LEVEL=DEBUG`.

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
# LOG_LEVEL=INFO
# LOG_FILE=/var/log/penguin-overlord/bot.log   # bare metal only; Docker rotates via the log driver
# LOG_MAX_BYTES=10485760
# LOG_BACKUPS=5
# NEWS_AUTO_POST=false   # when systemd timers own posting; see SYSTEMD.md
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
