# 🐧 Penguin Overlord

<div align="center">
  <img src="media/banner_wide.png" alt="Penguin Overlord Banner" />
  
  [![Docker](https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&logo=docker&logoColor=white)](https://github.com/ChiefGyk3D/penguin-overlord/pkgs/container/penguin-overlord)
  [![Python 3.10-3.14](https://img.shields.io/badge/Python-3.10--3.14-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
  [![Discord.py](https://img.shields.io/badge/Discord.py-2.6.4-5865F2?style=for-the-badge&logo=discord&logoColor=white)](https://discordpy.readthedocs.io/)
  [![License: MPL 2.0](https://img.shields.io/badge/License-MPL_2.0-brightgreen.svg?style=for-the-badge)](https://opensource.org/licenses/MPL-2.0)
</div>

A feature-rich Discord bot for tech enthusiasts, HAM radio operators, aviation spotters, and cybersecurity professionals! Get tech quotes, XKCD comics, solar weather data, HAM radio news, aviation frequencies, SIGINT resources, and event reminders all in one bot.

## ✨ Features

### 💬 Tech Quote of the Day
Get inspirational, humorous, and insightful quotes from tech legends!

**Commands:**
- `!techquote` or `/techquote` - Get a random quote from any tech legend
- `!quote_linus` or `/quote_linus` - Get a quote from Linus Torvalds
- `!quote_stallman` or `/quote_stallman` - Get a quote from Richard Stallman
- `!quote_hopper` or `/quote_hopper` - Get a quote from Grace Hopper
- `!quote_shevinsky` or `/quote_shevinsky` - Get a quote from Elissa Shevinsky
- `!quote_may` or `/quote_may` - Get a quote from Timothy C. May
- `!quote_list` or `/quote_list` - Browse all available quote authors (interactive paginator!)

**Featured Quote Authors (610+ quotes from 70+ legends):**
- Linux/Unix Pioneers: Linus Torvalds, Dennis Ritchie, Ken Thompson, Rob Pike
- Open Source Champions: Richard Stallman, Eric S. Raymond, Larry Wall
- Language Creators: Guido van Rossum (Python), Yukihiro Matsumoto (Ruby), Bjarne Stroustrup (C++)
- Computer Science Legends: Alan Turing, Ada Lovelace, Grace Hopper, Donald Knuth, Edsger Dijkstra
- Industry Icons: Steve Jobs, Bill Gates, Mark Zuckerberg
- Privacy & Security: Elissa Shevinsky, Timothy C. May, Gene Spafford
- Software Engineering: Fred Brooks, Robert C. Martin, Martin Fowler, Kent Beck
- And many more!

### 🎨 XKCD Commands
- `!xkcd` or `!xkcd [number]` - Get the latest XKCD comic or a specific one by number
- `!xkcd_latest` - Get the latest XKCD comic
- `!xkcd_random` - Get a random XKCD comic
- `!xkcd_search [keyword]` - Search for XKCD comics by keyword in titles (searches last 100 comics)

### 🤖 Automated XKCD Poster
The bot can automatically post new XKCD comics to a configured channel. This is handled by the `xkcd_poster` cog which polls the XKCD API and posts new comics when they appear.

Configuration options (set in your `.env` or via the runtime admin command):

- `XKCD_POST_CHANNEL_ID` — Numeric channel ID where new comics will be posted. Example: `123456789012345678`
- `XKCD_POLL_INTERVAL_MINUTES` — How often to check for new comics (default: `30` minutes)

Admin runtime commands (owner or Manage Server permission required):

- `!xkcd_set_channel <#channel|channel_id>` — Set the automatic post channel
- `!xkcd_enable` / `!xkcd_disable` — Enable or disable the automatic poster
- `!xkcd_post_now` — Force-post the latest XKCD immediately

State persistence:

The cog stores its state in `data/xkcd_state.json` and will create the `data/` directory and file on first run. The file contains `last_posted`, `channel_id`, and `enabled` fields.

### 🎨 Tech Comics Collection
Enjoy tech humor from multiple actively-updated webcomic sources with smart duplicate prevention!

**Manual Commands:**
- `!comic` or `!comic random` - Random tech comic from any source
- `!comic xkcd` - Latest XKCD (tech/science/cyber humor)
- `!comic joyoftech` - Latest Joy of Tech (Apple, Linux, geek culture)
- `!comic turnoff` - Latest TurnOff.us (Git/DevOps/programmer humor)
- `!comic_trivia [xkcd_num]` - Get explanation for an XKCD comic from explainxkcd.com

**📰 Daily Tech Comics (Automated):**
The bot can automatically post a random tech comic daily at 9 AM UTC to a configured channel. **New**: Duplicate prevention tracks the last 100 posted comics to avoid repeats.

Configuration:
- `COMIC_POST_CHANNEL_ID` — Channel ID for daily comic posts (optional, can use runtime command)

Admin runtime commands (owner or Manage Server permission required):
- `!comic_set_channel <#channel>` — Set the daily comic channel
- `!comic_enable` / `!comic_disable` — Toggle daily posting (9 AM UTC)
- `!daily_comic` — Force post a comic immediately

**Comic Sources:**
- 🤓 **XKCD**: Tech, science, and cybersecurity humor (via JSON API: https://xkcd.com/info.0.json)
- 😂 **Joy of Tech**: Apple, Linux, and general geek culture (via https://www.joyoftech.com/joyoftech/jotblog/index.xml)
- 🔧 **TurnOff.us**: Git, DevOps, and programmer humor (via https://turnoff.us/feed.xml)

State persistence: Stored in `data/comic_state.json`

### 🎲 Fun Commands
- `!cyberfortune` - Get a cybersecurity-themed fortune cookie
- `!randomlinuxcmd` - Get a random Linux command from the manpage (250+ commands)
- `!patchgremlin` - Encounter the mischievous Patch Gremlin who might... patch things

### ☀️ Solar & Space Weather (Radiohead)
Real-time space weather and **physics-based propagation predictions** for HAM radio operators!

**Propagation & Space Weather:**
- `!solar` - Current solar conditions with ionospheric physics predictions (foF2, MUF, D-layer absorption, includes 6-hour X-ray chart)
- `!propagation` - Alias for `!solar` - HF radio propagation conditions
- `!xray [period]` - GOES Solar X-Ray Flux charts (6h/1d/3d/7d) - Shows solar flare activity and HF blackout potential
- `!drap` - D-Region Absorption Prediction map (real-time HF absorption visualization)
- `!aurora` - Current auroral oval and 30-min forecast (VHF scatter conditions)
- `!radio_maps` - Comprehensive propagation maps (D-RAP, aurora, solar X-ray flux)

**Reference & Tools:**
- `!bandplan [band]` - ARRL band plan reference (160m-70cm)
- `!frequency [service]` - HAM band or service frequency lookup (LoRa, WiFi, GMRS, etc.)
- `!ham_class <class>` - License class info with privileges and power limits
- `!grid [coords/grid]` - **NEW!** Maidenhead grid square calculator - Convert lat/lon to grid, calculate distance & bearing between grids
- `!contests [days]` - **NEW!** Upcoming amateur radio contests (CW, SSB, Digital, VHF)
- `!satellite [grid]` - **NEW!** Active amateur satellites (FM voice, SSB, digital) with frequencies and operating tips
- `!repeater [location]` - **NEW!** Find repeaters by ZIP, city, or grid square (links to major databases)

**News & Trivia:**
- `!hamnews` - Latest HAM radio news and updates
- `!freqtrivia` - Random HAM radio frequency trivia
- `!hamradio` - Random HAM radio facts and trivia

**Recent improvements**: Enhanced propagation math and physics calculations, improved D-layer absorption modeling, refined MUF calculations for better HF band predictions, fixed 80m band status emoji display, and improved automated solar report posting reliability. Physics-based propagation uses MUF calculations, D-layer absorption modeling, gray line detection, K-index frequency-dependent impact, and seasonal Sporadic-E predictions. **Includes visual maps** from NOAA showing real-time HF absorption, aurora position, and solar activity. **Automated reports post every 30 minutes** with full physics-based calculations including X-ray flux, D-RAP, and Aurora forecast charts. **NEW:** Grid square tools for VHF/UHF contesting, satellite tracking, contest calendar, and repeater directory! See [docs/features/RADIOHEAD_HAM_RADIO.md](docs/features/RADIOHEAD_HAM_RADIO.md) for details.

### ✈️ Aviation (Planespotter)
Aviation frequencies and resources!
- `!avfreq [type]` - Get aviation frequencies (tower, ground, approach, departure, etc.)
- `!avresources` - Useful aviation monitoring resources

### 📡 SIGINT Resources
Intelligence and monitoring resources!
- `!sigint` - Get SIGINT monitoring resources and frequencies
- `!sigintresources` - Comprehensive SIGINT resource list

### 📰 Automated News Aggregation (120+ sources, 11 categories)

The bot features a comprehensive automated news system that aggregates and posts news from 120+ RSS feeds across 11 specialized categories!

**News Categories:**
- 🔒 **Cybersecurity** (36 sources) - TheHackerNews, Krebs on Security, Troy Hunt, Security Affairs, NCSC (UK), Google Security, Sophos, Trend Micro, Dark Reading, Schneier, and more
- 💻 **Tech** (17 sources) - Ars Technica, The Verge, TechCrunch, Wired, Engadget, ZDNet, BBC Technology, BBC Science, and more
- 🎮 **Gaming** (10 sources) - IGN, Polygon, Kotaku, PC Gamer, GameSpot, and more
- 🍎 **Apple & Google** (27 sources) - 9to5Mac, 9to5Google, MacRumors, Android Police, and more
- 🛡️ **CVE Vulnerabilities** (2 sources) - National Vulnerability Database, Ubuntu Security Notices (general awareness)
- 🚨 **KEV - Known Exploited** (2 sources) - CISA Known Exploited Vulnerabilities (CRITICAL: actively exploited), Exploit-DB RSS (HIGH: exploit code available)
- 🏛️ **US Legislation** (5 sources) - Congressional tech/privacy/security bills from Congress.gov (cleaned HTML presentation)
- 🇪🇺 **EU Legislation** (3 sources) - EU tech regulation from EUR-Lex
- 🇬🇧 **UK Legislation** (1 source) - UK Parliament All Bills (public + private combined)
- 📰 **General News** (12 sources) - NPR, PBS, Financial Times, Reuters, BBC News (UK, World, Politics, Health), and more
- 🚨 **Vendor Alerts** (8+ sources) - AWS Service Health, Azure Status, Google Cloud Status, Cloudflare, GitHub, Datadog, PagerDuty, Atlassian Status

**Manual Commands:**
- `/news status` - Check configuration and enabled categories
- `/news enable <category>` - Enable a news category
- `/news disable <category>` - Disable a news category
- `/news set_channel <category> <#channel>` - Set posting channel for a category
- `/news test <category>` - Test fetch and post for a category

**Automated Posting:**
The bot uses systemd timers (or manual cron) to automatically fetch and post news at configured intervals:
- Cybersecurity: Every 3 hours
- Tech & Gaming: Every 4 hours
- Apple/Google: Every 6 hours
- CVE (General): Every 8 hours
- KEV (Critical): Every 4 hours (dual sources: CISA + Exploit-DB)
- US Legislation: Every hour
- EU/UK Legislation: Every 12 hours
- General News: Every 2 hours
- Vendor Alerts: Every 30 minutes

**Features:**
- ✅ Smart deduplication (no repeated posts, tracks last 100 items)
- ✅ HTML tag stripping and entity decoding
- ✅ Special handling for GovInfo sources (clean title + link only, no raw HTML)
- ✅ Dual KEV sources with severity indicators (CRITICAL vs HIGH)
- ✅ Discord-friendly embeds with source-specific icons and colors
- ✅ Configurable per-category channels
- ✅ State persistence across restarts
- ✅ Concurrent feed fetching for performance
- ✅ Vendor alert monitoring for cloud service disruptions

See **[News System Guide](docs/features/NEWS_SYSTEM.md)** for complete setup instructions.

### �📅 Event Pinger
Never miss a cybersecurity conference or HAM radio event!
- `!events [type]` - List upcoming events (cybersecurity/ham/all)
- `!allevents [type]` - Paginated view of all events
- `!nextevent [type]` - Get the next upcoming event
- `!searchevent <query>` - Search for events by name

**Event Types:**
- 🔐 Cybersecurity conferences (DEF CON, BSides, DerbyCon, etc.)
- 📻 HAM radio events (Hamvention, Field Day, contests, etc.)

### 🎯 Source Code
- `!source_code` - Get the GitHub repository link

All commands support both prefix (`!command`) and slash commands (`/command`)!

## 🚀 Quick Start

### Option 1: Docker (Recommended)

The easiest way to get started:

```bash
# 1. Create .env file with your Discord bot token
cat > .env << 'EOF'
DISCORD_BOT_TOKEN=your_token_here
DISCORD_OWNER_ID=your_user_id

# Optional: Configure auto-posting channels (see .env.example for all options)
# IMPORTANT: Use numeric channel IDs only (no # or quotes)
# Get ID: Right-click channel → Copy Channel ID (requires Developer Mode enabled)
SOLAR_POST_CHANNEL_ID=1234567890123456789
XKCD_POST_CHANNEL_ID=1234567890123456789
COMIC_POST_CHANNEL_ID=1234567890123456789
NEWS_CYBERSECURITY_CHANNEL_ID=1234567890123456789
NEWS_KEV_CHANNEL_ID=1234567890123456789
EOF

# 2. Run with docker-compose
docker compose up -d

# 3. Check logs
docker compose logs -f
```

**Or use the pre-built image:**

```bash
docker run -d --name penguin-overlord \
  --env-file .env \
  -v $(pwd)/events:/app/events:ro \
  ghcr.io/chiefgyk3d/penguin-overlord:latest
```

### Option 2: Python (Development)

```bash
# 1. Clone repository
git clone https://github.com/ChiefGyk3D/penguin-overlord.git
cd penguin-overlord

# 2. Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Create .env file
./scripts/create-secrets.sh

# 5. Run the bot
cd penguin-overlord
python bot.py
```

### Option 3: systemd Service (Production)

```bash
# Install as system service (run as your user, not with sudo!)
./scripts/install-systemd.sh

# Choose deployment mode:
# 1 = Python with venv
# 2 = Docker container

# The script will prompt for sudo password when needed
# Service will auto-start on boot!
# Services now run with correct user permissions (no more --user 0:0 issues)
```

## 📚 Documentation

- **[DEPLOYMENT.md](DEPLOYMENT.md)** - Comprehensive deployment guide
- **[SECRETS_QUICK_REFERENCE.md](SECRETS_QUICK_REFERENCE.md)** - All secret management options
- **[GET_DISCORD_TOKEN.md](GET_DISCORD_TOKEN.md)** - How to get a Discord bot token
- **[DOPPLER_SETUP.md](DOPPLER_SETUP.md)** - Doppler secrets manager setup

## 🔐 Secret Management

The bot supports 5 different secret management methods (checked in priority order):

1. **Doppler** - Production recommended (`DOPPLER_TOKEN`)
2. **AWS Secrets Manager** - Enterprise (`SECRETS_MANAGER=aws`)
3. **HashiCorp Vault** - Enterprise (`SECRETS_MANAGER=vault`)
4. **Environment Variables** - Simple (`DISCORD_BOT_TOKEN`)
5. **.env File** - Development (automatic via python-dotenv)

See [SECRETS_QUICK_REFERENCE.md](SECRETS_QUICK_REFERENCE.md) for detailed examples.

### 📋 Channel ID Formatting (IMPORTANT!)

All channel IDs in `.env` or Doppler **must be numeric only** - no symbols, no quotes:

✅ **Correct:**
```bash
NEWS_CYBERSECURITY_CHANNEL_ID=1234567890123456789
SOLAR_POST_CHANNEL_ID=987654321098765432
XKCD_POST_CHANNEL_ID=1122334455667788990
```

❌ **Wrong:**
```bash
NEWS_CYBERSECURITY_CHANNEL_ID=#security-news          # Don't use channel name
NEWS_CYBERSECURITY_CHANNEL_ID="1234567890123456789"   # Don't use quotes
NEWS_CYBERSECURITY_CHANNEL_ID=<#1234567890123456789>  # Don't use Discord mention format
```

**How to get a channel ID:**
1. Enable Developer Mode: Discord Settings → Advanced → Developer Mode
2. Right-click any channel → Copy Channel ID
3. Paste the numeric ID (18-19 digits) into your `.env` file

## 🐳 Docker Images

Multi-architecture images available on GitHub Container Registry:

- `ghcr.io/chiefgyk3d/penguin-overlord:latest` - Latest stable
- `ghcr.io/chiefgyk3d/penguin-overlord:v1.0.0` - Specific version
- `ghcr.io/chiefgyk3d/penguin-overlord:main-sha-abc123` - Git commit

**Platforms:** `linux/amd64`, `linux/arm64`

**Security:** All system packages automatically upgraded during build (apt-get upgrade + dist-upgrade)

## 🔧 Development

### Project Structure

```
penguin-overlord/
├── .github/
│   └── workflows/           # CI/CD pipelines
│       ├── ci-tests.yml     # Python 3.10-3.14 testing, linting, security
│       └── docker-build-publish.yml  # Multi-arch Docker builds
├── penguin-overlord/
│   ├── bot.py               # Main bot entry point
│   ├── news_runner.py       # Standalone news fetcher for systemd
│   ├── cogs/                # Bot extensions/features
│   │   ├── xkcd.py          # XKCD commands
│   │   ├── xkcd_poster.py   # Automated XKCD posting
│   │   ├── comics.py        # Multi-source tech comics
│   │   ├── techquote.py     # Tech Quote commands (610+ quotes!)
│   │   ├── admin.py         # Admin & help commands (6 pages)
│   │   ├── cyberfortune.py  # Cyber fortune cookies
│   │   ├── manpage.py       # Random Linux commands (250+)
│   │   ├── patchgremlin.py  # Patch Gremlin fun
│   │   ├── radiohead.py     # Solar/HAM radio (NOAA APIs)
│   │   ├── planespotter.py  # Aviation frequencies
│   │   ├── sigint.py        # SIGINT resources
│   │   ├── eventpinger.py   # Event reminders (CSV-based)
│   │   ├── source_code.py   # GitHub link
│   │   ├── news_manager.py  # News admin commands (/news)
│   │   ├── cybersecurity_news.py  # Cybersecurity feeds (18 sources)
│   │   ├── tech_news.py     # Tech news feeds (23 sources)
│   │   ├── gaming_news.py   # Gaming news feeds (17 sources)
│   │   ├── apple_google.py  # Apple & Google news (10 sources)
│   │   ├── cve.py           # CVE & security alerts (6 sources)
│   │   ├── us_legislation.py  # US tech legislation (7 sources)
│   │   ├── eu_legislation.py  # EU tech regulation (3 sources)
│   │   └── general_news.py  # General news feeds (7 sources)
│   ├── social/              # Social platform integrations
│   │   ├── discord.py       # Discord webhook platform
│   │   └── matrix.py        # Matrix platform (future)
│   ├── utils/               # Utility modules
│   │   ├── config.py        # Configuration management
│   │   ├── secrets.py       # Secrets management (Doppler/AWS/Vault)
│   │   └── news_fetcher.py  # RSS feed fetching & HTML parsing
│   └── data/                # Runtime state & configuration
│       ├── news_config.json # News category configuration
│       └── *_state.json     # Per-category state files
├── events/                  # Event CSV files
│   └── security_and_ham_events_2026_with_types.csv
├── scripts/                 # Installation & management scripts
│   ├── install-systemd.sh   # systemd service installer
│   ├── uninstall-systemd.sh # Service removal
│   └── create-secrets.sh    # Interactive .env creator
├── Dockerfile               # Multi-stage Python 3.14-slim
├── docker-compose.yml       # Easy Docker deployment
├── requirements.txt         # Python dependencies
├── .env.example            # Example environment variables
├── DEPLOYMENT.md           # Deployment guide
├── SECRETS_QUICK_REFERENCE.md  # Secret management guide
└── README.md               # This file
```

### CI/CD Pipeline

**Automated Testing (Python 3.10-3.14):**
- Bot structure validation
- Import tests for all cogs
- Ruff linting
- Bandit security analysis
- Safety dependency checks

**Docker Builds:**
- Multi-architecture: amd64, arm64
- Trivy security scanning
- Auto-publish to ghcr.io on main branch
- Build-only for pull requests

### Adding New Features

To add a new feature/command set:

1. Create a new cog file in `penguin-overlord/cogs/`
2. Follow the pattern in existing cogs (e.g., `xkcd.py`)
3. The bot will automatically load it on startup!

Example cog structure:
```python
from discord.ext import commands

class MyCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    @commands.hybrid_command()
    async def mycommand(self, ctx):
        """My command description"""
        await ctx.send("Hello!")

async def setup(bot):
    await bot.add_cog(MyCog(bot))
```

### Running Tests

```bash
# Lint code
ruff check penguin-overlord/

# Security scan
bandit -r penguin-overlord/ -ll

# Dependency vulnerabilities
safety check --json

# Run all CI checks locally
pip install ruff bandit safety
ruff check penguin-overlord/
bandit -r penguin-overlord/ -ll
safety check
```

### Current Features (40+ Commands, 20+ Cogs)
- ✅ **Automated News Aggregation** (120+ sources, 11 categories including Vendor Alerts)
- ✅ **Dual KEV Sources** (CISA + Exploit-DB for comprehensive vulnerability tracking)
- ✅ **XKCD** comic integration with search & automated posting
- ✅ **Tech Comics** (Joy of Tech, TurnOff.us, XKCD) with duplicate prevention
- ✅ **Tech Quote of the Day** (610+ quotes from 70+ tech legends)
- ✅ **Interactive paginators** (quotes, events, help)
- ✅ **Hybrid commands** (both prefix and slash commands)
- ✅ **Doppler/AWS/Vault** secrets management
- ✅ **Enhanced Solar weather & HAM radio** (improved propagation math, physics-based predictions)
- ✅ **Aviation frequencies & SIGINT resources**
- ✅ **Event reminder system** (29 events, CSV-based)
- ✅ **Fun commands** (fortune, manpage, patch gremlin)
- ✅ **6-page paginated help system**
- ✅ **Docker multi-arch support** (amd64, arm64) with improved permission handling
- ✅ **CI/CD with GitHub Actions**
- ✅ **systemd service support** with timers and user-based installation

### Future Features
- 🔲 Matrix bot integration
- 🔲 Scheduled daily tech quotes
- 🔲 Automated event reminders (cron-based)
- 🔲 More SIGINT frequency databases
- 🔲 Games and interactive features
- 🔲 Moderation tools
- 🔲 Custom per-server configurations

## 🤝 Contributing

Contributions are welcome! Here's how you can help:

1. **Fork the repository**
2. **Create a feature branch** (`git checkout -b feature/amazing-feature`)
3. **Make your changes** (follow existing code style)
4. **Test locally** (ensure bot runs and commands work)
5. **Commit your changes** (`git commit -m 'Add amazing feature'`)
6. **Push to your branch** (`git push origin feature/amazing-feature`)
7. **Open a Pull Request**

### Contribution Guidelines

- Follow PEP 8 style guidelines
- Use type hints where possible
- Add docstrings to new functions/commands
- Test your changes before submitting
- Update documentation if needed

## 🆘 Support

If you encounter any issues or have questions:

1. **Check Documentation**: Review [DEPLOYMENT.md](DEPLOYMENT.md) and [SECRETS_QUICK_REFERENCE.md](SECRETS_QUICK_REFERENCE.md)
2. **Bot Token**: Verify your Discord bot token is correct
3. **Permissions**: Ensure bot has necessary Discord server permissions
4. **Console Logs**: Check logs for error messages
5. **Message Intent**: Enable "Message Content Intent" in Discord Developer Portal
6. **Open an Issue**: If problems persist, [open a GitHub issue](https://github.com/ChiefGyk3D/penguin-overlord/issues)

## 📜 License

This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
If a copy of the MPL was not distributed with this file, You can obtain one at https://mozilla.org/MPL/2.0/.

---

## 💝 Donations and Tips

If you find Penguin Overlord useful, consider supporting development:

**Donate**:

<div align="center">
  <table>
    <tr>
      <td align="center"><a href="https://patreon.com/chiefgyk3d?utm_medium=unknown&utm_source=join_link&utm_campaign=creatorshare_creator&utm_content=copyLink" title="Patreon"><img src="https://cdn.jsdelivr.net/gh/simple-icons/simple-icons/icons/patreon.svg" width="32" height="32" alt="Patreon"/></a></td>
      <td align="center"><a href="https://streamelements.com/chiefgyk3d/tip" title="StreamElements"><img src="media/streamelements.png" width="32" height="32" alt="StreamElements"/></a></td>
    </tr>
    <tr>
      <td align="center">Patreon</td>
      <td align="center">StreamElements</td>
    </tr>
  </table>
</div>

### Cryptocurrency Tips

<div align="center">
  <table style="border:none;">
    <tr>
      <td align="center" style="padding:8px; min-width:120px;">
        <img src="https://cdn.jsdelivr.net/gh/simple-icons/simple-icons/icons/bitcoin.svg" width="28" height="28" alt="Bitcoin"/>
      </td>
      <td align="left" style="padding:8px;">
        <b>Bitcoin</b><br/>
        <code style="font-size:12px;">bc1qztdzcy2wyavj2tsuandu4p0tcklzttvdnzalla</code>
      </td>
    </tr>
    <tr>
      <td align="center" style="padding:8px; min-width:120px;">
        <img src="https://cdn.jsdelivr.net/gh/simple-icons/simple-icons/icons/monero.svg" width="28" height="28" alt="Monero"/>
      </td>
      <td align="left" style="padding:8px;">
        <b>Monero</b><br/>
        <code style="font-size:12px;">84Y34QubRwQYK2HNviezeH9r6aRcPvgWmKtDkN3EwiuVbp6sNLhm9ffRgs6BA9X1n9jY7wEN16ZEpiEngZbecXseUrW8SeQ</code>
      </td>
    </tr>
    <tr>
      <td align="center" style="padding:8px; min-width:120px;">
        <img src="https://cdn.jsdelivr.net/gh/simple-icons/simple-icons/icons/ethereum.svg" width="28" height="28" alt="Ethereum"/>
      </td>
      <td align="left" style="padding:8px;">
        <b>Ethereum</b><br/>
        <code style="font-size:12px;">0x554f18cfB684889c3A60219BDBE7b050C39335ED</code>
      </td>
    </tr>
  </table>
</div>

---

<div align="center">

Made with ❤️ by [ChiefGyk3D](https://github.com/ChiefGyk3D)

## 📚 Documentation

Complete documentation is available in the [`docs/`](docs/) directory:

- **[Full Documentation Index](docs/README.md)** - Complete navigation guide
- **[Quick Reference](QUICK_REFERENCE.md)** - Fast command lookup
- **[Setup Guides](docs/setup/)** - Discord setup, permissions, configuration
- **[Feature Guides](docs/features/)** - News system, HAM radio, and more
- **[Deployment](docs/deployment/)** - Production deployment and systemd
- **[Reference](docs/reference/)** - Channel configuration, RSS feeds, optimization
- **[Migration](docs/migration/)** - Breaking changes and upgrade guides

### Quick Links
- 🚀 **[Getting Started](docs/setup/DISCORD_SETUP.md)**
- 🔒 **[Secrets Management](docs/secrets/README.md)**
- 📰 **[News System Guide](docs/features/NEWS_SYSTEM.md)**
- ⚙️ **[Channel Configuration](docs/reference/CHANNEL_CONFIGURATION.md)**

---

## Author & Socials

<table>
  <tr>
    <td align="center"><a href="https://social.chiefgyk3d.com/@chiefgyk3d" title="Mastodon"><img src="https://cdn.jsdelivr.net/gh/simple-icons/simple-icons/icons/mastodon.svg" width="32" height="32" alt="Mastodon"/></a></td>
    <td align="center"><a href="https://bsky.app/profile/chiefgyk3d.com" title="Bluesky"><img src="https://cdn.jsdelivr.net/gh/simple-icons/simple-icons/icons/bluesky.svg" width="32" height="32" alt="Bluesky"/></a></td>
    <td align="center"><a href="http://twitch.tv/chiefgyk3d" title="Twitch"><img src="https://cdn.jsdelivr.net/gh/simple-icons/simple-icons/icons/twitch.svg" width="32" height="32" alt="Twitch"/></a></td>
    <td align="center"><a href="https://www.youtube.com/channel/UCvFY4KyqVBuYd7JAl3NRyiQ" title="YouTube"><img src="https://cdn.jsdelivr.net/gh/simple-icons/simple-icons/icons/youtube.svg" width="32" height="32" alt="YouTube"/></a></td>
    <td align="center"><a href="https://kick.com/chiefgyk3d" title="Kick"><img src="https://cdn.jsdelivr.net/gh/simple-icons/simple-icons/icons/kick.svg" width="32" height="32" alt="Kick"/></a></td>
    <td align="center"><a href="https://www.tiktok.com/@chiefgyk3d" title="TikTok"><img src="https://cdn.jsdelivr.net/gh/simple-icons/simple-icons/icons/tiktok.svg" width="32" height="32" alt="TikTok"/></a></td>
    <td align="center"><a href="https://discord.chiefgyk3d.com" title="Discord"><img src="https://cdn.jsdelivr.net/gh/simple-icons/simple-icons/icons/discord.svg" width="32" height="32" alt="Discord"/></a></td>
    <td align="center"><a href="https://matrix-invite.chiefgyk3d.com" title="Matrix"><img src="https://cdn.jsdelivr.net/gh/simple-icons/simple-icons/icons/matrix.svg" width="32" height="32" alt="Matrix"/></a></td>
  </tr>
  <tr>
    <td align="center">Mastodon</td>
    <td align="center">Bluesky</td>
    <td align="center">Twitch</td>
    <td align="center">YouTube</td>
    <td align="center">Kick</td>
    <td align="center">TikTok</td>
    <td align="center">Discord</td>
    <td align="center">Matrix</td>
  </tr>
</table>

</div>
