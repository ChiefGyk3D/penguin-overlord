# 🔐 Discord Bot Permissions Guide for Penguin Overlord

This guide explains what Discord permissions Penguin Overlord needs and why.

## Permission Overview

Penguin Overlord is designed to be a fun, interactive bot for posting content like XKCD comics, either on command, via slash commands, or on a schedule.

## Required Permissions

These permissions are **essential** for the bot to work:

### 1. View Channels (Read Messages/View Channels)
- **Why:** Bot needs to see channels to respond to commands
- **Permission Value:** `1024`
- **Without it:** Bot can't see any messages or channels

### 2. Send Messages
- **Why:** Post XKCD comics and command responses
- **Permission Value:** `2048`
- **Without it:** Bot can't respond to anything

### 3. Embed Links
- **Why:** Display rich XKCD comic embeds with images
- **Permission Value:** `4096`
- **Without it:** Comics will show as plain links instead of nice embeds

### 4. Use Slash Commands
- **Why:** Enable `/xkcd` style commands
- **Scope:** Included in `applications.commands` OAuth2 scope
- **Without it:** Only `!` prefix commands work

## Recommended Permissions

These enhance functionality for scheduled posts and future features:

### 5. Attach Files
- **Why:** Upload images or files for future features
- **Permission Value:** `32768`
- **Future use:** Direct image uploads, memes, etc.

### 6. Read Message History
- **Why:** Provide context for commands, avoid duplicate posts
- **Permission Value:** `65536`
- **Use case:** Check if comic was already posted today

### 7. Add Reactions
- **Why:** Interactive features (voting, acknowledgment)
- **Permission Value:** `64`
- **Future use:** Poll reactions, emoji interactions

### 8. Send Messages in Threads
- **Why:** Participate in thread discussions
- **Permission Value:** `274877906944`
- **Use case:** Continue conversations in threads

## Per-feature permissions (only when you switch the feature on)

The community features are all off by default. Each one needs a specific
permission, and the bot says so in its reply when it is missing.

| Feature | Permission | Why |
|---|---|---|
| Role picker (`ROLE_PICKER_ENABLED`) | **Manage Roles**, with the bot's role dragged above the picker roles | `/roles post` creates the roles and the dropdowns assign them. See [ROLE_PICKER.md](../features/ROLE_PICKER.md). |
| Profile screen (`PROFILE_SCREEN_ENABLED`) | **Kick Members**, **Ban Members** for the mod card buttons; **Manage Server** for `/profile sync-automod` | Moderators press Ban/Kick on the card; the bot carries it out. The AutoMod sync creates a member-profile rule. |
| Moderation enforcement (`MOD_DRY_RUN=false`, Phase 3) | **Moderate Members** (timeouts), **Manage Messages** (deletes) | Not needed while moderation is alert-only, which is the default. |
| Welcome greeter | none beyond Send Messages and Embed Links in its channels | Greetings mention members, not roles or everyone. |

### Manage Messages
- **Why:** Clean up bot messages, delete flagged content once enforcement is on
- **Permission Value:** `8192`

### Mention Everyone
- **Why:** Announce important posts to @everyone
- **Permission Value:** `131072`
- **Use case:** Not used by any current feature; the role picker roles are created non-mentionable so only the bot can ping them, which does not need this permission

## Scheduled Posts Requirements

For scheduled posting (future feature), you'll need:

✅ **Send Messages** - Post on schedule
✅ **Embed Links** - Display comics
✅ **Read Message History** - Check if already posted
✅ **Send Messages in Threads** - Post in designated thread (optional)

**No additional permissions needed!** The bot can post on a schedule with the same permissions as command-based posting.

## Permission Calculation

### Recommended Permission Set

For a fully-featured bot with scheduled posting capability:

```
View Channels        =          1024
Send Messages        =          2048
Embed Links          =          4096
Add Reactions        =            64
Attach Files         =         32768
Read Message History =         65536
Send in Threads      = 274877906944
                      ───────────────
Total                = 414464724032
```

**Discord Permission Integer:** `414464724032`

### Minimal Permission Set

For basic functionality only:

```
View Channels   =   1024
Send Messages   =   2048
Embed Links     =   4096
                  ───────
Total           =   7168
```

**Discord Permission Integer:** `7168`

## How to Set Permissions

### Method 1: Using OAuth2 URL Generator (Recommended)

1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Select your application
3. Go to **OAuth2** → **URL Generator**
4. Select scopes:
   - ✅ `bot`
   - ✅ `applications.commands`
5. Select permissions (see lists above)
6. Copy the generated URL

### Method 2: Manual Permission URL

Create a URL like this:
```
https://discord.com/api/oauth2/authorize?client_id=YOUR_CLIENT_ID&permissions=414464724032&scope=bot%20applications.commands
```

Replace:
- `YOUR_CLIENT_ID` - Your bot's application ID (from General Information)
- `414464724032` - Permission integer (use recommended or minimal)

### Method 3: In-Server Permissions (After Bot is Added)

You can modify permissions after the bot is added:

1. Go to Server Settings → Roles
2. Find the bot's role
3. Edit permissions
4. OR go to specific channel → Permissions → Add bot role → Set permissions

## Permission Scenarios

### Scenario 1: Basic XKCD Bot (Commands Only)

**Permissions needed:**
- View Channels
- Send Messages
- Embed Links

**Use case:** Users run `!xkcd` and bot responds
**Permission integer:** `7168`

### Scenario 2: XKCD Bot with Slash Commands

**Permissions needed:**
- All from Scenario 1
- Applications.commands scope (OAuth2)

**Use case:** Users run `/xkcd` slash commands
**Permission integer:** `7168` + `applications.commands` scope

### Scenario 3: Full-Featured Bot with Scheduled Posts

**Permissions needed:**
- View Channels
- Send Messages
- Embed Links
- Attach Files
- Read Message History
- Add Reactions
- Send Messages in Threads

**Use case:** Bot posts XKCD on schedule, responds to commands, interactive features
**Permission integer:** `414464724032`

## Security Best Practices

### ✅ DO:

- **Grant minimum permissions** - Only give what's needed
- **Use role-based permissions** - Create a bot-specific role
- **Limit channel access** - Restrict to specific channels if needed
- **Review regularly** - Check what permissions bot actually uses

### ❌ DON'T:

- **Grant Administrator** - Never needed for Penguin Overlord
- **Grant Ban or Kick Members** - Unless the profile screen is on; its mod card is the only thing that uses them, and a human presses the button
- **Allow @everyone mentions** - Nothing uses it
- **Grant Manage Server** - Only `/profile sync-automod` needs it, and you can grant it for that one run and take it back

## Channel-Specific Permissions

You can restrict the bot to specific channels:

1. Go to Channel Settings → Permissions
2. Add the bot or bot role
3. Set channel-specific permissions:
   - ✅ View Channel
   - ✅ Send Messages
   - ✅ Embed Links
   - ❌ Deny all others

This way, bot only works in designated channels!

## Troubleshooting Permission Issues

### Bot doesn't respond to commands

**Check:**
- ✅ Bot has "View Channels" permission
- ✅ Bot has "Send Messages" permission
- ✅ MESSAGE CONTENT INTENT is enabled (Developer Portal)

### Embeds don't show up

**Check:**
- ✅ Bot has "Embed Links" permission
- ✅ Server settings allow embeds (Server Settings → Text & Images → "Show website preview info from links pasted into chat")

### Slash commands don't appear

**Check:**
- ✅ OAuth2 scope includes `applications.commands`
- ✅ Bot was invited with the correct scope
- ✅ May need to re-invite bot with updated scope

### Can't post in specific channel

**Check:**
- ✅ Bot has permission to view that channel
- ✅ Channel isn't age-restricted (if bot isn't verified)
- ✅ Channel-specific permission overrides aren't blocking the bot

## Permission Updates

If you need to add permissions later:

1. Go to OAuth2 URL Generator
2. Generate new URL with updated permissions
3. Open URL and re-authorize bot
4. Select "Update permissions" when prompted

No need to kick the bot and re-add it!

## Quick Reference

| Feature | Required Permissions | Permission Value |
|---------|---------------------|------------------|
| Basic commands | View Channels, Send Messages, Embed Links | 7168 |
| Slash commands | Above + applications.commands scope | 7168 + scope |
| Scheduled posts | Above + Read Message History | 74752 |
| Interactive features | Above + Add Reactions, Attach Files | 107584 |
| Full-featured | All recommended | 414464724032 |

## Implementation in Penguin Overlord

The bot is designed to work with **minimal permissions** by default. Advanced features gracefully degrade if permissions aren't available.

For example:
- If no "Add Reactions" → Skip reaction-based features
- If no "Read History" → Post without duplicate checking
- If no "Manage Messages" → Skip message cleanup

This makes Penguin Overlord safe and flexible! 🐧

---

**Recommended OAuth2 URL Template:**
```
https://discord.com/api/oauth2/authorize?client_id=YOUR_CLIENT_ID&permissions=414464724032&scope=bot%20applications.commands
```

Replace `YOUR_CLIENT_ID` with your application ID from the Developer Portal.

---

Made with 🐧 and ❤️
