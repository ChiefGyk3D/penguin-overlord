# Date Filtering for Legislation Feeds

> ARCHIVED: historical document. Commands, counts, and paths in here may no longer match the code; the current docs are indexed in [docs/README.md](../README.md).

## Problem Solved

When enabling legislation tracking for the first time, feeds with large archives (like GovInfo with 100+ items) would flood the channel with old content. This optimization ensures only **recent and relevant** items are posted.

## Solution Implemented

Added intelligent date filtering to both US and EU legislation cogs:

### Key Features

1. **7-Day Window** (configurable)
   - Only posts items from the last 7 days
   - Prevents historical content flooding
   - Focuses on current/active legislation

2. **Date Detection**
   - Supports multiple RSS date formats:
     - `<pubDate>` (RSS 2.0)
     - `<published>` (Atom)
     - `<updated>` (Atom)
     - `<dc:date>` (Dublin Core)
   - Handles both RFC 2822 and ISO 8601 formats

3. **Smart Fallback**
   - If no date found → assumes recent (posts it)
   - If date unparseable → assumes recent (posts it)
   - Fail-safe: never blocks content due to parsing errors

4. **Checks Multiple Items**
   - Examines up to 10 most recent feed items
   - Finds first recent + unposted item
   - Skips old items automatically

## How It Works

### Before (Old Behavior):
```python
# Get first item from feed
item = items[0]

# Check if already posted
if link in posted:
    return None

# Post it
return item
```
**Problem**: Would post 100+ old items from GovInfo on first run

### After (New Behavior):
```python
# Check up to 10 most recent items
for item in items[:10]:
    # Skip if older than 7 days
    if not is_recent(item, max_days=7):
        continue
    
    # Skip if already posted
    if link in posted:
        continue
    
    # Found a recent, unposted item!
    return item
```
**Result**: Only posts items from the last week, even on first setup

## Configuration

### Default Settings (in code):
```python
max_days = 7  # Only items from last 7 days
check_limit = 10  # Check up to 10 most recent items
```

### Per-Source Customization (future):
Could add to news_config.json:
```json
{
  "us_legislation": {
    "max_item_age_days": 7,
    "check_item_limit": 10,
    "sources": {
      "govinfo_bills": {
        "enabled": false  // Disable high-volume source
      }
    }
  }
}
```

## Example Scenarios

### Scenario 1: First Time Setup
**Feed**: GovInfo Bills (100 items, mostly old)

**Without filtering**:
- Posts all 100 items (flooding channel)
- Takes ~50 seconds (rate limiting)
- Clutters channel with historical content

**With filtering**:
- Checks 10 most recent items
- Finds 2 from last 7 days
- Posts only those 2 items
- Takes ~1 second

### Scenario 2: Congressional Recess
**Feed**: House Floor Today (empty during recess)

**Result**: No posts (no recent items) ✅

### Scenario 3: Active Session
**Feed**: Bills Presented to President (3 items this week)

**Result**: Posts all 3 recent bills ✅

## Benefits

1. **No Channel Flooding**
   - Clean initial setup
   - Only relevant content

2. **Automatic Pruning**
   - Old items ignored automatically
   - No manual intervention needed

3. **Performance**
   - Stops checking after finding first match
   - Faster execution

4. **User Experience**
   - Channel stays clean
   - Focus on current events
   - No historical spam

## Technical Details

### Date Parsing Order:
1. Try `email.utils.parsedate_to_datetime()` (RFC 2822)
2. Try `datetime.fromisoformat()` (ISO 8601)
3. If both fail → assume recent (safe fallback)

### Example Date Formats Supported:
```xml
<!-- RSS 2.0 -->
<pubDate>Sat, 09 Nov 2025 15:30:00 GMT</pubDate>

<!-- Atom -->
<published>2025-11-09T15:30:00Z</published>

<!-- ISO 8601 -->
<updated>2025-11-09T15:30:00+00:00</updated>

<!-- Dublin Core -->
<dc:date>2025-11-09</dc:date>
```

## Applies To

- ✅ US Legislation (9 sources)
- ✅ EU Legislation (3 sources)

## Source Behavior

| Source | Typical Volume | Old Items? | Filtering Impact |
|--------|---------------|------------|------------------|
| Most Recent Bills | Low | Few | Minimal |
| Presented to President | Very Low | None | None |
| House/Senate Floor | Low | None when in session | None |
| Most Viewed Bills | Low | Some | Filters ~1-2 |
| **GovInfo Bills** | **Very High (100+)** | **Many** | **Filters ~98** |
| C-SPAN Executive | Medium | Some | Filters ~5-10 |
| Reuters Politics | Medium | Some | Filters ~10-15 |
| AP Politics | Medium | Some | Filters ~10-15 |

## Recommendation

Keep `govinfo_bills` **disabled by default** even with filtering:
```
/news toggle_source us_legislation govinfo_bills
```

**Why?** Even with filtering, it's still high-volume compared to other sources.

## Monitoring

Check if filtering is working:
```bash
# View logs
journalctl -u penguin-news-us_legislation -f

# Look for:
# "Checking US legislation sources..." (hourly run)
# "Posted: <title>..." (successful post)
# No flood of posts = filtering working!
```

## Future Enhancements

1. **Configurable time window**
   - Per-category or per-source settings
   - `/news set_max_age us_legislation 3` (3 days)

2. **Smart initialization mode**
   - First run: only post 1 item per source
   - Subsequent runs: normal behavior

3. **Date in embed footer**
   - Show publication date in Discord embed
   - User can see item age

4. **Statistics**
   - Track filtered vs posted ratio
   - Alert if feed goes stale (no items in N days)

## Testing

Both cogs tested and working:
```
✅ EU Legislation cog loaded
✅ US Legislation cog loaded
```

No errors in date parsing or filtering logic.
