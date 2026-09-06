# Quick Reference: New Help System

## Using the New Help Command

### Basic Usage

```
!help               Show interactive help menu with dropdown
!help xkcd          Show help for specific command
/help               Also works as slash command
!help_old           Legacy paginated help (fallback)
```

## Category Structure

```
🐧 Penguin Overlord Help Menu
┌─────────────────────────────────────┐
│ 📚 Choose a category to explore... │
├─────────────────────────────────────┤
│ 🐧 Overview                         │
│ 🎨 Comics & Fun                     │
│ 📰 News & CVE                       │
│ 📻 HAM Radio                        │
│ ✈️ Aviation                         │
│ 🔍 SIGINT                           │
│ 📅 Con Recon                        │
│ 🛠️ Utilities                        │
│ ⚙️ Admin                            │
└─────────────────────────────────────┘
        [🗑️ Delete]
```

## What's in Each Category?

### 🐧 Overview
- Quick introduction
- Feature highlights
- Getting started guide
- Navigation tips

### 🎨 Comics & Fun
- **XKCD:** Latest, random, search comics
- **Tech Comics:** XKCD, Joy of Tech, TurnOff.us
- **Tech Quotes:** 610+ quotes from 70+ legends
- **Auto-posting:** XKCD & daily comics setup

### 📰 News & CVE (220+ sources, 11 categories)
- **Configuration:** Set channels, enable/disable
- **Categories:** Cybersecurity, tech, gaming, Apple/Google, CVE, legislation, general news
- **Manual Fetch:** Get news on demand
- **Environment Vars:** .env/Doppler setup

### 📻 HAM Radio (18 commands)
- **Solar Data:** Real-time solar weather from NOAA
- **Propagation:** Band conditions and forecasts
- **Auto-posting:** Solar reports (every 12 hours in-bot, every 30 minutes from the systemd timer)
- **Radio Info:** Frequency bands, trivia

### ✈️ Aviation (4 commands)
- **Squawk Codes:** Transponder lookup
- **Aircraft:** Random aircraft info
- **Frequencies:** Aviation radio frequencies
- **Trivia:** Aviation facts

### 🔍 SIGINT (3 commands)
- **Frequency Log:** Interesting frequencies to monitor
- **SDR Tools:** Software-defined radio decoders
- **Facts:** Signal intelligence tips

### 📅 Con Recon (5 commands)
- **Conferences:** DEF CON, BSides, HAM events
- **Search:** Find events by name/location
- **Countdown:** Next upcoming event
- **Filter:** By type (cybersecurity/ham)

### 🛠️ Utilities (3 commands)
- **Fortune:** Cyber fortune cookies
- **Manpages:** Random Linux commands
- **Patch Gremlin:** Update reminders

### ⚙️ Admin (Configuration)
- **Bot Management:** Sync, list cogs
- **Channel Setup:** All auto-posting channels
- **Config Methods:** Discord, .env, Doppler
- **News Management:** Full news system config

## Key Features

✅ **One-Click Navigation** - Jump directly to any category
✅ **Clean Organization** - Emoji-coded categories
✅ **Compact Display** - No pagination needed
✅ **Quick Delete** - Remove help with one click
✅ **Auto-Timeout** - Cleans up after 5 minutes

## Comparison: Old vs New

### Old Help (`!help`)
```
Page 1/6 ──▶ Page 2/6 ──▶ Page 3/6 ──▶ ... ──▶ Page 6/6
    ◀️         ◀️▶️         ◀️▶️                ◀️
```
**Linear navigation, must page through all content**

### New Help (`!help`)
```
        [Dropdown Menu]
             ▼
    ┌────────┬────────┐
    │ Comics │  News  │  HAM  │  Aviation  │  ...
    └────────┴────────┘
```
**Direct access to any category instantly**

## Configuration Examples

### Comics Auto-Posting
```bash
# Via Discord
!xkcd_set_channel #comics
!xkcd_enable

# Via .env
XKCD_POST_CHANNEL_ID=123456789012345678
```

### News Tracking
```bash
# Via Discord
/news set_channel cybersecurity #security-news
/news enable cybersecurity

# Via .env
NEWS_CYBERSECURITY_CHANNEL_ID=123456789012345678
```

### HAM Radio Solar Reports
```bash
# Via Discord
!solar_set_channel #ham-radio
!solar_enable

# Via .env
SOLAR_POST_CHANNEL_ID=123456789012345678
```

## Tips & Tricks

💡 **Start with Overview** - Select 🐧 Overview first for introduction
💡 **Explore Categories** - Use dropdown to browse different features
💡 **Specific Help** - Use `!help [command]` for detailed command info
💡 **Delete When Done** - Click 🗑️ to remove help message
💡 **Works Both Ways** - `!help` and `/help` both work

## Getting Started

1. **Try it:** Type `!help` in any channel
2. **Select category:** Choose from dropdown menu
3. **Read commands:** See all commands in that category
4. **Try commands:** Start using your favorite features!
5. **Configure:** Set up auto-posting if desired

## Need More Help?

- **Specific command:** `!help [command]`
- **Source code:** `!source_code`
- **Issues:** [GitHub Issues](https://github.com/ChiefGyk3D/penguin-overlord/issues)
- **Docs:** Check `/docs` folder in repository

---

**Made with 🐧 and ❤️**

## What the pages do not cover

The nine pages cover the member-facing commands. The `/mod`, `/profile`, `/roles` groups and the listener-only cogs (welcome greeter, newcomer helper, skid detector, rules sync, vendor alerts, metrics) are documented in [COMMANDS.md](COMMANDS.md) and the feature guides instead; Discord already hides the admin groups from members who lack the permission.
