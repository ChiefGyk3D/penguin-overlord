# Configuration loading

`penguin-overlord/utils/config.py` reads the whole environment once, at
startup, and turns it into a frozen `Config` object. Every entry point
(`bot.py` and the news, KEV, solar, xkcd and comics runners) calls
`load_config()` before it does anything else. If any variable is missing
or malformed the process logs one error listing all of them and exits 1.

Before this module each feature ran its own `os.getenv` calls. A typo in
one channel id showed up hours later as a silent no-post, and a missing
token gave a different error in each of the six entry points.

## What a failure looks like

```
❌ Refusing to start:
3 configuration problems:
  - DISCORD_BOT_TOKEN: required, not set
  - NEWS_TECH_CHANNEL_ID: expected a Discord id (17 to 20 digits), got 'general'
  - METRICS_PORT: expected an integer between 1 and 65535, got 'x'
```

Values are echoed only for non-secret variables, and truncated to 32
characters. Anything that reaches the secrets manager (`DISCORD_*`,
`GEMINI_*`, and so on) is reported by name alone.

## Checking without starting the bot

```
python scripts/check-config.py
docker compose run --rm penguin-overlord python scripts/check-config.py
```

Prints `OK:` followed by a counts-only summary (how many news channels
are set, which posters and AI features are on), or `FAIL:` with the same
list the bot would log. Exit code 0 or 1. It loads `.env` and the secrets
manager exactly the way `bot.py` does, so it validates what production
would actually run with.

## Sections

`Config` is a frozen dataclass of frozen dataclasses, grouped by concern:

| Section | Variables | Notes |
|---|---|---|
| `discord` | `DISCORD_BOT_TOKEN`, `DISCORD_OWNER_ID` | The token is the only required variable. `DISCORD_TOKEN` is accepted as an alias because the runners historically read it. |
| `logging` | `LOG_LEVEL`, `LOG_FILE`, `LOG_MAX_BYTES`, `LOG_BACKUPS` | See [Logging](LOGGING.md). |
| `paths` | `DATA_DIR`, `BOT_DATABASE_PATH`, `XKCD_STATE_PATH`, `COMIC_STATE_PATH` | Paths are not checked for existence. |
| `news` | `NEWS_<CATEGORY>_CHANNEL_ID` for the 11 categories, `NEWS_AUTO_POST` | `config.news.channel_id('kev')` or `config.news.kev`. See [Channel Configuration](CHANNEL_CONFIGURATION.md). |
| `posting` | `XKCD_POST_CHANNEL_ID`, `XKCD_POLL_INTERVAL_MINUTES`, `COMIC_POST_CHANNEL_ID`, `SOLAR_POST_CHANNEL_ID` | |
| `metrics` | `METRICS_ENABLED`, `METRICS_PORT` | |
| `ai` | `AI_*`, `OLLAMA_*`, `GEMINI_API_KEY` | Global defaults plus a per-feature `AiFeatureConfig` for roasting, moderation, news, cve and legislation. |
| `moderation` | `MOD_*`, `AI_MODERATION_SECOND_*` | |
| `greeter` | `WELCOME_*` | |
| `helper` | `HELPER_*` | |
| `role_picker` | `ROLE_PICKER_ENABLED` | |
| `profile_screen` | `PROFILE_SCREEN_*` | |
| `skid_detector` | `SKID_DETECTOR_*`, `SKID_FIRE_CHANCE`, `SKID_COOLDOWN_SECONDS` | |
| `banter` | `ARCH_BANTER_LLM` | |
| `events` | `EVENTS_*` | Reminders and the digest are logged, not sent, while `EVENTS_DRY_RUN` is true; moderator cards still post. See [Con Recon](../features/CON_RECON.md). |

Optional features default off. Defaults and per-variable descriptions
live in `.env.example`.

The secrets-manager bootstrap variables (`SECRETS_MANAGER`, `DOPPLER_*`,
`SECRETS_VAULT_*`, `AWS_SECRET_NAME`, `VAULT_SECRET_PATH`) are read by
`utils/secrets.py` itself and are deliberately not part of `Config`; the
config loader depends on them.

## Value shapes

| Shape | Accepted |
|---|---|
| bool | `true/false`, `yes/no`, `on/off`, `1/0`, case-insensitive |
| int | Digits, with an optional minimum and maximum per variable |
| snowflake | 17 to 20 digits. `<#id>`, `<@id>`, `<@&id>` and surrounding quotes are stripped first, so a pasted channel mention works |
| snowflake list | Comma or whitespace separated ids; each bad entry is reported |
| word list | Comma-separated, whitespace trimmed, lower-cased unless noted |
| time | `HH:MM`, 24-hour |
| timezone | An IANA name that `zoneinfo` can load |
| log level | `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |

An empty string is the same as unset. A value starting with `your_` is
also treated as unset, so an unedited `.env.example` placeholder reports
"required, not set" rather than being sent to Discord as a token.

## Secrets

Values are resolved in the same order the cogs always used: the secrets
manager first (`utils.secrets.get_secret(platform, key)`, where the
platform is the variable's prefix, `MOD` for `MOD_ALERT_CHANNEL_ID`),
then the process environment, which `load_dotenv()` has already filled
from `.env`.

Secret-shaped values (`DISCORD_BOT_TOKEN`, `GEMINI_API_KEY`) are wrapped
in `Secret`. Its `repr` and `str` are `Secret(***)`, the token field is
excluded from the dataclass repr, and nothing in this module logs a value.
Call `.reveal()` at the one place the raw string is needed, which is
`bot.run()` or `client.start()`.

## Import-time reads

Three things must be configured before `load_config()` can run: logging
(so the config error has somewhere to go), the metrics module constants,
and the runners' `DATA_DIR`. They use the lenient section loaders
`load_logging_config()`, `load_metrics_config()` and
`load_paths_config()`, which substitute defaults for anything malformed
and never raise. The same malformed value is then reported by
`load_config()` a moment later, so nothing is swallowed.

## In tests

`load_config(env={...})` takes a plain mapping and never touches
`os.environ`, `.env` or a secrets manager. Build the smallest environment
the test needs:

```python
config = load_config({'DISCORD_BOT_TOKEN': 'x', 'NEWS_KEV_CHANNEL_ID': '123456789012345678'})
assert config.news.kev == 123456789012345678
```

To assert on the error list, catch `ConfigError` and inspect `.problems`.

## Adding a variable

1. Add a typed field with a default to the section dataclass in
   `utils/config.py`. If no section fits, add a new frozen dataclass and
   a field for it on `Config`.
2. Read it in that section's `_load_*` function with the matching
   `_Reader` method (`r.bool`, `r.snowflake`, `r.words`, ...). Pass
   `minimum`/`maximum` for ints that have a sane range. Use `r.secret`
   for anything that should never be echoed.
3. If the prefix is new and should be resolvable through the secrets
   manager, add it to `_SECRET_PLATFORMS`.
4. Document it in `.env.example` and, if it belongs to a feature guide,
   there too.
5. Add a case to `tests/unit/test_config.py`: the happy path, and the
   error text for one malformed value.
6. Read it from `config.<section>.<field>` in the code. Cogs that have
   not migrated yet can still call `os.getenv`, but new code should not.

## Migration status

Migrated: `bot.py`, the five runners, `utils/logging_setup.py`,
`utils/metrics.py`. Cogs and the `ai/` package still read the environment
themselves; the bot exposes `self.config` so they can switch over one at
a time.
