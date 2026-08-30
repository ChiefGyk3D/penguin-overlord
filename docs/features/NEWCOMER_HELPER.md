# Newcomer helper

"Where do I start with this?" gets asked constantly in a learning-oriented
server, usually by someone who has not found the pinned channels yet. This
answers once, politely, and then gets out of the way.

The governing constraint is the same one moderation runs on: **a false
positive is expensive**. A bot that replies to messages that were not
questions is worse than one that stays quiet, because members learn to tune
it out. Everything below exists to make silence the default.

## Configuration

```env
HELPER_ENABLED=true
HELPER_CHANNELS=123,456              # REQUIRED allowlist — empty watches nothing
HELPER_RESOURCE_CHANNEL_ID=789       # REQUIRED — the channel to point at
HELPER_RULES_CHANNEL_ID=012          # optional second channel
HELPER_TIERS=new                     # trust tiers eligible for the nudge
HELPER_COOLDOWN_SECONDS=60           # per-channel quiet period
HELPER_USER_COOLDOWN_SECONDS=1800    # per-person quiet period
HELPER_MIN_LENGTH=12                 # ignore very short messages
HELPER_USE_LLM=true                  # let the second model veto a weak match
HELPER_MESSAGE=                      # template; see below
```

With `HELPER_ENABLED=true` but no allowlist or no resource channel, the cog
logs an error and disables itself rather than guessing.

### The message

Default:

> Welcome {user}! Please have a look at {rules}, and {resources} is the best
> place to start.

Placeholders: `{user}` (a mention), `{resources}`, `{rules}` (channel
mentions), and `{rules_clause}` — the "Please have a look at …, and " phrase,
which disappears when no rules channel is configured. Set your own with
`HELPER_MESSAGE`; a template referencing an unknown placeholder falls back to
the default wording rather than silencing the feature.

```env
HELPER_MESSAGE=Welcome {user}! Please read {rules} and start with {resources}.
```

## How a message qualifies

1. **Tier** — only `HELPER_TIERS` (default `new`, meaning under
   `MOD_MEMBER_DAYS`). A two-year regular asking where to start is just
   conversation. Tiers come from the same `utils/trust.py` moderation uses,
   so one member is one tier everywhere.
2. **Pattern** — a deterministic regex must match a request for *direction*
   ("where do I start", "any good resources", "point me in the right
   direction"). Merely containing "learn" or "resources" is not enough:
   *"i learned that the hard way"* and *"here are some resources I put
   together"* do not match.
3. **Not a support question** — "any resources on why my nmap scan fails"
   wants a human with an answer, not a signpost, so specific-problem
   phrasing (error, traceback, not working, why is my …) disqualifies it.
4. **Cooldowns** — one per channel so the bot never chatters, one per person
   so nobody gets followed around.
5. **Model veto** (optional) — the second-stage model can overrule a
   borderline pattern match. When it is unavailable the regex match stands:
   a downed model must not silently switch the feature off.

Only steps 4 and 5 cost anything beyond a regex, and step 5 only runs on
messages that already matched.

Verified against the live models: 6/6 on a hand-built set, including the two
that must stay quiet (*"here are some resources i put together for you all"*
and *"any resources on why my nmap scan fails to resolve"*).

Replies are counted in `penguin_helper_replies_total`, never ping the room
(`@everyone`/roles are disabled), and do not force a reply-ping on the
author.
