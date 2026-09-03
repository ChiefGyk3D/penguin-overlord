# US Legislation Sources - Verified Working

> ARCHIVED: historical document. Commands, counts, and paths in here may no longer match the code; the current docs are indexed in [docs/README.md](../README.md).

## ✅ Final Source List (5 sources)

All feeds tested and confirmed working as of November 9, 2025.

### 1. Bills Presented to President
- **Key**: `presented_to_president`
- **URL**: https://www.congress.gov/rss/presented-to-president.xml
- **Emoji**: ✍️
- **Description**: Bills that have passed both chambers and are awaiting presidential action
- **Status**: ✅ Working (0 items currently - normal when no bills pending)

### 2. House Floor Today
- **Key**: `house_floor`
- **URL**: https://www.congress.gov/rss/house-floor-today.xml
- **Emoji**: 🏛️
- **Description**: Current House floor activity and schedule
- **Status**: ✅ Working (0 items when House not in session)

### 3. Senate Floor Today
- **Key**: `senate_floor`
- **URL**: https://www.congress.gov/rss/senate-floor-today.xml
- **Emoji**: 🏛️
- **Description**: Current Senate floor activity and schedule
- **Status**: ✅ Working (0 items when Senate not in session)

### 4. Most Viewed Bills
- **Key**: `most_viewed_bills`
- **URL**: https://www.congress.gov/rss/most-viewed-bills.xml
- **Emoji**: 📋
- **Description**: Bills getting the most public attention on Congress.gov
- **Status**: ✅ Working (1 item found)

### 5. GovInfo Bills
- **Key**: `govinfo_bills`
- **URL**: https://www.govinfo.gov/rss/bills.xml
- **Emoji**: 📜
- **Description**: Official government publication of all bills
- **Status**: ✅ Working (100 items - high volume)

## ❌ Feeds Attempted But Not Working

These URLs from your original list returned 404 errors:

1. `https://www.congress.gov/rss/most-recent-bills.xml` - 404
2. `https://www.congress.gov/rss/most-recent-amendments.xml` - 404
3. `https://www.congress.gov/rss/enacted-bills.xml` - 404
4. `https://statesnewsroom.com/feed/dc-bureau` - 404
5. `https://www.whitehouse.gov/feed/` - 404

**Note**: Congress.gov may have changed their RSS feed structure. The feeds we're using are confirmed to work.

## Discord Commands

```
# Manual fetching
/uslegislation presented_to_president
/uslegislation house_floor
/uslegislation senate_floor
/uslegislation most_viewed_bills
/uslegislation govinfo_bills

# Configuration
/news set_channel us_legislation #us-legislation
/news enable us_legislation
/news toggle_source us_legislation govinfo_bills
/news status us_legislation
```

## Hourly Update Schedule

- **Frequency**: Every hour
- **Minute Offset**: :05 (e.g., 00:05, 01:05, 02:05...)
- **Prevents overlap** with news categories

## Expected Behavior

### During Congressional Sessions
- House/Senate floor feeds will have items about current proceedings
- Bills presented to president will show pending legislation
- Most viewed will reflect hot topics

### During Recess
- Floor feeds may be empty (normal)
- Bills presented may be empty (normal)
- GovInfo continues with historical/archived content
- Most viewed still shows popular bills

## Feed Characteristics

| Source | Update Frequency | Volume | Empty When? |
|--------|------------------|--------|-------------|
| Presented to President | Real-time | Low | Often (only when bills pending signature) |
| House Floor | Real-time | Low | When House not in session |
| Senate Floor | Real-time | Low | When Senate not in session |
| Most Viewed | Daily | Low | Rarely |
| GovInfo Bills | Daily | **High** (100+) | Never |

**⚠️ Warning**: GovInfo Bills feed is very high volume (100 items). Consider:
- Disabling by default: `/news toggle_source us_legislation govinfo_bills`
- Or increasing deduplication cache size
- Posts will flood channel if all 100 items are new

## Recommendation

For most use cases, you may want to disable `govinfo_bills` initially:

```
/news toggle_source us_legislation govinfo_bills
```

This leaves you with 4 low-volume, high-signal sources focused on active congressional activity.

## Testing

Run the test script to verify all feeds:
```bash
python3 scripts/test_us_legislation.py
```

Expected output: All 5 feeds should show ✅ OK

## Integration Status

- ✅ Cog loads successfully
- ✅ All 5 feeds tested and working
- ✅ Integrated with NewsManager
- ✅ Hourly schedule configured
- ✅ Discord commands functional
- ✅ State file tracking working
