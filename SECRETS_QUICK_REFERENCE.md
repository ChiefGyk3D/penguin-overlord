# Penguin Overlord - Environment & Secrets Quick Reference

## 🔐 Secrets Management Options

The bot supports 5 different ways to provide credentials, checked in this order:

### Priority Order
1. **Doppler** - If `DOPPLER_TOKEN` is set
2. **AWS Secrets Manager** - If `SECRETS_MANAGER=aws`
3. **HashiCorp Vault** - If `SECRETS_MANAGER=vault`
4. **Environment Variable** - Direct `DISCORD_BOT_TOKEN`
5. **.env File** - Loaded via python-dotenv

---

## 🐳 Docker Deployment Options

### Option 1: Using .env File (Easiest)

```bash
# 1. Create .env file
cat > .env << 'EOF'
DISCORD_BOT_TOKEN=your_token_here
DISCORD_OWNER_ID=your_user_id
EOF

# 2. Run with docker-compose
docker compose up -d

# OR run directly
docker run -d --name penguin-overlord \
  --env-file .env \
  -v $(pwd)/events:/app/events:ro \
  ghcr.io/chiefgyk3d/penguin-overlord:latest
```

### Option 2: Using Doppler (Production Recommended)

```bash
# 1. Set Doppler token
export DOPPLER_TOKEN=dp.st.your_token_here

# 2. Run with docker-compose (uncomment Doppler section)
docker compose up -d

# OR run directly
docker run -d --name penguin-overlord \
  -e DOPPLER_TOKEN=$DOPPLER_TOKEN \
  -e DOPPLER_PROJECT=penguin-overlord \
  -e DOPPLER_CONFIG=prd \
  -v $(pwd)/events:/app/events:ro \
  ghcr.io/chiefgyk3d/penguin-overlord:latest
```

### Option 3: Direct Environment Variable

```bash
# Quick test run (not recommended for production)
docker run -d --name penguin-overlord \
  -e DISCORD_BOT_TOKEN=your_token_here \
  -v $(pwd)/events:/app/events:ro \
  ghcr.io/chiefgyk3d/penguin-overlord:latest
```

---

## 🐍 Python Deployment Options

### Option 1: Using .env File

```bash
# 1. Create virtual environment
python3 -m venv venv
source venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Create .env
./scripts/create-secrets.sh

# 4. Run bot
cd penguin-overlord
python bot.py
```

### Option 2: Using Doppler

```bash
# 1. Set Doppler token
export DOPPLER_TOKEN=dp.st.your_token_here
export DOPPLER_PROJECT=penguin-overlord
export DOPPLER_CONFIG=prd

# 2. Run bot (will fetch token from Doppler)
cd penguin-overlord
python bot.py
```

### Option 3: Direct Environment Variable

```bash
# 1. Set token
export DISCORD_BOT_TOKEN=your_token_here

# 2. Run bot
cd penguin-overlord
python bot.py
```

---

## 🔧 systemd Service (Production)

The installer supports both Python and Docker deployments:

```bash
# Run installer
sudo ./scripts/install-systemd.sh

# Choose deployment:
# 1 = Python with venv
# 2 = Docker container

# The installer will:
# - Create systemd service
# - Set up auto-start on boot
# - Configure proper security settings
```

---

## 🔍 Verification Commands

### Check if bot can access token

```bash
# Docker
docker run --rm --env-file .env ghcr.io/chiefgyk3d/penguin-overlord:latest \
  python -c "import os; print('Token found!' if os.getenv('DISCORD_BOT_TOKEN') else 'No token')"

# Python
cd penguin-overlord
python -c "from dotenv import load_dotenv; import os; load_dotenv(); print('Token found!' if os.getenv('DISCORD_BOT_TOKEN') else 'No token')"
```

### Test Doppler connection

```bash
# Set token
export DOPPLER_TOKEN=dp.st.your_token

# Test
python -c "
from dopplersdk import DopplerSDK
import os
sdk = DopplerSDK()
sdk.set_access_token(os.getenv('DOPPLER_TOKEN'))
print('Doppler connected!')
"
```

---

## 📋 Environment Variable Reference

### Required (at least one method)

| Variable | Purpose | Method |
|----------|---------|--------|
| `DISCORD_BOT_TOKEN` | Discord bot token | Direct/.env |
| `DOPPLER_TOKEN` | Doppler access token | Doppler |
| `AWS_ACCESS_KEY_ID` + `AWS_SECRET_ACCESS_KEY` | AWS credentials | AWS |
| `SECRETS_VAULT_TOKEN` | Vault token | Vault |

### Optional

| Variable | Default | Purpose |
|----------|---------|---------|
| `DISCORD_OWNER_ID` | None | Bot owner user ID |
| `DOPPLER_PROJECT` | stream-daemon | Doppler project name |
| `DOPPLER_CONFIG` | prd | Doppler config name |
| `SECRETS_MANAGER` | auto | Force specific manager (aws/vault) |
| `LOG_LEVEL` | INFO | Logging verbosity |
| `DEBUG` | false | Enable debug mode |

---

## 🚨 Security Best Practices

### ✅ DO:
- Use Doppler for production deployments
- Use `.env` file for development (add to .gitignore)
- Set proper file permissions: `chmod 600 .env`
- Use Docker secrets or Kubernetes secrets in orchestrated environments
- Rotate tokens regularly

### ❌ DON'T:
- Commit `.env` files to git
- Use direct environment variables in production
- Share tokens in logs or error messages
- Store tokens in plaintext on shared systems
- Use the same token for dev and production

---

## 🆘 Troubleshooting

### Bot says "DISCORD_BOT_TOKEN not found"

Check in order:
1. If using Doppler: `echo $DOPPLER_TOKEN` (should show token)
2. If using .env: `cat .env | grep DISCORD_BOT_TOKEN` (should show token)
3. If using env var: `echo $DISCORD_BOT_TOKEN` (should show token)
4. File permissions: `ls -la .env` (should be readable)
5. Working directory: Make sure you're in the right directory

### Doppler not working

```bash
# Test Doppler CLI
doppler --version

# Test token
doppler secrets list --token=$DOPPLER_TOKEN

# Check bot logs
docker logs penguin-overlord | grep -i doppler
```

### Docker can't read .env

```bash
# Check file exists
ls -la .env

# Check file is readable
cat .env

# Try mounting explicitly
docker run -v $(pwd)/.env:/app/.env:ro ...

# Or use --env-file
docker run --env-file .env ...
```

---

## 📚 Additional Resources

- [Doppler Documentation](https://docs.doppler.com/)
- [Discord Bot Token Guide](../GET_DISCORD_TOKEN.md)
- [Doppler Setup Guide](../DOPPLER_SETUP.md)
- [Full Deployment Guide](../DEPLOYMENT.md)
