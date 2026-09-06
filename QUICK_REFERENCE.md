# 🐧 Penguin Overlord - Quick Reference Card

## Essential Commands

### Setup & Testing
```bash
# Quick start (automated)
./start.sh

# Test configuration
python test_secrets.py

# Manual start
cd penguin-overlord && python bot.py
# OR
python -m penguin-overlord.bot
```

### With Doppler
```bash
# Export token
export DOPPLER_TOKEN=dp.st.your_token
export DOPPLER_PROJECT=penguin-overlord
export DOPPLER_CONFIG=prd

# OR use Doppler CLI
doppler run -- python bot.py
```

## Discord Bot Commands

The full list, every command with its arguments, permission, and env gate,
is [docs/reference/COMMANDS.md](docs/reference/COMMANDS.md). Hybrid
commands work as `/name` or `!name`; the `/mod`, `/news`, `/profile`, and
`/roles` groups are slash only.

The ones people reach for:

| Command | Description |
|---------|-------------|
| `/help` | Categorized help with a dropdown of pages |
| `/solar` | Physics-based solar weather and band predictions |
| `/radio_maps` | D-RAP, aurora, and X-ray maps in one post |
| `/bandplan 20m` | ARRL band plan reference |
| `/cve`, `/kev` | Latest CVEs, latest CISA KEV additions |
| `/xkcd [number]`, `/comic` | XKCD or a random tech comic |
| `/events next`, `/events submit` | Con Recon: upcoming events; propose one for review |
| `/news status <category>` | Where and how often a news category posts |
| `/mod status`, `/mod pending` | Moderation mode and open reviews (moderators) |
| `/profile sync-automod` | Push the name screen into Discord AutoMod (admins) |
| `/roles post <panel>` | Create and post a self-role panel (Manage Roles) |

## Doppler Secrets

### Required Secret
- `DISCORD_BOT_TOKEN` - Your Discord bot token

### Optional Secrets (for future features)
- Any secret with format: `PREFIX_KEY_NAME`
- Access in code: `get_secret('PREFIX', 'KEY_NAME')`

## Configuration Priority

1. 🥇 **Doppler** (if `DOPPLER_TOKEN` is set)
2. 🥈 **AWS Secrets Manager** (if `SECRETS_MANAGER=aws`)
3. 🥉 **HashiCorp Vault** (if `SECRETS_MANAGER=vault`)
4. 📄 **.env file** (fallback)

## Project Structure
```
penguin-overlord/
├── penguin-overlord/
│   ├── bot.py              # Main bot entry point
│   ├── cogs/               # Bot features/commands
│   │   └── xkcd.py         # XKCD commands
│   ├── social/
│   │   ├── discord.py      # Discord webhook platform
│   │   └── matrix.py       # Matrix (future)
│   └── utils/
│       ├── config.py       # Configuration management
│       └── secrets.py      # Secrets manager integration
├── requirements.txt        # Dependencies
├── .env.example           # Config template
├── start.sh               # Quick start script
├── test_secrets.py        # Configuration tester
├── README.md              # Full documentation
├── DOPPLER_SETUP.md       # Doppler guide
└── DOPPLER_INTEGRATION.md # Integration details
```

## Troubleshooting

### Bot won't start
```bash
# Test configuration
python test_secrets.py

# Check token is set
echo $DOPPLER_TOKEN
# OR
cat .env | grep DISCORD_BOT_TOKEN
```

### "Token not found" error
1. Verify Doppler token: `echo $DOPPLER_TOKEN`
2. Check secret exists in Doppler dashboard
3. Verify secret name is exactly `DISCORD_BOT_TOKEN`
4. Try fallback: Create `.env` file

### Import errors
```bash
# Install dependencies
pip install -r requirements.txt

# OR use the start script
./start.sh
```

## Adding New Features

1. Create new file in `penguin-overlord/cogs/`
2. Follow pattern from `xkcd.py`
3. Bot auto-loads all cogs on startup

Example:
```python
from discord.ext import commands

class MyCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    @commands.hybrid_command()
    async def mycommand(self, ctx):
        await ctx.send("Hello!")

async def setup(bot):
    await bot.add_cog(MyCog(bot))
```

## Discord Bot Setup

### Get Bot Token
See `GET_DISCORD_TOKEN.md` for complete guide

### OAuth2 Invite URL (for Private Bots)
```
https://discord.com/api/oauth2/authorize?client_id=YOUR_CLIENT_ID&permissions=414464724032&scope=bot%20applications.commands
```

Replace `YOUR_CLIENT_ID` with your Application ID from Developer Portal

### Required Permissions
- View Channels (1024)
- Send Messages (2048)
- Embed Links (4096)
- **Recommended:** 414464724032 (includes all features)

See `DISCORD_PERMISSIONS.md` for detailed permission guide

### Critical Setting
⚠️ **Enable "MESSAGE CONTENT INTENT"** in Developer Portal → Bot settings!

## Useful Links

- [Discord Developer Portal](https://discord.com/developers/applications)
- [Doppler Dashboard](https://dashboard.doppler.com/)
- [Discord.py Documentation](https://discordpy.readthedocs.io/)
- [XKCD API](https://xkcd.com/json.html)

## Getting Help

📖 **Read the docs:**
- `README.md` - General documentation
- `DOPPLER_SETUP.md` - Doppler setup guide
- `DOPPLER_INTEGRATION.md` - Integration details

🧪 **Test your setup:**
```bash
python test_secrets.py
```

🚀 **Quick start:**
```bash
./start.sh
```

---

Made with 🐧 and ❤️
