# Doppler Setup Guide for Penguin Overlord

> ARCHIVED: historical document. Commands, counts, and paths in here may no longer match the code; the current docs are indexed in [docs/README.md](../README.md).

This guide will help you set up Doppler secrets manager with Penguin Overlord.

## Why Use Doppler?

- ✅ Secure secret storage
- ✅ Team collaboration
- ✅ Environment-specific configs (dev, staging, prod)
- ✅ Audit logs
- ✅ No `.env` files to manage
- ✅ Automatic secret syncing

## Setup Steps

### 1. Create a Doppler Account

1. Go to [Doppler](https://www.doppler.com/) and sign up
2. Create a new project (e.g., "penguin-overlord")

### 2. Add Your Discord Bot Token to Doppler

1. In your Doppler project, select your config (e.g., "prd" for production)
2. Click "Add Secret"
3. Add the following secret:
   - **Name**: `DISCORD_BOT_TOKEN`
   - **Value**: Your Discord bot token from the Discord Developer Portal

### 3. Get Your Doppler Service Token

1. In Doppler, go to your project settings
2. Go to "Access" → "Service Tokens"
3. Create a new service token for your environment (e.g., "penguin-overlord-bot")
4. Copy the token (it starts with `dp.st.`)

### 4. Configure Your Environment

You have two options:

**Option A: Set Environment Variables**

```bash
export DOPPLER_TOKEN=dp.st.your_token_here
export DOPPLER_PROJECT=penguin-overlord
export DOPPLER_CONFIG=prd
```

**Option B: Use Doppler CLI (Recommended)**

Install Doppler CLI:
```bash
# macOS
brew install dopplerhq/cli/doppler

# Linux
curl -Ls https://cli.doppler.com/install.sh | sh

# Windows
scoop install doppler
```

Login and setup:
```bash
doppler login
doppler setup
```

Then run your bot with Doppler:
```bash
doppler run -- python -m penguin-overlord.bot
```

Or from the penguin-overlord directory:
```bash
doppler run -- python bot.py
```

### 5. Verify It Works

When you start the bot, you should see in the logs:
```
INFO - Doppler connection successful. Found X total secrets
```

If the bot starts successfully, Doppler is working! 🎉

## Adding More Secrets

As you add more features, simply add new secrets to Doppler:

```
DISCORD_BOT_TOKEN=your_bot_token
# Future secrets for other features
API_KEY=some_api_key
DATABASE_URL=postgresql://...
```

The bot will automatically fetch them using the `get_secret()` function from `utils/secrets.py`.

## Environment-Specific Configs

Doppler supports multiple environments:

- **dev** - Development/testing
- **stg** - Staging
- **prd** - Production

Switch between them:
```bash
export DOPPLER_CONFIG=dev  # or stg, prd
```

Or with Doppler CLI:
```bash
doppler run --config dev -- python bot.py
```

## Troubleshooting

### "DISCORD_BOT_TOKEN not found"

1. Check your Doppler token is set: `echo $DOPPLER_TOKEN`
2. Verify the secret exists in Doppler with the exact name `DISCORD_BOT_TOKEN`
3. Make sure your project and config are correct

### Using Both .env and Doppler

The bot prioritizes secrets in this order:
1. **Doppler** (if `DOPPLER_TOKEN` is set)
2. **AWS Secrets Manager** (if `SECRETS_MANAGER=aws`)
3. **HashiCorp Vault** (if `SECRETS_MANAGER=vault`)
4. **.env file** (fallback)

So if you have `DOPPLER_TOKEN` set, it will use Doppler first!

## Security Best Practices

✅ **DO:**
- Use service tokens (not personal access tokens) for bots
- Rotate tokens periodically
- Use different configs for dev/staging/prod
- Keep your `DOPPLER_TOKEN` secure

❌ **DON'T:**
- Commit `.env` files with real secrets
- Share service tokens publicly
- Use production tokens in development

## More Information

- [Doppler Documentation](https://docs.doppler.com/)
- [Doppler CLI Reference](https://docs.doppler.com/docs/cli)
- [Service Tokens](https://docs.doppler.com/docs/service-tokens)
