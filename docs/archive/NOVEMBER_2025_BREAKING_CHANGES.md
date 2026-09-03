# November 2025 Breaking Changes

> ARCHIVED: historical document. Commands, counts, and paths in here may no longer match the code; the current docs are indexed in [docs/README.md](../README.md).

**Date**: November 9, 2025  
**Severity**: Medium (requires manual re-enablement of auto-posting)

## Summary

Two major changes to improve consistency and prevent unexpected auto-posting:

1. **All auto-posting now defaults to DISABLED**
2. **Legacy SecurityNews system removed**

## Breaking Change 1: Auto-Posting Defaults to Disabled

### What Changed

Previously, XKCD and Comics auto-posting defaulted to **enabled**, meaning setting a channel ID in `.env` would immediately start auto-posting. This was inconsistent with the News System (which defaulted to disabled) and could cause surprise posts.

**Now all auto-posting features default to DISABLED across the board.**

### Impact

| Feature | Old Behavior | New Behavior |
|---------|--------------|--------------|
| XKCD | Set channel → auto-posts immediately | Set channel → must run `!xkcd_enable` |
| Comics | Set channel → auto-posts immediately | Set channel → must run `!comic_enable` |
| Solar | Set channel → must enable | ✅ No change (already disabled by default) |
| News (all) | Set channel → must enable | ✅ No change (already disabled by default) |

### Who Is Affected

**You ARE affected if:**
- You currently have `XKCD_POST_CHANNEL_ID` or `COMIC_POST_CHANNEL_ID` set in .env
- Your bot is currently auto-posting XKCD or comics
- You expect auto-posting to continue without intervention

**You are NOT affected if:**
- You use the News System only (already disabled by default)
- You configure channels via Discord commands after bot startup
- You're doing a fresh installation

### Migration Steps

If you currently have auto-posting enabled and want to keep it:

#### Option 1: Via Discord Commands (Recommended)

After deploying the update:

```
# XKCD
!xkcd_status
!xkcd_enable

# Comics
!comic_status
!comic_enable

# Solar (if applicable)
!solar_status
!solar_enable

# News System (if applicable)
/news status
/news enable cybersecurity
/news enable tech
# ... etc for each category
```

#### Option 2: Manual State File Edit (Advanced)

If the bot is stopped, you can manually edit state files:

```bash
cd /home/chiefgyk3d/src/penguin-overlord/penguin-overlord/data

# XKCD
nano xkcd_state.json
# Change "enabled": false to "enabled": true

# Comics
nano comic_state.json
# Change "enabled": false to "enabled": true

# Solar
nano solar_state.json
# Change "enabled": false to "enabled": true
```

### Code Changes

**File**: `penguin-overlord/cogs/xkcd_poster.py`
```python
# Line 53, 55 changed from:
self.state = {'last_posted': 0, 'channel_id': None, 'enabled': True}

# To:
self.state = {'last_posted': 0, 'channel_id': None, 'enabled': False}
```

**File**: `penguin-overlord/cogs/comics.py`
```python
# Line 65, 67 changed from:
self.state = {'last_posted': None, 'channel_id': None, 'enabled': True, 'source': 'random'}

# To:
self.state = {'last_posted': None, 'channel_id': None, 'enabled': False, 'source': 'random'}
```

### Rollback (If Needed)

If you need to temporarily revert to the old behavior:

```bash
cd /home/chiefgyk3d/src/penguin-overlord
git diff penguin-overlord/cogs/xkcd_poster.py
git diff penguin-overlord/cogs/comics.py

# To revert:
git checkout HEAD~1 -- penguin-overlord/cogs/xkcd_poster.py
git checkout HEAD~1 -- penguin-overlord/cogs/comics.py
```

## Breaking Change 2: Legacy SecurityNews Removed

### What Changed

The old `securitynews.py` cog (25 mixed-quality sources) has been **removed** and replaced by the modern `cybersecurity_news.py` (18 curated sources) which is part of the News System.

### Impact

| Component | Status |
|-----------|--------|
| `securitynews.py` cog | ❌ Removed (renamed to `.deprecated`) |
| `!secnews_*` commands | ❌ No longer available |
| `SECNEWS_POST_CHANNEL_ID` env var | ❌ No longer used |
| `data/securitynews_state.json` | ❌ Ignored (can be deleted) |
| `cybersecurity_news.py` cog | ✅ Modern replacement |
| `/news` commands | ✅ Use instead |
| `NEWS_CYBERSECURITY_CHANNEL_ID` | ✅ Use instead |

### Who Is Affected

**You ARE affected if:**
- You have `SECNEWS_POST_CHANNEL_ID` in your .env
- You use `!secnews_*` commands
- You rely on the old security news feeds

**You are NOT affected if:**
- You already use the News System (`NEWS_CYBERSECURITY_CHANNEL_ID`)
- You're doing a fresh installation
- You don't use security news features

### Migration Steps

#### Step 1: Switch to News System

**Old Configuration:**
```bash
# .env
SECNEWS_POST_CHANNEL_ID=123456789012345678

# Discord
!secnews_set_channel #security
!secnews_enable
!secnews_status
```

**New Configuration:**
```bash
# .env
NEWS_CYBERSECURITY_CHANNEL_ID=123456789012345678

# Discord
/news set_channel cybersecurity #security
/news enable cybersecurity
/news status
```

#### Step 2: Test New System

```
# Check sources
/news list_sources cybersecurity

# Toggle individual sources if needed
/news toggle_source cybersecurity krebs

# Fetch news manually to test
/news fetch cybersecurity
```

#### Step 3: Cleanup (Optional)

```bash
cd /home/chiefgyk3d/src/penguin-overlord

# Remove env var from .env (if present)
nano .env
# Delete line: SECNEWS_POST_CHANNEL_ID=...

# Remove old state file
rm penguin-overlord/data/securitynews_state.json

# Optionally remove deprecated cog entirely
rm penguin-overlord/cogs/securitynews.py.deprecated
```

### Advantages of New System

The new cybersecurity news category provides:

✅ **Better sources**: 18 curated high-quality feeds vs 25 mixed quality  
✅ **Per-source control**: Enable/disable individual sources  
✅ **Unified interface**: Same commands as all other news categories  
✅ **Better performance**: ETag caching, concurrent fetching, optimized intervals  
✅ **Date filtering**: Prevents spam from historical items  
✅ **Consistent behavior**: Same disabled-by-default policy  

### Sources Comparison

**Old SecurityNews** (25 sources, removed):
- Mixed quality, some duplicates
- No per-source control
- Separate management interface

**New Cybersecurity News** (18 sources, current):
1. 404 Media
2. Ars Technica Security
3. Bleeping Computer
4. CyberScoop
5. Dark Reading
6. Graham Cluley
7. Infosecurity Magazine
8. Kaspersky Securelist
9. Krebs on Security
10. Malwarebytes Labs
11. Naked Security (Sophos)
12. SANS Internet Storm Center
13. Schneier on Security
14. Security Affairs
15. SecurityWeek
16. Talos Intelligence
17. The Hacker News
18. The Security Ledger
19. Threatpost
20. Troy Hunt (Have I Been Pwned)

### Rollback (If Needed)

If you absolutely need the old system temporarily:

```bash
cd /home/chiefgyk3d/src/penguin-overlord/penguin-overlord/cogs
mv securitynews.py.deprecated securitynews.py

# Restart bot
sudo systemctl restart penguin-overlord
```

**⚠️ Warning**: The old system will be completely removed in a future release. Migrate to the News System as soon as possible.

## Configuration File Changes

### .env.example

**Removed**:
```bash
# 🔐 Legacy Security News (Being replaced by News System)
SECNEWS_POST_CHANNEL_ID=
```

**Updated**:
```bash
# 🎨 Comics & Fun
# NOTE: Auto-posting is DISABLED by default. Run !xkcd_enable after setting channel.
XKCD_POST_CHANNEL_ID=

# NOTE: Auto-posting is DISABLED by default. Run !comic_enable after setting channel.
COMIC_POST_CHANNEL_ID=

# 📻 HAM Radio
# NOTE: Auto-posting is DISABLED by default. Run !solar_enable after setting channel.
SOLAR_POST_CHANNEL_ID=

# 📰 News & Legislation Tracking System
# NOTE: Auto-posting is DISABLED by default for all categories.
#       Run /news enable <category> after setting channels.
NEWS_CYBERSECURITY_CHANNEL_ID=
NEWS_TECH_CHANNEL_ID=
NEWS_GAMING_CHANNEL_ID=
NEWS_APPLE_GOOGLE_CHANNEL_ID=
NEWS_CVE_CHANNEL_ID=
NEWS_US_LEGISLATION_CHANNEL_ID=
NEWS_EU_LEGISLATION_CHANNEL_ID=
NEWS_GENERAL_NEWS_CHANNEL_ID=
```

## Testing Checklist

After deployment, verify:

- [ ] Bot starts without errors
- [ ] No `securitynews` cog loaded (check logs)
- [ ] `cybersecurity_news` cog loads successfully
- [ ] XKCD: `!xkcd_status` shows `enabled: False`
- [ ] Comics: `!comic_status` shows `enabled: False`
- [ ] Solar: `!solar_status` shows `enabled: False`
- [ ] News: `/news status` shows all categories disabled
- [ ] Enable commands work: `!xkcd_enable`, `!comic_enable`, `/news enable <category>`
- [ ] Auto-posting works after enabling
- [ ] No unexpected posts to channels

## Timeline

- **November 9, 2025**: Changes implemented
- **November 10-16, 2025**: Grace period - old state files still work
- **November 17, 2025**: Old state files can be cleaned up
- **December 2025**: `securitynews.py.deprecated` will be deleted

## Support

If you encounter issues:

1. Check logs: `journalctl -u penguin-overlord -f`
2. Verify state files: `ls -la penguin-overlord/data/*.json`
3. Check channel permissions in Discord
4. Review this migration guide
5. Open an issue on GitHub with logs

## Related Documentation

- `docs/CHANNEL_CONFIGURATION_REFERENCE.md` - Complete channel configuration guide
- `docs/HOUSEKEEPING_NOVEMBER_2025.md` - Other November improvements
- `.env.example` - Configuration template
- `docs/RSS_FEEDS_AND_API_KEYS.md` - Feed information

---

**Questions?** Check the help system: `!help` or `/help`
