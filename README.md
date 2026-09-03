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

- `XKCD_POST_CHANNEL_ID`: Numeric channel ID where new comics will be posted. Example: `123456789012345678`
- `XKCD_POLL_INTERVAL_MINUTES`: How often to check for new comics (default: `30` minutes)

Admin runtime commands (owner or Manage Server permission required):

- `!xkcd_set_channel <#channel|channel_id>`: Set the automatic post channel
- `!xkcd_enable` / `!xkcd_disable`: Enable or disable the automatic poster
- `!xkcd_post_now`: Force-post the latest XKCD immediately

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
- `COMIC_POST_CHANNEL_ID`: Channel ID for daily comic posts (optional, can use runtime command)

Admin runtime commands (owner or Manage Server permission required):
- `!comic_set_channel <#channel>`: Set the daily comic channel
- `!comic_enable` / `!comic_disable`: Toggle daily posting (9 AM UTC)
- `!daily_comic`: Force post a comic immediately

**Comic Sources:**
- 🤓 **XKCD**: Tech, science, and cybersecurity humor (via JSON API: https://xkcd.com/info.0.json)
- 😂 **Joy of Tech**: Apple, Linux, and general geek culture (via https://www.joyoftech.com/joyoftech/jotblog/index.xml)
- 🔧 **TurnOff.us**: Git, DevOps, and programmer humor (via https://turnoff.us/feed.xml)

State persistence: Stored in `data/comic_state.json`

### 🎲 Fun Commands
- `!fortune` - Get a cybersecurity-themed fortune cookie
- `!manpage` - Get a random Linux command from the manpage (250+ commands)
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
- `!hamradio` - Random HAM radio facts and trivia

**Recent improvements**: Enhanced propagation math and physics calculations, improved D-layer absorption modeling, refined MUF calculations for better HF band predictions, fixed 80m band status emoji display, and improved automated solar report posting reliability. Physics-based propagation uses MUF calculations, D-layer absorption modeling, gray line detection, K-index frequency-dependent impact, and seasonal Sporadic-E predictions. **Includes visual maps** from NOAA showing real-time HF absorption, aurora position, and solar activity. **Automated reports post every 30 minutes** with full physics-based calculations including X-ray flux, D-RAP, and Aurora forecast charts. **NEW:** Grid square tools for VHF/UHF contesting, satellite tracking, contest calendar, and repeater directory! See [docs/features/RADIOHEAD_HAM_RADIO.md](docs/features/RADIOHEAD_HAM_RADIO.md) for details.

### ✈️ Aviation (Planespotter)
Aviation frequencies and resources!
- `!avfreq` - Aviation frequencies (tower, ground, approach, departure, etc.)
- `!squawk [code]` - What a transponder squawk code means
- `!aircraft` - Aircraft type information
- `!avfact` - Aviation trivia

### 📡 SIGINT Resources
Intelligence and monitoring resources!
- `!frequency_log` - Interesting frequencies to monitor
- `!sdrtool` - SDR decoder tools and software
- `!sigintfact` - SIGINT facts and tips

### 🤖 AI Features (Ollama, local-first)

Optional AI subsystem backed by your own Ollama server; **everything is off
by default** and the bot behaves exactly as before until you opt in.

- **AI Arch roasts**: contextual, guardrailed roasts when someone mentions
  Arch (btw); the static joke list remains the fallback for every failed or
  blocked generation
- **Two-stage alert-first moderation**: regex PII/slur/dog-whistle scanning,
  a Llama Guard primary verdict, and a context-capable second model for the
  judgement calls: reclaimed in-group language vs. an attack, public vs.
  private addresses, coded hate signals vs. ham radio's "73 and 88", and
  educational security talk vs. targeting a real person. Edited messages are
  rescanned. Dry-run by default: no automatic actions, ever, until you
  graduate it
- **Community profiles**: `MOD_PROFILE=cybersecurity,hobbyist` tells the
  model what counts as normal talk in *your* server (IPs and exploit
  discussion; locksport, radio, lawful firearms) and profiles compose. No
  profile can relax hate speech, harassment, self-harm, or sexual content;
  that floor is clamped in code
- **Trust tiers**: new → member → veteran by tenure, trusted/creator by
  role, shared across features; alerts show the tier so mods can weigh a
  2-year regular differently from a 2-day-old account
- **Attack labeling**: prompt-injection and filter-evasion attempts
  (zero-width characters, homoglyphs, "ignore all previous instructions")
  are named on the alert and flagged as `prompt_injection` even when they
  carry no slur or PII
- **Moderator calibration workflow**: alerts carry Approve / Dismiss
  controls plus a category select for relabeling a true positive that was
  tagged wrong; `MOD_REVIEW_VOTES=2+` turns clicks into votes with a live
  tally. Every label feeds `/mod stats` and the future fine-tune
- **Newcomer helper**: optionally points brand-new members at your rules
  and resources channels when they ask where to start, with cooldowns and
  a false-positive-averse matcher ([guide](docs/features/NEWCOMER_HELPER.md))
- **Profile screen**: usernames, display names and nicknames get the same
  look messages do, at join and on every change; a flag holds the welcome
  and posts a Ban / Kick / Dismiss card to the mod channel, and
  `/profile sync-automod` mirrors the term list into a Discord AutoMod
  member-profile rule so bios (which no bot can read) are covered too
- **Privacy floor**: moderation inference never leaves your network (the
  remote fallback is hard-disabled for moderation in code), and nothing the
  bot posts to Discord ever contains an endpoint address: private hosts
  read `RFC1918`, public IPs are withheld, known APIs are named
- **Prometheus metrics**: `METRICS_ENABLED=true` exposes gateway, AI,
  moderation, adjudication, and attack-marker series plus a real container
  healthcheck

**Commands:** `/mod status`, `/mod stats`, `/mod pending`, `/mod benchmark`,
`/mod test`, `/mod purge_user`

Per-feature models and hosts are configurable (e.g. roasting on
`gemma4:12b`, moderation on `llama-guard3:8b` + `gemma4:12b` second stage).
See the [AI features operator guide](docs/features/AI_MODERATION.md) for
setup, guardrails, and the calibration workflow.

### 📰 Automated News Aggregation (220+ sources, 11 categories)

The bot features a comprehensive automated news system that aggregates and posts news from 220+ RSS feeds across 11 categories.

**News Categories:**
- 🔒 **Cybersecurity** (115 sources) - TheHackerNews, Krebs on Security, Troy Hunt, Security Affairs, NCSC (UK), Google Security, Sophos, Trend Micro, Dark Reading, Schneier, and more
- 💻 **Tech** (17 sources) - Ars Technica, The Verge, TechCrunch, Wired, Engadget, ZDNet, BBC Technology, BBC Science, and more
- 🎮 **Gaming** (10 sources) - IGN, Polygon, Kotaku, PC Gamer, GameSpot, and more
- 🍎 **Apple & Google** (25 sources) - 9to5Mac, 9to5Google, MacRumors, Android Police, and more
- 🛡️ **CVE Vulnerabilities** (6 sources) - National Vulnerability Database, Ubuntu Security Notices, and the Polish, French, Canadian, and Japanese CERTs (general awareness)
- 🚨 **KEV - Known Exploited** (2 sources) - CISA Known Exploited Vulnerabilities (CRITICAL: actively exploited), Exploit-DB RSS (HIGH: exploit code available)
- 🏛️ **US Legislation** (4 sources) - Congressional tech/privacy/security bills from Congress.gov (cleaned HTML presentation)
- 🇪🇺 **EU Legislation** (3 sources) - EU tech regulation from EUR-Lex
- 🇬🇧 **UK Legislation** (1 source) - UK Parliament All Bills (public + private combined)
- 📰 **General News** (12 sources) - NPR, PBS, Financial Times, Reuters, BBC News (UK, World, Politics, Health), and more
- 🚨 **Vendor Alerts** (34 sources) - AWS Service Health, Azure Status, Google Cloud Status, Cloudflare, GitHub, Datadog, PagerDuty, Atlassian Status, and more

**Manual Commands:**
- `/news status <category>` - Check a category's channel, interval, and sources
- `/news enable <category>` / `/news disable <category>` - Turn auto-posting on or off
- `/news set_channel <category> <#channel>` - Set posting channel for a category
- `/news toggle_source <category> <source>` - Enable or disable one feed
- `/cybersecurity <source>`, `/tech <source>`, `/gaming <source>`, ... - Fetch one source on demand (full list in [docs/reference/COMMANDS.md](docs/reference/COMMANDS.md))

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

### 📅 Events
A crowd-sourced calendar of cyber, ham, and FOSS events with a moderator
approval queue. Members opt in by topic and region through the role picker
and get channel reminders 30, 7, and 1 days out that tag those roles.
- `/events list [topic] [where] [page]` - the year ahead, filtered
- `/events next` - the next 30 days
- `/events search <query>` - by title or city
- `/events submit` - propose one; moderators approve it from a review card
- `/events mine` - your submissions and their status

See **[Events Guide](docs/features/EVENTS.md)** for setup, moderation, and the one-time import.

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
  -v penguin-data:/app/data \
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

Complete documentation lives in the [`docs/`](docs/) directory:

- **[Full Documentation Index](docs/README.md)** - Complete navigation guide
- **[Command Reference](docs/reference/COMMANDS.md)** - Every command, its arguments, permission, and env gate
- **[Roadmap](docs/ROADMAP.md)** - What is requested, in flight, and needed structurally
- **[Quick Reference](QUICK_REFERENCE.md)** - Fast setup and command lookup
- **[Setup Guides](docs/setup/)** - Discord setup, permissions, configuration
- **[Feature Guides](docs/features/)** - AI moderation, news system, HAM radio, and more
- **[Deployment](docs/deployment/)** - Production deployment and systemd
- **[Reference](docs/reference/)** - Channel configuration, RSS feeds, optimization
- **[Archive](docs/archive/)** - Historical docs, kept for reference

### Quick Links

- 🚀 **[Getting Started](docs/setup/DISCORD_SETUP.md)**
- 🔒 **[Secrets Management](docs/secrets/README.md)** (Doppler, Vault, AWS, env, `.env`)
- 🛡️ **[AI Moderation Guide](docs/features/AI_MODERATION.md)**
- 📰 **[News System Guide](docs/features/NEWS_SYSTEM.md)**
- ⚙️ **[Channel Configuration](docs/reference/CHANNEL_CONFIGURATION.md)**
- 🪵 **[Logging & rotation](docs/reference/LOGGING.md)**
- ✅ **[Configuration & startup validation](docs/reference/CONFIGURATION.md)**
- 🚢 **[Production Deployment](docs/deployment/PRODUCTION.md)** · [systemd](docs/deployment/SYSTEMD.md)

## 🔐 Secret Management

The bot supports 5 different secret management methods (checked in priority order):

1. **Doppler** - Production recommended (`DOPPLER_TOKEN`)
2. **AWS Secrets Manager** - Enterprise (`SECRETS_MANAGER=aws`)
3. **HashiCorp Vault** - Enterprise (`SECRETS_MANAGER=vault`)
4. **Environment Variables** - Simple (`DISCORD_BOT_TOKEN`)
5. **.env File** - Development (automatic via python-dotenv)

See the [secrets guide](docs/secrets/README.md) for detailed examples.

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
├── .github/workflows/
│   ├── ci-tests.yml            # ruff, bandit, pytest with a coverage floor
│   └── docker-build-publish.yml  # Multi-arch image to GHCR
├── penguin-overlord/
│   ├── bot.py                  # Main bot entry point (auto-loads cogs/)
│   ├── news_runner.py          # One news category per run, for systemd timers
│   ├── kev_runner.py           # Same idea for KEV, solar, XKCD, and comics
│   ├── solar_runner.py
│   ├── xkcd_runner.py
│   ├── comics_runner.py
│   ├── cogs/                   # 34 cogs; the command reference lists them
│   │   ├── admin.py, help_categorized.py     # help, sync, source_code
│   │   ├── ai_moderation.py, profile_screen.py, rules_sync.py
│   │   ├── welcome_greeter.py, newcomer_helper.py, role_picker.py
│   │   ├── arch_banter.py, skid_detector.py  # the roasters
│   │   ├── news_manager.py     # /news config hub for the 11 categories
│   │   ├── cybersecurity_news.py, tech_news.py, gaming_news.py,
│   │   │   apple_google_news.py, general_news.py, vendor_alerts.py,
│   │   │   us_legislation.py, eu_legislation.py, uk_legislation.py,
│   │   │   cve.py, kev.py
│   │   ├── radiohead.py, planespotter.py, sigint.py
│   │   ├── xkcd.py, xkcd_poster.py, comics.py, techquote.py
│   │   ├── fortune.py, manpage.py, patchgremlin.py, events.py
│   │   └── metrics.py          # Prometheus exporter
│   ├── ai/                     # Ollama/Gemini manager, guardrails, queue
│   │   └── features/           # moderation, profiles, arch_roaster, skid_roaster
│   ├── assets/                 # Shipped data (role panels, images)
│   ├── utils/                  # secrets, state, database, trust, news_fetcher,
│   │                           # news_dedupe, logging_setup, metrics
│   └── data/                   # Runtime state (bind-mounted in Docker)
├── events/                     # Seed CSV for the one-time events import
├── tests/unit/                 # pytest suite
├── scripts/                    # install-systemd.sh, build-and-transfer.sh,
│                               # healthcheck.py, feed-check/, eval-moderation
├── docs/                       # Setup, features, deployment, reference
├── Dockerfile, docker-compose.yml, docker-compose.macvlan.example.yml
├── requirements.txt, .env.example
└── README.md
```

### CI/CD Pipeline

**Automated Testing (Python 3.10-3.13, 3.14 experimental):**
- pytest suite in `tests/unit/` with a coverage floor (a required check)
- Ruff linting
- Bandit security analysis (high severity fails the build)
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
# Unit and regression tests (what CI gates on)
python3 -m pytest tests/unit -q

# Skip the tests that need the network
python3 -m pytest tests/ -m "not network" -q

# Lint and security scan
ruff check penguin-overlord/
bandit -r penguin-overlord/ -ll
safety check
```

New behaviour comes with a test in `tests/unit/`; the moderation golden set
lives at `penguin-overlord/ai/moderation_golden.json` and `/mod benchmark`
runs it against the live models.

### Current Features (100+ commands, 34 cogs; see [docs/reference/COMMANDS.md](docs/reference/COMMANDS.md))
- ✅ **Automated News Aggregation** (220+ sources, 11 categories including Vendor Alerts)
- ✅ **Dual KEV Sources** (CISA + Exploit-DB for comprehensive vulnerability tracking)
- ✅ **XKCD** comic integration with search & automated posting
- ✅ **Tech Comics** (Joy of Tech, TurnOff.us, XKCD) with duplicate prevention
- ✅ **Tech Quote of the Day** (610+ quotes from 70+ tech legends)
- ✅ **Interactive paginators** (quotes, help)
- ✅ **Hybrid commands** (both prefix and slash commands)
- ✅ **Doppler/AWS/Vault** secrets management
- ✅ **Enhanced Solar weather & HAM radio** (improved propagation math, physics-based predictions)
- ✅ **Aviation frequencies & SIGINT resources**
- ✅ **Events calendar**: member submissions, moderator review cards, reminders that tag the picker roles, Monday digest ([guide](docs/features/EVENTS.md))
- ✅ **Fun commands** (fortune, manpage, patch gremlin)
- ✅ **Categorized help** (nine dropdown pages; `!help_old` keeps the paginated version)
- ✅ **Docker multi-arch support** (amd64, arm64) with improved permission handling
- ✅ **CI/CD with GitHub Actions**
- ✅ **systemd service support** with timers and user-based installation
- ✅ **AI subsystem (Ollama-first)**: Arch and NixOS roasts, the Skid Detector, and two-stage alert-first moderation with trust tiers, community profiles, dog-whistle watchlist, attack labeling, moderator voting/relabeling, hard guardrails, per-feature models
- ✅ **Newcomer helper**: configurable welcome pointer to rules/resources with cooldowns
- ✅ **Welcome greeter and rules sync**: batched daily greetings on join and on verify; #rules read into the moderation prompt
- ✅ **Profile screen**: display names screened at join and on change, mod card with Ban/Kick/Dismiss, AutoMod member-profile rule for bios
- ✅ **Role picker**: self-roles by country, US state, and Canadian province as persistent dropdowns, provisioned by `/roles post` ([guide](docs/features/ROLE_PICKER.md))
- ✅ **Prometheus metrics** endpoint with a real gateway healthcheck

### What is next

The ordered list lives in [docs/ROADMAP.md](docs/ROADMAP.md). The short version:
- 🔲 Events phase 2: Gemini-backed date verification and discovery of new events (spec section 10)
- 🔲 Alert subscription roles for CVE, KEV, breaches, and legislation (#25) and a dedicated breach channel (#24)
- 🔲 Moderation enforcement graduation (timeouts and warnings from calibration data; alert-first phase shipped)
- 🔲 Quiz bot (#14)
- 🔲 Split the news aggregator from the community bot before the cloud move

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

1. **Check Documentation**: Review the [deployment guide](docs/deployment/PRODUCTION.md) and the [secrets guide](docs/secrets/README.md)
2. **Bot Token**: Verify your Discord bot token is correct
3. **Permissions**: Ensure bot has necessary Discord server permissions
4. **Console Logs**: Check logs for error messages
5. **Message Intent**: Enable "Message Content Intent" in Discord Developer Portal
6. **Open an Issue**: If problems persist, [open a GitHub issue](https://github.com/ChiefGyk3D/penguin-overlord/issues)

## 📜 License

This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
If a copy of the MPL was not distributed with this file, You can obtain one at https://mozilla.org/MPL/2.0/.

---

## 💝 Support This Project

If you find Penguin Overlord useful, consider supporting continued development.
Everything is also collected at **[support.chiefgyk3d.com](https://support.chiefgyk3d.com)**.

### Recurring Support

<div align="center">
<table>
  <tr>
    <td align="center" width="150">
      <a href="https://patreon.com/chiefgyk3d" title="Patreon">
        <img src="media/icons/patreon.svg" width="36" height="36" alt="Patreon"><br>
        <sub><b>Patreon</b></sub>
      </a>
    </td>
    <td align="center" width="150">
      <a href="https://streamelements.com/chiefgyk3d/tip" title="StreamElements">
        <img src="media/streamelements.png" width="36" height="36" alt="StreamElements"><br>
        <sub><b>StreamElements</b></sub>
      </a>
    </td>
    <td align="center" width="150">
      <a href="https://shop.chiefgyk3d.com/" title="Merch Store">
        <img src="media/icons/merch.svg" width="36" height="36" alt="Merch"><br>
        <sub><b>Merch Store</b></sub>
      </a>
    </td>
  </tr>
</table>
</div>

### Cryptocurrency Tips

<div align="center">
<table>
  <tr>
    <td align="center" width="60"><img src="media/icons/bitcoin.svg" width="28" height="28" alt="Bitcoin"></td>
    <td><b>Bitcoin</b><br><code>bc1qztdzcy2wyavj2tsuandu4p0tcklzttvdnzalla</code></td>
  </tr>
  <tr>
    <td align="center" width="60"><img src="media/icons/monero.svg" width="28" height="28" alt="Monero"></td>
    <td><b>Monero</b><br><code>84Y34QubRwQYK2HNviezeH9r6aRcPvgWmKtDkN3EwiuVbp6sNLhm9ffRgs6BA9X1n9jY7wEN16ZEpiEngZbecXseUrW8SeQ</code></td>
  </tr>
  <tr>
    <td align="center" width="60"><img src="media/icons/ethereum.svg" width="28" height="28" alt="Ethereum"></td>
    <td><b>Ethereum</b><br><code>0x554f18cfB684889c3A60219BDBE7b050C39335ED</code></td>
  </tr>
  <tr>
    <td align="center" width="60"><img src="media/icons/solana.svg" width="28" height="28" alt="Solana"></td>
    <td><b>Solana</b><br><code>5T8h3HbyvHgLxwXgchRYbHSqRjZyAr8J7uwjLN9Fh8Jh</code></td>
  </tr>
</table>
</div>

---

## 👤 Author & Socials

<div align="center">
<table>
  <tr>
    <td align="center" width="90"><a href="https://social.chiefgyk3d.com/@chiefgyk3d" title="Mastodon"><img src="media/icons/mastodon.svg" width="30" height="30" alt="Mastodon"><br><sub>Mastodon</sub></a></td>
    <td align="center" width="90"><a href="https://bsky.app/profile/chiefgyk3d.com" title="Bluesky"><img src="media/icons/bluesky.svg" width="30" height="30" alt="Bluesky"><br><sub>Bluesky</sub></a></td>
    <td align="center" width="90"><a href="https://twitch.tv/chiefgyk3d" title="Twitch"><img src="media/icons/twitch.svg" width="30" height="30" alt="Twitch"><br><sub>Twitch</sub></a></td>
    <td align="center" width="90"><a href="https://www.youtube.com/channel/UCvFY4KyqVBuYd7JAl3NRyiQ" title="YouTube"><img src="media/icons/youtube.svg" width="30" height="30" alt="YouTube"><br><sub>YouTube</sub></a></td>
    <td align="center" width="90"><a href="https://kick.com/chiefgyk3d" title="Kick"><img src="media/icons/kick.svg" width="30" height="30" alt="Kick"><br><sub>Kick</sub></a></td>
    <td align="center" width="90"><a href="https://www.tiktok.com/@chiefgyk3d" title="TikTok"><img src="media/icons/tiktok.svg" width="30" height="30" alt="TikTok"><br><sub>TikTok</sub></a></td>
    <td align="center" width="90"><a href="https://discord.chiefgyk3d.com" title="Discord"><img src="media/icons/discord.svg" width="30" height="30" alt="Discord"><br><sub>Discord</sub></a></td>
    <td align="center" width="90"><a href="https://matrix-invite.chiefgyk3d.com" title="Matrix"><img src="media/icons/matrix.svg" width="30" height="30" alt="Matrix"><br><sub>Matrix</sub></a></td>
  </tr>
</table>
</div>

<div align="center"><sub>Made with ❤️ by <a href="https://github.com/ChiefGyk3D">ChiefGyk3D</a></sub></div>
