# 🐧 Penguin Overlord Documentation

<div align="center">
  <img src="../media/banner_wide.png" alt="Penguin Overlord Banner" width="800"/>
  
  **Complete documentation for the Penguin Overlord Discord Bot**
  
  *For hackers, HAMs, and hobbyists*
</div>

---

## 📚 Quick Navigation

- **[Roadmap](ROADMAP.md)** - open requests from issues, what is in flight, and the structural work, in order

### 🚀 Getting Started
- **[Discord Setup](setup/DISCORD_SETUP.md)** - Create your bot and get tokens
- **[Permissions Guide](setup/PERMISSIONS.md)** - Required Discord permissions
- **[Secrets Management](secrets/README.md)** - Configure credentials securely

### ✨ Features
- **[AI Features](features/AI_MODERATION.md)** - Arch roasts and two-stage alert-first moderation: trust tiers, community profiles, dog-whistle watchlist, moderator voting and relabeling
- **[Newcomer Helper](features/NEWCOMER_HELPER.md)** - points new members at your resources channel
- **Skid Detector** - the script-kiddie alarm; roasts the energy, then points at the real path (section in the AI guide)
- **Profile screen** - display names screened at join and on change, greeter hold, mod card, AutoMod member-profile rule for bios (section in the AI guide)
- **Welcome greeter & rules sync** - two-stage greeting: a Micro Center welcome in #welcome-newbies on join (with the verify steps), then a Costco/Idiocracy intro in #general once they verify; each batched, deduped, and greeted once. Plus daily #rules sync into the moderation prompt (see `.env.example`)
- **[Role Picker](features/ROLE_PICKER.md)** - MEE6-style self-roles as persistent dropdown panels (country, US state, Canadian province), roles provisioned from JSON
- **[Role Management Notes](features/ROLE_MANAGEMENT_NOTES.md)** - future work: the rest of taking over from MEE6 (autorole, levelling)
- **[News System](features/NEWS_SYSTEM.md)** - 220+ sources across 11 categories
- **[News Categories](features/NEWS_CATEGORIES_OVERVIEW.md)** - Detailed category breakdown
- **[Phase 3 enforcement spec](features/PHASE3_ENFORCEMENT_SPEC.md)** and **[moderation fine-tune plan](features/MODERATION_FINETUNE_PLAN.md)** - what graduating moderation out of dry-run looks like (not implemented yet)

### 🚢 Deployment
- **[Production Deployment](deployment/PRODUCTION.md)** - Deploy to production
- **[Systemd Setup](deployment/SYSTEMD.md)** - Run as a Linux service
- **[Build and Transfer](deployment/BUILD_AND_TRANSFER.md)** - Build the image here, load it on an offline box
- **[Docker Volume Permissions](deployment/DOCKER_VOLUME_PERMISSIONS.md)** - The non-root container user and the data volume

### 📖 Reference
- **[Command Reference](reference/COMMANDS.md)** - Every command grouped by feature: arguments, permission, env gate
- **[Channel Configuration](reference/CHANNEL_CONFIGURATION.md)** - Every channel environment variable
- **[RSS Feeds](reference/RSS_FEEDS.md)** - Complete feed list and API information
- **[News Optimization](reference/NEWS_OPTIMIZATION.md)** - Performance tuning guide
- **[Help System](reference/HELP_SYSTEM.md)** - Using the categorized help system
- **[Logging](reference/LOGGING.md)** - Log levels, rotation, and what to grep for
- **[Configuration](reference/CONFIGURATION.md)** - How env vars are loaded and validated, `check-config.py`, adding a variable

### 📦 Archive
Historical documentation, kept for reference and not to be followed:
- [August 2026 assessment](ASSESSMENT_AND_AI_ROADMAP.md) - the review that produced the current roadmap; its roadmap half is superseded by [ROADMAP.md](ROADMAP.md)
- [November 2025 breaking changes](archive/NOVEMBER_2025_BREAKING_CHANGES.md)
- [Documentation housekeeping plan](archive/DOCUMENTATION_HOUSEKEEPING_PLAN.md) - done
- [Doppler Integration History](archive/DOPPLER_INTEGRATION.md)
- [More archived docs...](archive/)

---

## 🎯 Common Tasks

### Setting Up Your Bot
1. [Get Discord Bot Token](setup/DISCORD_SETUP.md#getting-your-token)
2. [Configure Secrets](secrets/README.md#quick-start)
3. [Set Channel IDs](reference/CHANNEL_CONFIGURATION.md#env-configuration-examples)
4. [Enable Auto-Posting](features/NEWS_SYSTEM.md)

### Configuring News
1. [Choose News Categories](features/NEWS_CATEGORIES_OVERVIEW.md)
2. [Set Channel Environment Variables](reference/CHANNEL_CONFIGURATION.md)
3. [Enable Categories](reference/CHANNEL_CONFIGURATION.md#configuration-priority)
4. [Optimize Performance](reference/NEWS_OPTIMIZATION.md)

### Deploying to Production
1. [Choose Deployment Method](deployment/PRODUCTION.md)
2. [Setup Systemd Service](deployment/SYSTEMD.md)
3. [Configure Auto-Start](deployment/SYSTEMD.md#enabling-auto-start)

---

## 📋 Feature Overview

### 💬 Comics & Fun
- **XKCD Comics** - Auto-post new comics (disabled by default)
- **Daily Tech Comics** - XKCD, Joy of Tech, and TurnOff.us in rotation
- **Tech Quotes** - 610+ quotes from 70+ tech legends

### 📰 News Aggregation (220+ sources, 11 categories)
- **Cybersecurity** (115 sources) - Krebs, Dark Reading, Schneier, HIBP, vendor research blogs
- **Technology** (17 sources) - Ars Technica, The Verge, TechCrunch, BBC Technology
- **Gaming** (10 sources) - IGN, Kotaku, PC Gamer
- **Apple & Google** (25 sources) - 9to5Mac, Android Police, MacRumors
- **CVE** (6 sources) - NVD, Ubuntu Security Notices, four national CERTs
- **KEV** (2 sources) - CISA Known Exploited Vulnerabilities, Exploit-DB
- **US Legislation** (4 sources) - Congress.gov floor activity, GovInfo bills
- **EU Legislation** (3 sources) - EUR-Lex
- **UK Legislation** (1 source) - Parliament bills
- **General News** (12 sources) - NPR, PBS, Financial Times, BBC
- **Vendor Alerts** (34 sources) - cloud and SaaS status pages, security advisories

### 📻 HAM Radio
- **Solar Weather** - Live data from NOAA SWPC
- **Propagation Reports** - Band-by-band predictions
- **Auto-Posting** - Solar reports every 12 hours from the in-bot loop, or every 30 minutes from the `solar_runner.py` timer

### ✈️ Aviation
- **Squawk Codes** - Transponder code lookup
- **Aircraft Info** - Random aircraft facts
- **Frequencies** - Aviation radio bands

### 🔍 SIGINT
- **Frequency Logs** - Interesting frequencies to monitor
- **SDR Tools** - Software-defined radio decoders
- **Tips & Tricks** - Signal intelligence resources

### 📅 Events
- **Conference Tracking** - DEF CON, BSides, Hamvention, etc.
- **Countdown Timers** - Days until next event
- **Search & Filter** - Find events by name/location/type

### 🛠️ Utilities
- **Fortune Cookies** - Cyber-themed fortune cookies
- **Man Pages** - Random Linux command explanations
- **Patch Gremlin** - Update reminders

---

## 🔒 Security & Secrets

Penguin Overlord supports multiple secrets management solutions:

### Supported Providers
- **[Doppler](secrets/README.md#doppler-secrets-manager)** - Recommended for production
- **[AWS Secrets Manager](secrets/README.md#aws-secrets-manager)** - For AWS deployments
- **[HashiCorp Vault](secrets/README.md#hashicorp-vault)** - For enterprise environments
- **[.env Files](secrets/README.md#environment-variables)** - For local development

### Priority Order
1. Doppler (if `DOPPLER_TOKEN` set)
2. AWS Secrets Manager (if `SECRETS_MANAGER=aws`)
3. HashiCorp Vault (if `SECRETS_MANAGER=vault`)
4. Environment Variables (.env file)

---

## 📊 Configuration Reference

### Environment Variables

#### Required
```bash
DISCORD_BOT_TOKEN=your_bot_token_here
DISCORD_OWNER_ID=your_discord_user_id
```

#### Optional - Comics & Fun
```bash
XKCD_POST_CHANNEL_ID=123456789012345678
COMIC_POST_CHANNEL_ID=234567890123456789
```

#### Optional - HAM Radio
```bash
SOLAR_POST_CHANNEL_ID=345678901234567890
```

#### Optional - News System (11 categories)
```bash
NEWS_CYBERSECURITY_CHANNEL_ID=...
NEWS_TECH_CHANNEL_ID=...
NEWS_GAMING_CHANNEL_ID=...
NEWS_APPLE_GOOGLE_CHANNEL_ID=...
NEWS_CVE_CHANNEL_ID=...
NEWS_KEV_CHANNEL_ID=...
NEWS_US_LEGISLATION_CHANNEL_ID=...
NEWS_EU_LEGISLATION_CHANNEL_ID=...
NEWS_UK_LEGISLATION_CHANNEL_ID=...
NEWS_GENERAL_NEWS_CHANNEL_ID=...
NEWS_VENDOR_ALERTS_CHANNEL_ID=...
```

Community features (welcome greeter, newcomer helper, skid detector, profile
screen, role picker, moderation) are switched on per feature; `.env.example`
carries every variable with a comment, and the feature guides above explain
the ones that matter.

See [Channel Configuration Reference](reference/CHANNEL_CONFIGURATION.md) for complete details.

---

## 🆘 Getting Help

### In Discord
```
!help          # Interactive categorized help
/help          # Slash command version
!help [command] # Help for specific command
```

### Documentation Issues
- **Found a broken link?** [Open an issue](https://github.com/ChiefGyk3D/penguin-overlord/issues)
- **Documentation unclear?** [Suggest improvements](https://github.com/ChiefGyk3D/penguin-overlord/issues/new)
- **Missing information?** [Request new docs](https://github.com/ChiefGyk3D/penguin-overlord/issues/new?labels=documentation)

### Support Channels
- **GitHub Issues**: Bug reports and feature requests
- **GitHub Discussions**: General questions and community help

---

## 🤝 Contributing

Want to improve the documentation?

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

See the [contributing section of the README](../README.md#-contributing) for more details.

---

## 📝 Documentation Standards

All documentation follows these standards:

### Structure
- Clear table of contents
- Numbered steps for procedures
- Code examples with syntax highlighting
- Screenshots for complex UI interactions

### Formatting
- Use `code blocks` for commands and code
- Use **bold** for important terms
- Use *italics* for emphasis
- Use > blockquotes for important notes

### Style Guide
- Write in second person ("you")
- Use active voice
- Keep paragraphs short (3-4 sentences)
- Include examples for complex concepts

---

## 📅 Last Updated

**September 2, 2026**

---

<div align="center">
  
  **🐧 Made with ❤️ for hackers, HAMs, and hobbyists**
  
  [GitHub](https://github.com/ChiefGyk3D/penguin-overlord) • [Issues](https://github.com/ChiefGyk3D/penguin-overlord/issues) • [Discussions](https://github.com/ChiefGyk3D/penguin-overlord/discussions)
  
</div>
