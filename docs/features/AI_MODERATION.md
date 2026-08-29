# AI Features: Ollama Roasts & Alert-First Moderation

This document is the operator guide for the AI subsystem added on the
`claude/discord-bot-moderation-ai-5va77u` branch. The staging strategy and
rationale live in [docs/ASSESSMENT_AND_AI_ROADMAP.md](../ASSESSMENT_AND_AI_ROADMAP.md).

Everything is **off by default**. A fresh deployment of this branch behaves
exactly like the bot did before.

## Architecture

```
cogs/arch_banter.py ─┐
cogs/ai_moderation.py ┤→ ai/manager.py → ai/queue.py (bounded) → ai/providers.py
                      │        │                                   ├─ OllamaProvider (async, local)
                      │        └─ ai/guardrails.py                 └─ GeminiProvider (optional, never moderation)
                      └→ utils/database.py (aiosqlite: infractions, verdicts, pending actions)
```

- **Local-first**: Ollama via `ollama.AsyncClient`, hard timeouts on every
  network call, rate-limited reconnects. A dead Ollama box degrades every
  feature to its non-AI behavior — users never see errors.
- **Guardrails**: prompt-injection sanitization on input; think-tag /
  preamble cleanup, emoji caps, mass-mention neutralization, a dedup cache,
  and a **hard slur deny-list** (leet/spacing/repeat-normalization aware,
  extensible via `data/blocklist.txt`) on ALL model output.
- **Privacy floor**: moderation inference never leaves your network — the
  Gemini fallback flag is ignored for the moderation feature in code, not
  just by convention.

## Quick start: AI Arch roasts

```env
AI_ENABLED=true
OLLAMA_HOST=192.168.1.50          # your Ollama box
AI_DEFAULT_MODEL=llama3.2
AI_ROASTING_ENABLED=true
ARCH_BANTER_LLM=true
```

Static jokes remain the fallback for every failed, slow, or
guardrail-blocked generation.

## Quick start: moderation (dry-run)

```env
AI_ENABLED=true
OLLAMA_HOST=192.168.1.50
AI_MODERATION_ENABLED=true
AI_MODERATION_MODEL=llama-guard3:8b   # or llama3.2 to start
```

Both response styles are understood: Llama Guard's native protocol
(`safe` / `unsafe` + S-codes, mapped onto our categories) and the
instruction template general models are prompted with. Anything else is
treated as unparseable and forces `review`.

Guard models are prompted with the **bare message only** — no username
wrapper, channel context, prior-flag notes, or system prompt. Llama
Guard's chat template classifies the entire user turn as conversation
content, so any metadata we add is contamination: measured live, an
innocent "Nigerian Prince" flagged as doxxing because the channel context
quoted an earlier SSN test message. The cost is that guard models cannot
use cross-message context (template models still get the full prompt);
the payoff halved the false-positive rate on out-of-domain benchmarks.
Messages with no letters (emoji spam, bare mentions) skip the LLM
entirely — regex scans still run on everything.

### Two-stage second opinion (recommended with a guard model)

```env
AI_MODERATION_SECOND_MODEL=gemma3:12b       # template model; guard models refused
# AI_MODERATION_SECOND_CATEGORIES=hate_speech,harassment   (default)
# AI_MODERATION_SECOND_MIN_CONFIDENCE=0.85                 (default)
```

Messages the primary model calls safe get a second pass through an
instruction-following model with the FULL rich prompt (context is safe
there — template models actually obey "analyze the message, not the
context"). Only its high-confidence verdicts in the configured categories
count; everything else is ignored, because its non-hate verdicts (violence
on game vocabulary, spam on scam jokes) are measured noise. Measured with
llama-guard3:8b + gemma3:12b: golden-set hate recall 92% → 100% with the
clean false-positive rate unchanged at 3%; Vicomtech recall 58.7% → 78.7%.
Cost: one extra model call per scanned message that the primary passed.

```env
MOD_ENABLED=true
MOD_DRY_RUN=true                      # alert-only; the default
MOD_ALERT_CHANNEL_ID=<private mod channel id>
MOD_CHANNELS=<one busy channel id>    # allowlist; start with ONE channel
MOD_PING_ROLE_ID=<moderator role id>  # optional: @mention this role on alerts
```

All `MOD_*` settings can live in your secrets manager (Doppler/AWS/Vault)
instead of `.env` — same layering as the `AI_*` keys.

What happens:

1. Messages in allowlisted channels are scanned — regex PII + slur
   deny-list on everything, LLM classification for messages ≥
   `MOD_MIN_MESSAGE_LENGTH` (per-user cooldown applies).
2. Detections post an alert embed to the mod channel: jump link, category,
   confidence, model reasoning, PII types, prior flags for that user.
3. **Moderators label each alert** with ✅ (confirmed) or ❌ (false
   positive) — one click. High-severity detections carry
   Approve/Dismiss buttons instead (restart-proof).
4. `/mod stats` shows per-category precision from those labels. This is
   the calibration dataset for any future enforcement.
5. `/mod test text:...` runs the analyzer on sample text without storing
   anything — use it to try slur evasions and borderline cases against
   your chosen model.

Tuning alert noise (all optional):

```env
MOD_ALERT_MIN_CONFIDENCE=0.6   # mute non-forced alerts below this confidence
MOD_IGNORED_CATEGORIES=misinformation,spam   # categories to never alert on
```

Forced-review categories (hate_speech/doxxing/self_harm/violence) and
blocklist hits ignore both knobs — they always alert. To see what your
moderators' ❌ labels actually point at, run on the bot host:

```bash
python scripts/eval-moderation/fp_report.py --days 14
```

It groups alerts by category with per-category precision and replays each
false positive through the current regex filters, separating "filter bug
(fixed/still firing)" from "model verdict" so you know what to tune next.

### Golden-set tests

`penguin-overlord/ai/moderation_golden.json` is a labeled corpus of known hate
speech (slurs, leet/spacing evasions, slur-free tropes and dog whistles)
and known-clean messages (identity affirmations like "I'm Jewish and bi",
tech chat, banter). Two tiers consume it:

- **CI gate (deterministic)** — `tests/unit/test_moderation_golden.py`:
  every slur-bearing hate example must trip the deny-list (even with the
  model down) and no clean example may ever trip the deny-list or PII
  scan. Runs on every PR; a regression here fails the build.
- **Live-model benchmark** — on the bot host:

  ```bash
  OLLAMA_HOST=http://192.168.1.50:11434 AI_MODERATION_MODEL=llama-guard3:8b \
      python -m pytest tests/unit/test_moderation_live.py -m network -s
  ```

  Prints overall accuracy, hate recall (overall and on the slur-free tier
  only the model can catch) and the clean false-positive rate, listing
  every miss and FP. Run it before/after any model or prompt change.
- **In Discord** — `/mod benchmark` runs the same corpus through the live
  analyzer and posts the accuracy summary to the mod channel (one model
  call per example; takes a few minutes). `/mod stats` now leads with the
  live alert accuracy computed from your moderators' ✅/❌ labels.

The corpus ships with the bot at `penguin-overlord/ai/moderation_golden.json`
— grow it from real moderator labels (`fp_report.py` shows candidates) and
every added line is pinned by CI forever.

Hard rules enforced by the policy layer (covered by unit tests):

- `hate_speech`, `doxxing`, `self_harm`, `violence` and every kick/ban
  proposal **always require a human** — never auto-actioned in any mode.
- A deny-listed slur alerts as hate_speech even when the model is down or
  calls it safe.
- Malformed model output forces `review` — never silently safe.

Data handling: only the first 300 characters of a flagged message are
stored, purged after `MOD_RETENTION_DAYS` (90 default); `/mod purge_user`
deletes everything stored about a user.

## Graduating to enforcement (Phase 3 — not yet recommended)

Only after ≥2 weeks of dry-run and `/mod stats` showing the precision you
want:

```env
MOD_DRY_RUN=false
MOD_AUTO_DELETE=true       # opt in per action
# MOD_AUTO_TIMEOUT=true
MOD_MIN_CONFIDENCE=0.85    # raise from calibration data
```

Auto-actions apply only to categories outside the forced-review set and
only at/above the confidence floor. Setting `MOD_DRY_RUN=true` again is
the instant kill switch.

## Metrics / Grafana

```env
METRICS_ENABLED=true
METRICS_PORT=9200
```

Prometheus scrape target: `http://<bot-host>:9200/metrics`. Exposed series
include `penguin_bot_connected`, `penguin_gateway_latency_seconds`,
`penguin_ai_requests_total{feature,outcome}`, `penguin_ai_request_seconds`,
`penguin_mod_alerts_total{category}`, `penguin_mod_verdicts_total{verdict}`.
With metrics enabled the Docker healthcheck verifies real gateway
connectivity instead of always passing. Remember to publish the port
(e.g. `-p 9200:9200` or in docker-compose) so Prometheus can reach it.

## Model suggestions

| VRAM | Roasting | Moderation |
|------|----------|------------|
| 8 GB | `llama3.2` (3B) | `llama-guard3:8b-q4_0` or `llama3.1:8b-q4` |
| 12–16 GB | `llama3.1:8b` | `llama-guard3:8b` |
| 24 GB+ | `qwen3:14b` | `qwen3:14b` + guard model on 2nd host |

Different features can point at different hosts/models via
`AI_<FEATURE>_OLLAMA_HOST` / `AI_<FEATURE>_MODEL`.

## Fine-tuning the moderation model (future)

The calibration labels this system collects are the seed of a fine-tuning
dataset. The full plan — data blend, Llama Guard label mapping, QLoRA run,
eval gates, rollout/rollback — lives in
[MODERATION_FINETUNE_PLAN.md](MODERATION_FINETUNE_PLAN.md), and
`scripts/eval-moderation/eval_guard.py` is the benchmark that gates it.
