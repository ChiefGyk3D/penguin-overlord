# Threat model

`penguin-overlord.threat-dragon.json` is an OWASP Threat Dragon v2 model of the Discord bot and its AI layer. It was written from a read of `penguin-overlord/` at commit e3f484d. Open it in the Threat Dragon desktop or web app with File > Open.

Two diagrams: "Discord bot core" (actors, cogs, SQLite, data volume, secrets, CI) and "AI layer" (sanitizer, guardrails, AIManager and queue, Ollama and Gemini). Every cell and threat cites the file or function it was taken from. Not a full audit.

## Trust boundaries

- Discord platform: members, moderators and other bots; message text, names and edits are attacker-controlled.
- Bot container: the Python process, SQLite database and data volume.
- Operator, secrets and CI: environment, Doppler/AWS/Vault, GYST build and release.
- Third-party feeds and APIs: RSS, CVE and KEV sources (never sent to a model).
- Untrusted text sources: everything that enters a prompt (messages, names, cached #rules).
- Inference hosts: operator-run Ollama and the optional Gemini API.

## Open threats

No Critical or High threat is Open. Open Medium:

- Prompt injection can steer the moderation classifier to "safe" (phrase-based sanitizer, unescaped fence).
- Injection through context messages, display names and profile names is not marker-checked.
- A message flood fills the shared AI queue and silently disables model-tier moderation.
- Inference traffic to Ollama is cleartext and unauthenticated from the bot side.

Open Low: long-message truncation to 1500 characters, arch_banter has no `allowed_mentions`, links/markdown in model output, Gemini fallback for roasting (opt-in), metrics endpoint on all interfaces, writable data files, webhook and bot authors unscanned.

## UNVERIFIED

- Deployment topology: how the Ollama host is reached, whether the metrics port is exposed.
- Who can read the moderation alert channel and write to the #rules channel (Discord permissions).
- Every news/CVE/KEV cog's embed construction, response size limits and URL validation.
- Welcome greeter, events cogs and admin cog were not reviewed in depth.
- Tests cited (tests/unit/test_moderation.py, test_ai_guardrails.py) were not re-run for this model.
