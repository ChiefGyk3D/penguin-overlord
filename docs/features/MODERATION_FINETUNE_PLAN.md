# Moderation Model Fine-Tune Plan (llama-guard3:8b)

Status: **planned — do not execute yet.** Written 2026-08-28 while the
alert-first moderation phase was deployed. Execute only when the
preconditions below are met.

## Why

Benchmarked stock `llama-guard3:8b` against the Vicomtech hate-speech
dataset (150-sentence balanced sample, via the bot's real prompt + parser,
`scripts/eval-moderation/eval_guard.py`):

- Recall on hate-labeled sentences: **70.7%**
- False-positive rate on benign sentences: **21.3%**

Both numbers have clear headroom. Dry-run + human labels absorb the FPs
today; the recall gap is what training should close.

## Preconditions (all required)

1. Several hundred moderator ✅/❌ calibration labels accumulated in
   `mod_infractions` (the in-domain data nothing public can replace).
2. `/mod stats` reviewed — categories where precision is weak inform the
   blend weights.
3. A free afternoon for the AI server's 16 GB GPU (the `:11434` instance):
   both inference models get unloaded during training. The bot stays up —
   moderation degrades to regex + deny-list, roasts fall back to static
   jokes. The second GPU's instance is unaffected.
4. Export/bump retention first: excerpts purge after `MOD_RETENTION_DAYS`
   (90 default) — export labels before they age out.

## Training data blend

| Dataset | Role | Access | License |
|---|---|---|---|
| Own calibration labels (`mod_infractions`) | In-domain ground truth; highest weight per example | export from DB | ours |
| [Vicomtech hate-speech-dataset](https://github.com/Vicomtech/hate-speech-dataset) | ~10k explicit-hate sentences (hate/noHate) | GitHub clone | CC BY-SA 3.0 ES |
| [ToxiGen](https://huggingface.co/datasets/toxigen/toxigen-data) | Implicit/coded hate + benign identity mentions — targets BOTH the recall gap and the FP rate | HF, short access form | research |
| [HateXplain](https://github.com/hate-alert/HateXplain) | hate vs offensive vs normal, with target groups — sharpens hate_speech/harassment boundary | GitHub/HF | MIT |
| [Civil Comments](https://huggingface.co/datasets/google/civil_comments) | Volume source of BENIGN informal comments (+ threat/insult labels); heavy on the safe side of the blend | HF | CC0 |
| [Aegis 2.0 / Nemotron Content Safety V2](https://huggingface.co/datasets/nvidia/Aegis-AI-Content-Safety-Dataset-2.0) | Taxonomy-preserving backbone — near Llama Guard S-codes, NVIDIA's own LlamaGuard fine-tune used it; prevents forgetting the other 12 categories | HF | see card |
| [WildGuardMix](https://huggingface.co/datasets/allenai/wildguardmix) | Optional: adversarial/in-the-wild safety examples | HF | see card |
| [Dynabench DGHS](https://github.com/bvidgen/Dynamically-Generated-Hate-Speech-Dataset) | Optional: adversarial hate written to fool classifiers (evasion) | GitHub | check |

**Held-out eval (never in training):** OpenAI moderation eval set
(~1.7k, multi-category), a Vicomtech test split, and a frozen sample of
own calibration labels.

**No public data for `self_harm`** — serious corpora are
access-restricted; it is a forced-human-review category, so leave the base
model's behavior untouched there.

## Label → Llama Guard output mapping

Training targets use the guard's NATIVE protocol (what
`ai/features/moderation.py::_parse_guard_response` parses):

- benign/noHate/normal → `safe`
- hate (explicit or implicit) → `unsafe\nS10`
- threat/violence → `unsafe\nS1`
- privacy/doxxing → `unsafe\nS7`
- self-harm (from Aegis only) → `unsafe\nS11`
- sexual content → `unsafe\nS12`
- Aegis/WildGuardMix rows keep their existing S-code-aligned labels

Wrap every example in the same user-turn shape the bot sends
(`Message from '<user>' in #<channel>: """..."""`) so train matches serve.

## Blend ratios (starting point, tune by eval)

~40% benign (Civil Comments safe + noHate + own false positives),
~25% Aegis backbone (all categories), ~20% explicit+implicit hate
(Vicomtech + ToxiGen + HateXplain), ~10% own confirmed labels
(oversampled ×3–5), ~5% adversarial. Dedup + decontaminate against all
eval sets before training.

## Training run (on the AI server, 16 GB GPU)

1. Unload inference models on `:11434` (`keep_alive: 0` generate calls).
2. QLoRA via Unsloth (or axolotl): 4-bit base, LoRA r=16 α=32 on
   attention+MLP projections, lr 1e-4 cosine, 1–2 epochs, seq len 1024,
   effective batch ≥32 via grad accum. Expect ~2–5 h.
3. Merge LoRA → fp16, convert to GGUF, quantize Q4_K_M (~30–45 min).
4. `ollama create llama-guard3:8b-penguin -f Modelfile` on the `:11434`
   instance (FROM the quantized GGUF; keep the base model's template).

## Evaluate → deploy → rollback

1. Re-run `scripts/eval-moderation/eval_guard.py` against the held-out
   sets for base vs fine-tuned. Acceptance: recall +10pts or more on
   hate held-out, FP rate not worse, no category regression on the
   multi-category set.
2. Deploy: set `AI_MODERATION_MODEL=llama-guard3:8b-penguin`, keep
   `MOD_DRY_RUN=true`, recreate the container. Watch `/mod stats`
   precision for 1–2 weeks before any enforcement talk.
3. Rollback = set the model var back to `llama-guard3:8b`. Keep the base
   model pulled.

Timing summary: prep ~30 min, first-time env setup 30–60 min, training
2–5 h, convert 30–45 min, eval ~30 min. One afternoon; bot never goes
down.
