# RSS Feeds and API Keys Guide

## TL;DR: No API Keys Required

Every feed Penguin Overlord fetches is public. RSS and Atom for most
categories, keyless JSON for NVD, the CISA KEV catalog and the Zscaler
status pages. Configure channel IDs and you are done.

Counts here were measured from the cogs' `*_SOURCES` dicts on 2026-09-02.
The live list is `/news list_sources <category>`; the full guide is
[NEWS_SYSTEM.md](../features/NEWS_SYSTEM.md).

---

## RSS vs API Access

### Feeds (What We Use)
- Public and free, no registration
- No rate limits for reasonable use
- Simple XML or JSON
- Limited to recent items, no historical search

### Authenticated APIs (What We Don't Use)
- Registration and API keys
- Rate limited (often 1,000 requests/day)
- Full data access and historical search, which the bot does not need

---

## Feed Inventory by Category

| Category | Sources | Notes |
|---|---:|---|
| Cybersecurity | 115 | media, vendor research blogs, CERTs |
| Vendor alerts | 34 | status pages and advisories; 5 Zscaler feeds are JSON, most others Atom |
| Apple/Google | 25 | |
| Tech | 17 | includes BBC Technology and BBC Science |
| General news | 12 | see below |
| Gaming | 10 | |
| CVE | 6 | NVD is a keyless JSON API; the rest are RSS/Atom |
| US legislation | 4 | see below |
| EU legislation | 3 | see below |
| KEV | 2 | CISA KEV JSON, Exploit Database RSS |
| UK legislation | 1 | see below |
| **Total** | **229** | 11 categories |

### US Legislation (4 sources, government only)

| Key | Source | Host | Notes |
|---|---|---|---|
| `presented_to_president` | Bills Presented to President | congress.gov | Low volume |
| `house_floor` | House Floor Today | congress.gov | Active during session |
| `senate_floor` | Senate Floor Today | congress.gov | Active during session |
| `govinfo_bills` | GovInfo Bills | govinfo.gov | High volume (100+ items) |

### General News (12 sources)

News outlets live here, not under US legislation.

| Key | Source | Host |
|---|---|---|
| `npr_news` | NPR News | npr.org |
| `pbs_economy` | PBS NewsHour, Economy | pbs.org |
| `financial_times` | Financial Times | ft.com |
| `pew_research` | Pew Research Center | pewresearch.org |
| `nyt_homepage` | New York Times, Homepage | nytimes.com |
| `foreign_affairs` | Foreign Affairs | foreignaffairs.com |
| `politico` | Politico | politico.com |
| `bbc_news` | BBC News, Top Stories | feeds.bbci.co.uk |
| `bbc_world` | BBC News, World | feeds.bbci.co.uk |
| `bbc_uk` | BBC News, UK | feeds.bbci.co.uk |
| `bbc_politics` | BBC News, Politics | feeds.bbci.co.uk |
| `bbc_health` | BBC News, Health | feeds.bbci.co.uk |

The five BBC feeds syndicate the same stories; cross-feed dedupe
(`utils/news_dedupe.py`) posts each once.

### EU Legislation (3 sources)

| Key | Source |
|---|---|
| `eurlex_parliament_council` | EUR-Lex, Parliament and Council legislation |
| `eurlex_proposals` | EUR-Lex, Commission proposals |
| `eurlex_official_journal` | EUR-Lex, Official Journal (binding acts) |

### UK Legislation (1 source)

| Key | Source |
|---|---|
| `all_bills` | UK Parliament, all bills (bills.parliament.uk) |

### Previously removed feeds

Congress.gov "most recent bills" (404), C-SPAN Executive (410) and AP
Politics (404) were dropped in November 2025. Later removals are recorded in
the git history of each cog; the 2026-08-31 audit retired or replaced 26
dead feeds (PR #134).

---

## Checking Feed Health

No document can promise that every feed returns 200 today. Two tools
measure it.

### `scripts/feed_audit.py` (use this one)

Harvests every URL from the cogs' source dicts, fetches each with the bot's
real User-Agent, follows redirects, and classifies the result as `OK`,
`EMPTY`, `REDIRECTED`, `HTML`, `PARSE` or `FAIL`. Exit code is the count of
`HTML + PARSE + FAIL`, so cron or CI can alert on it.

```bash
python3 scripts/feed_audit.py                 # everything
python3 scripts/feed_audit.py --cog tech_news
python3 scripts/feed_audit.py --failures-only
```

### `scripts/feed-check/`

A collection of one-off checker scripts kept from past feed additions
(`test_vendor_feeds.py`, `test_cert_feeds.py`, `test_comprehensive_feeds.py`,
`test_all_rss_parsers.py`, and so on). Most carry their own hard-coded feed
list and hit the network with `aiohttp`; they are triage tools, not unit
tests, and their lists drift from the cogs. Its `README.md` still refers to
the scripts by their old `tests/` path. Reach for `feed_audit.py` first and
these only when you want the historical list a script was written against.

### Logs

```bash
journalctl -u penguin-news-cybersecurity -n 100
journalctl -u penguin-news-us_legislation -f | grep -E "ERROR|WARNING"
systemctl status 'penguin-news-*'
```

Look for `Posted: <title>` (success), `HTTP 404` (feed gone),
`Request timeout` (slow feed), `No items found` (empty; normal during a
recess).

---

## Error Handling

Every news cog and the timer runner wrap each fetch:

```python
if response.status != 200:
    logger.warning(f"{source['name']}: HTTP {response.status}")
    return None

timeout = aiohttp.ClientTimeout(total=10, connect=5)

try:
    async with self.session.get(source['url']) as response:
        ...
except asyncio.TimeoutError:
    logger.warning(f"{source['name']}: Request timeout")
    return None
except Exception as e:
    logger.error(f"{source['name']}: Error: {e}")
    return None
```

An HTTP error, timeout, parse error or network error logs and skips that
source; the rest of the run continues, and the next scheduled run retries.

---

## GovInfo Special Case

**URL:** `https://www.govinfo.gov/rss/bills.xml`

The RSS feed is public and needs no key; GovInfo's separate API at
`api.govinfo.gov` does, and the bot does not use it. Volume is high (100+
items per fetch). The 7-day date filter in the legislation cogs keeps the
backlog out, but it can still post several items an hour. Silence it with:

```
/news toggle_source us_legislation govinfo_bills
```

---

## Testing a Feed Yourself

```bash
# HTTP status
curl -s -o /dev/null -w "%{http_code}\n" --max-time 5 https://www.govinfo.gov/rss/bills.xml

# Inspect content and count items
curl -s https://feeds.npr.org/1001/rss.xml | head -50
curl -s https://www.govinfo.gov/rss/bills.xml | grep -c "<item>"
```

`200` is working, `404` is gone, `301/302` is a redirect (followed
automatically, but update the URL in the cog when `feed_audit.py` reports
`REDIRECTED`).

---

## Configuration with Environment Variables

```bash
NEWS_CYBERSECURITY_CHANNEL_ID=123456789012345678
NEWS_VENDOR_ALERTS_CHANNEL_ID=
NEWS_APPLE_GOOGLE_CHANNEL_ID=
NEWS_TECH_CHANNEL_ID=
NEWS_GENERAL_NEWS_CHANNEL_ID=
NEWS_GAMING_CHANNEL_ID=
NEWS_CVE_CHANNEL_ID=
NEWS_US_LEGISLATION_CHANNEL_ID=
NEWS_EU_LEGISLATION_CHANNEL_ID=
NEWS_KEV_CHANNEL_ID=
NEWS_UK_LEGISLATION_CHANNEL_ID=
```

Or in Doppler: `doppler secrets set NEWS_US_LEGISLATION_CHANNEL_ID="..."`.
Or in Discord: `/news set_channel us_legislation #us-legislation` then
`/news enable us_legislation`. See
[CHANNEL_CONFIGURATION.md](CHANNEL_CONFIGURATION.md).

---

## Adding New Feeds

### Requirements

1. RSS, Atom or a JSON shape the category's parser already understands.
2. Publicly accessible: no auth, HTTP 200, no paywall on the feed itself.
3. Reasonable volume, ideally under 50 items a day; high-volume feeds need
   the date filter.

### Steps

1. Add an entry to the category's source dict (for example
   `LEGISLATION_SOURCES` in `cogs/us_legislation.py`):

   ```python
   'new_source': {
       'name': 'New Source Name',
       'url': 'https://example.com/feed.xml',
       'emoji': '📰'
   }
   ```

2. If the category's manual-fetch command uses a `Literal[...]` for its
   `source` argument (the legislation cogs and `general_news` do), add the
   key there too, or the slash command will not offer it.
3. `python3 scripts/feed_audit.py --cog <cog_name>` and confirm `OK`.
4. Test in Discord, for example `/uslegislation new_source`.

### Checklist

- [ ] `feed_audit.py` reports `OK` (not `REDIRECTED`, `HTML` or `EMPTY`)
- [ ] Items have title, link and a publication date
- [ ] Feed updates regularly
- [ ] No authentication required
- [ ] Volume under 100 items a day

---

## Troubleshooting

**"No items found" but the feed exists.** The feed is empty (common in a
congressional recess), every item is older than 7 days, or everything was
already posted. Normal; wait.

**HTTP 404.** URL changed or the feed was discontinued. Run
`feed_audit.py`, then replace or remove the source.

**Request timeout.** Slow server or network. Retries on the next run.

**Old content posted.** The feed's dates are wrong or unparseable; check the
cog's `_is_recent()`.

---

## Summary

- API keys, accounts, subscriptions: none needed.
- What you do need: Discord channel IDs (via `.env` or `/news`) and a
  network connection.
- 229 feeds across 11 categories as of 2026-09-02; verify with
  `scripts/feed_audit.py`, not with this page.
