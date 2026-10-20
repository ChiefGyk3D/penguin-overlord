# Roast data

The Arch and NixOS roasts used to repeat themselves: one fixed list of
stereotypes in a prompt written in Python, no memory of recent output, and
one format. The wording now lives in data files so it can be replaced
without a code change, and the code rotates and de-duplicates it.

Ollama still writes every AI roast. The data files only steer it.

## Where the files live

| File | Purpose |
|---|---|
| `penguin-overlord/ai/features/roast_data/arch.json` | Arch prompt, angles, formats, fallback jokes, house jokes |
| `penguin-overlord/ai/features/roast_data/nix.json` | The same for NixOS (no house jokes) |

The static fallback banks (`ARCH_JOKES`, `NIX_JOKES`, `HOUSE_JOKES` on the
`ArchBanter` cog) are derived from these files, so the `arch_banter_stats`
count and the no-repeat pick logic keep working unchanged.

## Schema (version 1)

Strict: unknown keys, duplicate keys, wrong types, NaN or Infinity, blank
entries and files over 256 KiB are rejected with a clear error.

| Key | Type | Required | Notes |
|---|---|---|---|
| `schema_version` | integer | yes | Must be `1`. |
| `system_prompt` | string | yes | Multi-line, up to 8000 characters. Must contain each placeholder below exactly once. |
| `user_prompt_tail` | string | yes | Last line of the user prompt. May use `{distro_name}` and `{max_length}`. |
| `max_length` | integer 20 to 1000 | no | Default 120. The character limit told to the model. |
| `avoid_header` | string | no | Heading printed above the recent-roasts list. |
| `exemplar_header` | string | no | Heading printed above the exemplars. |
| `angles` | list of strings | yes | One stereotype or theme per entry. Non-empty, up to 64, no duplicates. |
| `formats` | list of objects | yes | See below. Non-empty, up to 16, unique names. |
| `exemplars` | list of strings | no | If non-empty, a few are injected per call as few-shot examples. |
| `banned_phrases` | list of strings | no | Output containing one (case-insensitive) is rejected. |
| `fallback_jokes` | list of strings | yes | The static bank used when AI is off or fails. Non-empty, up to 500. |
| `house_jokes` | object | no | `{"chance": 0.12, "jokes": [...]}`. Arch only today. Chance is 0 to 1. |

Each `formats` entry is `{"name": ..., "instruction": ..., "max_length": ...}`.
`instruction` is text added to the prompt for that format (empty is fine).
`max_length` is optional and overrides the top-level limit for that format.
The shipped files have one format, `one-liner`, so behaviour is unchanged
until more are added.

### Placeholders in `system_prompt`

| Placeholder | Replaced with |
|---|---|
| `{angles}` | The sampled angles, one `  * angle` line each |
| `{exemplars}` | `exemplar_header` plus a few `- exemplar` lines, or nothing |
| `{format}` | The chosen format's `instruction`, or nothing |
| `{avoid}` | `avoid_header` plus the recent roasts as `- roast` lines, or nothing |

A placeholder that renders empty removes its whole line. Substitution is
single pass, so text inserted for one placeholder is never expanded as
another.

### House style

Loaded text is stripped of em dashes the same way the skid detector strips
model output (a spaced one becomes a colon and space, a bare one becomes a comma). `system_prompt`
is exempt because it is instruction text and names the rule itself.
Model output containing an em dash is rejected.

## Operator override directory

Set `ARCH_BANTER_DATA_DIR` to a directory containing `arch.json` and/or
`nix.json`. A valid file there replaces the shipped file wholesale (no
merging). If it is missing, the shipped file is used silently. If it is
invalid, a warning naming the file and the problem is logged and the shipped
file is used. File contents are never logged.

The override is read as untrusted input: the file is opened without
following symlinks, must be a regular file, and is size-capped before
parsing.

## Rotation and repetition control

Per roast, in code:

1. Sample `ARCH_BANTER_ANGLES_PER_CALL` angles (default 2), avoiding angles
   used in the last `ARCH_BANTER_ANGLE_WINDOW` calls (default 6). If the pool
   is too small for that, the least recently used angles fill in.
2. Choose one format, avoiding the one used last.
3. Inject the last `ARCH_BANTER_RECENT_ROASTS` accepted roasts (default 12)
   as an avoid block. They are run through `sanitize_input` first, because a
   roast can echo user text.
4. Review the output. An em dash or a banned phrase rejects it. More than
   one emoji is repaired by dropping the extras (zero emoji is accepted).
   A near duplicate of a recent roast rejects it: normalised token Jaccard
   at or above `ARCH_BANTER_DUP_THRESHOLD` (default 0.6).
5. On a rejection, retry once with a higher temperature (plus 0.15, capped
   at 1.3). If the retry is rejected too, the roast is `None` and the cog
   posts a fallback joke.

Other knobs: `ARCH_BANTER_TEMPERATURE` (default 0.85) and
`ARCH_BANTER_MAX_TOKENS` (default 80). Each ring is per distro and lives in
memory only.

Context cost: the avoid block adds up to about a dozen short lines to the
system prompt, which fits a small context.

## Measuring

`scripts/eval-roasts/eval_roasts.py` generates N roasts per distro through
the real roaster and AI manager and writes a JSON report. It calls Ollama,
so it runs only when a human passes `--live`.

```
python scripts/eval-roasts/eval_roasts.py --live --n 40 --out /tmp/roast-report.json
python scripts/eval-roasts/eval_roasts.py --live --n 40 \
    --data-dir ./draft-roast-data --out /tmp/roast-report-draft.json
```

It reports, per distro: distinct-roast ratio, mean pairwise Jaccard, top
repeated 3-grams, angle and format usage, em dash violations, emoji-count
violations, retries and failures. Higher distinct ratio and lower mean
Jaccard are better.

## Workflow

1. ChatGPT drafts the data files: prompt wording, angles, formats,
   exemplars, banned phrases and fallback jokes.
2. Claude integrates them (drops the files in, fixes schema errors) and
   measures before and after with the eval script, pointing `--data-dir`
   at the draft.
3. The maintainer approves the public copy before the files replace the
   shipped ones.

Code never writes jokes. Claude does not author roast language.
