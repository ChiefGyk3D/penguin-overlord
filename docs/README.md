# 🐧 Penguin Overlord Documentation

<div align="center">
  <img src="../media/banner_wide.png" alt="Penguin Overlord Banner" width="800"/>
  
  **Complete documentation for the Penguin Overlord Discord Bot**
  
  *For hackers, HAMs, and hobbyists*
</div>

---

## 📚 Quick Navigation

### 🚀 Getting Started
- **[Discord Setup](setup/DISCORD_SETUP.md)** - Create your bot and get tokens
- **[Permissions Guide](setup/PERMISSIONS.md)** - Required Discord permissions
- **[Secrets Management](secrets/README.md)** - Configure credentials securely

### ✨ Features
- **[News System](features/NEWS_SYSTEM.md)** - 92 sources across 8 categories
- **[News Categories](features/NEWS_CATEGORIES_OVERVIEW.md)** - Detailed category breakdown

### 🚢 Deployment
- **[Production Deployment](deployment/PRODUCTION.md)** - Deploy to production
- **[Systemd Setup](deployment/SYSTEMD.md)** - Run as a Linux service

### 📖 Reference
- **[Channel Configuration](reference/CHANNEL_CONFIGURATION.md)** - All 11 channel environment variables
- **[RSS Feeds](reference/RSS_FEEDS.md)** - Complete feed list and API information
- **[News Optimization](reference/NEWS_OPTIMIZATION.md)** - Performance tuning guide
- **[Help System](reference/HELP_SYSTEM.md)** - Using the categorized help system

### 🔄 Migration & Updates
- **[November 2025 Breaking Changes](migration/NOVEMBER_2025_BREAKING_CHANGES.md)** - Important updates

### 📦 Archive
Historical documentation preserved for reference:
- [Doppler Integration History](archive/DOPPLER_INTEGRATION.md)
- [Legislation Feed Updates](archive/LEGISLATION_FEED_UPDATES.md)
- [Housekeeping November 2025](archive/HOUSEKEEPING_NOVEMBER_2025.md)
- [More archived docs...](archive/)

---

## 🎯 Common Tasks

### Setting Up Your Bot
1. [Get Discord Bot Token](setup/DISCORD_SETUP.md#getting-your-token)
2. [Configure Secrets](secrets/README.md#quick-start)
3. [Set Channel IDs](reference/CHANNEL_CONFIGURATION.md#configuration-examples)
4. [Enable Auto-Posting](migration/NOVEMBER_2025_BREAKING_CHANGES.md#migration-steps)

### Configuring News
1. [Choose News Categories](features/NEWS_CATEGORIES_OVERVIEW.md)
2. [Set Channel Environment Variables](reference/CHANNEL_CONFIGURATION.md#news-system-8-channels-90-sources)
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
- **Daily Tech Comics** - Rotation of 5 tech comic sources
- **Tech Quotes** - 610+ quotes from 70+ tech legends

### 📰 News Aggregation (92 sources)
- **Cybersecurity** (18 sources) - Krebs, Dark Reading, Schneier, etc.
- **Technology** (15 sources) - Ars Technica, The Verge, TechCrunch, etc.
- **Gaming** (10 sources) - IGN, Kotaku, PC Gamer, etc.
- **Apple & Google** (27 sources) - 9to5Mac, Android Police, etc.
- **CVE Tracking** (3 sources) - CISA KEV, NVD, CERT-EU
- **US Legislation** (5 sources) - GovInfo, Congressional Record, etc.
- **EU Legislation** (3 sources) - EUR-Lex, EU Publications, etc.
- **General News** (7 sources) - NPR, PBS, Financial Times, etc.

### 📻 HAM Radio
- **Solar Weather** - Live data from NOAA SWPC
- **Propagation Reports** - Band-by-band predictions
- **Auto-Posting** - Solar reports every 12 hours

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

#### Optional - News System (9 categories)
```bash
NEWS_CYBERSECURITY_CHANNEL_ID=...
NEWS_TECH_CHANNEL_ID=...
NEWS_GAMING_CHANNEL_ID=...
NEWS_APPLE_GOOGLE_CHANNEL_ID=...
NEWS_CVE_CHANNEL_ID=...
NEWS_US_LEGISLATION_CHANNEL_ID=...
NEWS_EU_LEGISLATION_CHANNEL_ID=...
NEWS_UK_LEGISLATION_CHANNEL_ID=...
NEWS_GENERAL_NEWS_CHANNEL_ID=...
```

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

See our [contributing guidelines](../CONTRIBUTING.md) for more details.

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

**November 9, 2025**

---

<div align="center">
  
  **🐧 Made with ❤️ for hackers, HAMs, and hobbyists**
  
  [GitHub](https://github.com/ChiefGyk3D/penguin-overlord) • [Issues](https://github.com/ChiefGyk3D/penguin-overlord/issues) • [Discussions](https://github.com/ChiefGyk3D/penguin-overlord/discussions)
  
</div>
