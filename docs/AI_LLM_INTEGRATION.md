# AI & LLM Integration Guide

Penguin Overlord includes a multi-provider AI system that powers contextual features across the bot. This guide covers everything from architecture to hardware selection to deployment.

> **New to Ollama?** Skip to [Quick Start](#quick-start) for the fastest path to running AI features.

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Quick Start](#quick-start)
- [How It Works](#how-it-works)
- [Hardware Recommendations](#hardware-recommendations)
- [Model Selection Guide](#model-selection-guide)
- [Configuration Reference](#configuration-reference)
- [Multi-Server Setup (FrankenLLM)](#multi-server-setup-frankenllm)
- [Secrets Management (Doppler / AWS / Vault)](#secrets-management)
- [Current AI Features](#current-ai-features)
- [Recommended Future AI Features](#recommended-future-ai-features)
- [Troubleshooting](#troubleshooting)

---

## Architecture Overview

The AI system is designed around **per-feature routing** — each bot feature (roasting, news analysis, CVE analysis, moderation) can use a different LLM, on a different server, with independent fallback behavior.

```
┌─────────────────────────────────────────────────────────────┐
│                        AIManager                            │
│  Central orchestrator — routes requests per feature config  │
├──────────┬──────────┬───────────────┬───────────────────────┤
│          │          │               │                       │
│    RequestQueue     │         Provider Pool                 │
│  (concurrency +     │                                       │
│   rate limiting)    │                                       │
│          │          │                                       │
│          ▼          ▼                                       │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────────────┐  │
│  │ Ollama   │ │ Ollama   │ │ Ollama   │ │    Gemini     │  │
│  │ Server 1 │ │ Server 2 │ │ Server 3 │ │   Fallback    │  │
│  │ :11434   │ │ :11435   │ │ :11434   │ │  (cloud API)  │  │
│  │ GPU box  │ │ GPU box  │ │ Remote   │ │               │  │
│  └──────────┘ └──────────┘ └──────────┘ └───────────────┘  │
├─────────────────────────────────────────────────────────────┤
│                     Feature Modules                         │
│  ┌───────────┐ ┌────────────┐ ┌───────────┐ ┌───────────┐  │
│  │   Arch    │ │   News     │ │   CVE     │ │Moderation │  │
│  │  Roaster  │ │  Analyzer  │ │ Analyzer  │ │ Analyzer  │  │
│  │           │ │            │ │           │ │  (stub)   │  │
│  └───────────┘ └────────────┘ └───────────┘ └───────────┘  │
└─────────────────────────────────────────────────────────────┘
```

**Key design principles:**

| Principle | Implementation |
|-----------|---------------|
| **Per-feature routing** | Each feature can target a different Ollama server and model |
| **Graceful fallback** | Gemini API as optional per-feature fallback when Ollama is down |
| **Thinking model support** | Handles Qwen3 and DeepSeek-R1 reasoning output natively |
| **Request queuing** | Async semaphore + rate limiting prevents server overload |
| **Auto-reconnect** | Automatic reconnection with configurable backoff |
| **Backward compatibility** | Old `OLLAMA_*` env vars still work alongside new `AI_*` system |

---

## Quick Start

### Minimal Setup (Single Server, One Model)

```bash
# 1. Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# 2. Pull a model (pick one based on your GPU VRAM)
ollama pull gemma3:4b      # 8GB VRAM
# OR
ollama pull gemma3:12b     # 16GB VRAM
# OR
ollama pull qwen3:8b       # 16GB VRAM (thinking model)

# 3. Add to your .env
echo "AI_ENABLED=true" >> .env
echo "AI_DEFAULT_MODEL=gemma3:4b" >> .env
echo "ARCH_BANTER_LLM=true" >> .env

# 4. Install the Python dependency (already in requirements.txt)
pip install ollama

# 5. Start the bot — AI features are now active
python main.py
```

### With Gemini Fallback

```bash
# Add your Gemini API key (free tier: https://aistudio.google.com/app/apikey)
echo "GEMINI_API_KEY=your_key_here" >> .env
echo "AI_GEMINI_FALLBACK=true" >> .env

# Install the Gemini SDK
pip install google-genai
```

---

## How It Works

### Request Flow

When any AI feature is triggered (e.g., an Arch Linux mention, a news article posted, a CVE detected):

1. **Feature module** creates a prompt with an appropriate system prompt
2. **AIManager** looks up the feature's config → determines provider, model, server
3. **RequestQueue** enforces concurrency limits (default: 4 concurrent, 1s min delay)
4. **Primary provider** (Ollama or Gemini) attempts generation with retry logic
5. **If primary fails** and Gemini fallback is enabled → tries Gemini automatically
6. **Response** is returned to the feature module for formatting and posting

### Thinking Model Support

Models like **Qwen3** and **DeepSeek-R1** output their reasoning in a separate `thinking` field before generating the final answer. The system handles this automatically:

```
Standard model response:
  {"message": {"content": "Here's your roast..."}}

Thinking model response:
  {"message": {"content": "", "thinking": "Let me think about what makes this funny... 
   The user mentioned i3 which is a tiling WM... Final answer: ..."}}
```

When a thinking model returns empty `content`, the system extracts the final answer from the `thinking` field using cascading strategies:
1. Look for explicit markers ("Final answer:", "Here's the response:")
2. Look for quoted output lines
3. Extract the last substantial paragraph
4. Return `None` if nothing usable (triggers fallback)

Thinking models are **auto-detected** for known families (Qwen3, DeepSeek-R1). You can also force thinking mode via `AI_ENABLE_THINKING_MODE=true`.

### Retry & Reconnection

| Event | Behavior |
|-------|----------|
| Transient error (503, 429, timeout) | Exponential backoff retry (default: 3 retries, base delay 2s → 1s, 2s, 4s) |
| Connection refused/lost | Marks provider as disconnected, triggers auto-reconnect |
| Auto-reconnect | Tries every 60s (configurable), resets on success |
| All providers fail | Returns `None` → feature gracefully degrades to non-AI behavior |

### Graceful Degradation

Every AI-enhanced feature has a non-AI fallback:

| Feature | AI Mode | Fallback Mode |
|---------|---------|---------------|
| Arch Roaster | Contextual LLM-generated roasts | 130+ static pre-written jokes |
| News Analyzer | AI-generated article summaries | Raw article title + link (existing behavior) |
| CVE Analyzer | AI severity assessment + remediation | CVSS score + NVD description |
| Moderation | Contextual intent analysis | Regex pattern matching (future) |

---

## Hardware Recommendations

### GPU VRAM Requirements

AI models run in GPU VRAM. The model size determines the minimum VRAM needed:

| VRAM | Recommended Models | Use Case |
|------|-------------------|----------|
| **6 GB** | `gemma3:1b`, `phi3:mini`, `tinyllama` | Basic roasting only |
| **8 GB** | `gemma3:4b` ⭐, `llama3.2:3b`, `qwen2.5:3b` | Roasting + basic analysis |
| **12 GB** | `gemma3:12b`, `mistral:7b`, `qwen2.5:7b` | All features, good quality |
| **16 GB** | `gemma3:12b` ⭐, `qwen3:8b`, `llama3.1:8b` | All features, excellent quality |
| **24 GB** | `gemma3:27b` ⭐, `qwen3:14b`, `qwen2.5:14b` | Premium quality, long analysis |
| **32 GB+** | `qwen3:32b`, `llama3.1:70b` (quantized) | Enterprise-grade analysis |

⭐ = Recommended "sweet spot" for that VRAM tier

### CPU-Only (No GPU)

Ollama can run on CPU, but expect **5-30x slower** responses:

| CPU | Recommended Models | Response Time |
|-----|-------------------|---------------|
| 4+ cores, 8GB RAM | `gemma3:1b`, `phi3:mini` | 5-15 seconds |
| 8+ cores, 16GB RAM | `gemma3:4b`, `llama3.2:3b` | 10-30 seconds |
| 16+ cores, 32GB RAM | `mistral:7b` | 20-60 seconds |

> **Tip:** For CPU-only setups, consider using Gemini as the primary provider for latency-sensitive features (roasting) and Ollama for background tasks (news analysis).

### Recommended Server Configurations

#### Hobby / Single Machine (1 GPU)

Best for: Personal Discord server, all features on one box.

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| GPU | RTX 3060 12GB | RTX 4060 Ti 16GB |
| RAM | 16 GB | 32 GB |
| CPU | 4 cores | 8+ cores |
| Storage | 20 GB free | 50 GB free (for multiple models) |
| OS | Ubuntu 22.04+ | Ubuntu Server 24.04 |

**Model setup:**
```bash
ollama pull gemma3:12b   # Primary — all features
```

#### Prosumer / Dual GPU (FrankenLLM-style)

Best for: Dedicated features on dedicated GPUs, better throughput.

| Component | Setup |
|-----------|-------|
| GPU 0 | RTX 4060 Ti 16GB — `gemma3:12b` (roasting + news) |
| GPU 1 | RTX 3050 8GB — `gemma3:4b` (CVE quick analysis) |
| RAM | 32 GB |
| OS | Ubuntu Server 24.04 |

```env
AI_ROASTING_OLLAMA_HOST=http://localhost:11434
AI_ROASTING_MODEL=gemma3:12b
AI_NEWS_OLLAMA_HOST=http://localhost:11434
AI_NEWS_MODEL=gemma3:12b
AI_CVE_OLLAMA_HOST=http://localhost:11435
AI_CVE_MODEL=gemma3:4b
```

#### Lab / Multi-Server (3 Machines)

Best for: Home lab with multiple AI servers, maximum throughput and model variety.

| Server | GPU | Model | Features |
|--------|-----|-------|----------|
| Server 1 (inference-1) | RTX 4090 24GB | `qwen3:14b` | News analysis, CVE analysis |
| Server 2 (inference-2) | RTX 3060 12GB | `gemma3:12b` | Arch roasting, general |
| Server 3 (moderation) | RTX 3050 8GB | `llama-guard3:8b` | Content moderation |

```env
AI_NEWS_OLLAMA_HOST=http://inference-1:11434
AI_NEWS_MODEL=qwen3:14b
AI_CVE_OLLAMA_HOST=http://inference-1:11434
AI_CVE_MODEL=qwen3:14b
AI_ROASTING_OLLAMA_HOST=http://inference-2:11434
AI_ROASTING_MODEL=gemma3:12b
AI_MODERATION_OLLAMA_HOST=http://moderation:11434
AI_MODERATION_MODEL=llama-guard3:8b
```

> **See also:** [FrankenLLM](https://github.com/ChiefGyk3D/FrankenLLM) for automated multi-GPU Ollama setup with systemd services, VRAM warmup, and health monitoring.

---

## Model Selection Guide

### By Feature

| Feature | Recommended Models | Why |
|---------|-------------------|-----|
| **Arch Roasting** | `gemma3:4b`, `gemma3:12b`, Gemini | Creative, fast, personality-driven. Gemma excels at humor. |
| **News Analysis** | `qwen3:8b`, `qwen3:14b`, `qwen2.5:7b` | Qwen models are strong at structured analysis and summarization. Thinking mode helps with nuanced assessment. |
| **CVE Analysis** | `qwen3:14b`, `llama3.1:8b`, `qwen2.5:14b` | Security analysis benefits from reasoning. Qwen3 thinking mode helps assess impact. |
| **Moderation** | `llama-guard3:8b`, `llama-guard3:1b` | Purpose-built for content classification. Fast, focused on safety categories. |

### By Model Family

| Family | Strengths | Best For |
|--------|-----------|----------|
| **Gemma 3** (Google) | Excellent at creative text, fast, multimodal, 128K context | Roasting, general chat features |
| **Qwen 3** (Alibaba) | Strong reasoning, thinking mode, multilingual, structured output | News/CVE analysis, summarization |
| **Qwen 2.5** (Alibaba) | Stable, fast, great quality-to-size ratio | Budget analysis, all-around |
| **Llama 3.x** (Meta) | Well-rounded, huge context (128K), widely tested | General purpose, CVE analysis |
| **Llama Guard 3** (Meta) | Purpose-built content safety model | Moderation (dedicated) |
| **Mistral/Mixtral** | Good instruction following, fast | General purpose |
| **DeepSeek-R1** | Strong mathematical/logical reasoning, thinking mode | Complex analysis |
| **Phi 3/4** (Microsoft) | Efficient for size, good at structured tasks | Budget setups |

### Thinking Models vs. Standard Models

| Aspect | Standard (Gemma, Llama) | Thinking (Qwen3, DeepSeek-R1) |
|--------|------------------------|-------------------------------|
| Speed | Faster | 2-4x slower (reasoning overhead) |
| Token usage | Lower | Higher (thinking multiplier: 4x) |
| Quality for analysis | Good | Better (structured reasoning) |
| Quality for creative | Good to great | Similar |
| Best for | Roasting, quick tasks | News/CVE analysis, moderation |

---

## Configuration Reference

### Environment Variables

All configuration is via environment variables (`.env` file, Doppler, or system env).

#### Global Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `AI_ENABLED` | `true` | Master switch for all AI features |
| `AI_DEFAULT_PROVIDER` | `ollama` | Default provider: `ollama` or `gemini` |
| `AI_DEFAULT_MODEL` | `gemma3:4b` | Default model for all features |
| `AI_DEFAULT_OLLAMA_HOST` | `http://localhost:11434` | Default Ollama server URL |
| `AI_DEFAULT_TIMEOUT` | `30` | Default request timeout (seconds) |

#### Legacy (Backward Compatible)

| Variable | Maps To |
|----------|---------|
| `OLLAMA_ENABLED` | `AI_ENABLED` |
| `OLLAMA_HOST` | `AI_DEFAULT_OLLAMA_HOST` (host part) |
| `OLLAMA_PORT` | `AI_DEFAULT_OLLAMA_HOST` (port part) |
| `OLLAMA_MODEL` | `AI_DEFAULT_MODEL` |

#### Per-Feature Overrides

Replace `{FEATURE}` with `ROASTING`, `NEWS`, `CVE`, or `MODERATION`:

| Variable | Default | Description |
|----------|---------|-------------|
| `AI_{FEATURE}_PROVIDER` | Global default | `ollama` or `gemini` |
| `AI_{FEATURE}_MODEL` | Global default | Model name for this feature |
| `AI_{FEATURE}_OLLAMA_HOST` | Global default | Ollama server URL for this feature |
| `AI_{FEATURE}_GEMINI_MODEL` | `gemini-2.0-flash` | Gemini model for fallback |
| `AI_{FEATURE}_GEMINI_FALLBACK` | `true` | Enable Gemini fallback for this feature |
| `AI_{FEATURE}_TEMPERATURE` | Model default | Override creativity (0.0-1.0) |
| `AI_{FEATURE}_MAX_TOKENS` | Model default | Override max response tokens |
| `AI_{FEATURE}_TIMEOUT` | `30` | Request timeout (seconds) |
| `AI_{FEATURE}_ENABLED` | `true` | Enable/disable this specific feature |

#### Gemini Fallback

| Variable | Default | Description |
|----------|---------|-------------|
| `GEMINI_API_KEY` | *(none)* | Google Gemini API key |
| `AI_GEMINI_MODEL` | `gemini-2.0-flash` | Default Gemini model |
| `AI_GEMINI_FALLBACK` | `true` | Global fallback toggle |

#### Thinking Models

| Variable | Default | Description |
|----------|---------|-------------|
| `AI_ENABLE_THINKING_MODE` | `false` | Force thinking mode globally (auto-detected for known models) |
| `AI_THINKING_TOKEN_MULTIPLIER` | `4.0` | Token budget multiplier for reasoning |

#### Queue & Rate Limiting

| Variable | Default | Description |
|----------|---------|-------------|
| `AI_MAX_CONCURRENT_REQUESTS` | `4` | Max simultaneous requests across all features |
| `AI_MIN_DELAY_BETWEEN_REQUESTS` | `1.0` | Minimum seconds between requests |

#### Retry & Reconnection

| Variable | Default | Description |
|----------|---------|-------------|
| `AI_MAX_RETRIES` | `3` | Retries for transient errors (503, 429) |
| `AI_RETRY_DELAY_BASE` | `2` | Base delay for exponential backoff (seconds) |
| `AI_ENABLE_AUTO_RECONNECT` | `true` | Auto-reconnect on Ollama connection loss |
| `AI_RECONNECT_INTERVAL` | `60` | Seconds between reconnect attempts |
| `AI_MAX_RECONNECT_ATTEMPTS` | `0` | Max reconnect attempts (0 = unlimited) |

#### Feature Toggle

| Variable | Default | Description |
|----------|---------|-------------|
| `ARCH_BANTER_LLM` | `false` | Enable AI-powered Arch roasts |

### Example Configurations

#### Minimal (Ollama only, single model)
```env
AI_ENABLED=true
AI_DEFAULT_MODEL=gemma3:4b
ARCH_BANTER_LLM=true
```

#### Gemini-Only (No Ollama)
```env
AI_ENABLED=true
AI_DEFAULT_PROVIDER=gemini
GEMINI_API_KEY=AIza...your-key...
AI_GEMINI_MODEL=gemini-2.0-flash
ARCH_BANTER_LLM=true
```

#### Multi-Server Lab
```env
AI_ENABLED=true
AI_DEFAULT_PROVIDER=ollama

# Roasting: Gemini (fast, creative, no local GPU needed)
AI_ROASTING_PROVIDER=gemini
GEMINI_API_KEY=AIza...your-key...

# News: Qwen3 on inference server
AI_NEWS_PROVIDER=ollama
AI_NEWS_MODEL=qwen3:14b
AI_NEWS_OLLAMA_HOST=http://192.168.1.100:11434

# CVE: Same inference server, same model
AI_CVE_PROVIDER=ollama
AI_CVE_MODEL=qwen3:14b
AI_CVE_OLLAMA_HOST=http://192.168.1.100:11434

# Moderation: Llama Guard on dedicated box
AI_MODERATION_PROVIDER=ollama
AI_MODERATION_MODEL=llama-guard3:8b
AI_MODERATION_OLLAMA_HOST=http://192.168.1.101:11434
AI_MODERATION_ENABLED=false  # Not wired up yet
```

---

## Multi-Server Setup (FrankenLLM)

For multi-GPU and multi-server setups, [FrankenLLM](https://github.com/ChiefGyk3D/FrankenLLM) automates the process of running multiple Ollama instances.

### What FrankenLLM Does

- Runs **one Ollama instance per GPU** as a separate systemd service
- Each GPU gets its own port (11434, 11435, 11436...) and model storage
- Models are **pre-loaded into VRAM** at boot via a warmup service
- Health monitoring with automatic driver recovery
- Supports local and remote installation via SSH

### Architecture with Penguin Overlord

```
┌──────────────────────────────────────┐
│          AI Server (FrankenLLM)       │
│                                       │
│  ollama-gpu0 (RTX 5060 Ti 16GB)      │
│    Port: 11434                        │
│    Model: gemma3:12b (roasting/news)  │
│                                       │
│  ollama-gpu1 (RTX 3050 8GB)          │
│    Port: 11435                        │
│    Model: gemma3:4b (CVE/general)     │
└───────────────┬──────────┬────────────┘
                │          │
        ┌───────┘          └───────┐
        ▼                          ▼
┌───────────────┐          ┌───────────────┐
│ Penguin       │          │ Other bots/   │
│ Overlord      │          │ services      │
│ (Discord bot) │          │ (Open WebUI)  │
└───────────────┘          └───────────────┘
```

### Setup Steps

1. **Set up FrankenLLM on your AI server:**
   ```bash
   git clone https://github.com/ChiefGyk3D/FrankenLLM.git
   cd FrankenLLM
   ./setup-frankenllm.sh   # Interactive wizard
   ```

2. **Configure Penguin Overlord to point at the server:**
   ```env
   AI_ROASTING_OLLAMA_HOST=http://ai-server:11434
   AI_ROASTING_MODEL=gemma3:12b
   AI_CVE_OLLAMA_HOST=http://ai-server:11435
   AI_CVE_MODEL=gemma3:4b
   ```

3. **Ensure network access:** Ollama defaults to `0.0.0.0` binding in FrankenLLM, so the bot just needs network access to the server's ports.

### Recommended FrankenLLM Combos for Penguin Overlord

| GPUs | GPU 0 Model | GPU 1 Model | Bot Config |
|------|-------------|-------------|------------|
| 16GB + 8GB | `gemma3:12b` | `gemma3:4b` | News/roasting → GPU 0, CVE → GPU 1 |
| 24GB + 16GB | `qwen3:14b` | `gemma3:12b` | Analysis → GPU 0, roasting → GPU 1 |
| 24GB + 8GB | `gemma3:27b` | `llama-guard3:8b` | All analysis → GPU 0, moderation → GPU 1 |
| 24GB + 16GB + 8GB | `qwen3:14b` | `gemma3:12b` | Analysis → GPU 0, roasting → GPU 1, moderation → GPU 2 |

---

## Secrets Management

The AI system integrates with Penguin Overlord's existing secrets pipeline. The `GEMINI_API_KEY` (and any future API keys) are resolved through:

### Priority Order

1. **Doppler** (if `DOPPLER_TOKEN` is set) — recommended for production
2. **AWS Secrets Manager** (if `SECRETS_AWS_ENABLED=true`)
3. **HashiCorp Vault** (if `SECRETS_VAULT_ENABLED=true`)
4. **Environment variable** (`.env` file or system env)

### Doppler Setup

If you're already using Doppler for `DISCORD_BOT_TOKEN`, just add the AI secrets to the same project:

```bash
# In your Doppler dashboard, add these secrets:
# Project: penguin-overlord, Config: prd

GEMINI_API_KEY=AIza...your-key...
AI_ENABLED=true
AI_DEFAULT_MODEL=gemma3:4b
```

Or via CLI:
```bash
doppler secrets set GEMINI_API_KEY "AIza...your-key..."
doppler secrets set AI_ENABLED "true"
doppler secrets set AI_DEFAULT_MODEL "gemma3:4b"
```

The bot reads these automatically — the AI config module calls `get_secret('AI', 'GEMINI_API_KEY')` which follows the same Doppler → AWS → Vault → env fallback chain used for `DISCORD_BOT_TOKEN`.

### .env Setup (Simple)

For local development or simple deployments:

```env
# In .env file
GEMINI_API_KEY=AIza...your-key...
```

### AWS Secrets Manager

Store under `penguin-overlord/ai`:
```json
{
  "GEMINI_API_KEY": "AIza...",
  "AI_ENABLED": "true"
}
```

### HashiCorp Vault

```bash
vault kv put secret/penguin-overlord/ai \
  GEMINI_API_KEY="AIza..." \
  AI_ENABLED="true"
```

> **Note:** Ollama connections don't require API keys — just network access. Only the Gemini fallback needs an API key.

---

## Current AI Features

### 1. Arch Roaster (`cogs/arch_banter.py`)

**Status:** ✅ Fully integrated

Generates contextual, witty Arch Linux roasts using LLM when someone mentions Arch, pacman, AUR, etc.

| Aspect | Details |
|--------|---------|
| Trigger | Arch Linux mentions in chat |
| AI Feature | `roasting` |
| Fallback | 130+ static pre-written jokes |
| Enable | `ARCH_BANTER_LLM=true` |
| Best models | `gemma3:4b`, `gemma3:12b`, Gemini |
| Temperature | 0.85 (creative) |
| Timeout | 15 seconds |

**Example:**
```
User: "Just spent 6 hours ricing my i3 setup on Arch"
Bot:  "@user 6 hours on rice? That's commitment to making your desktop look exactly
       like every other Arch user's r/unixporn submission 🍚"
```

### 2. News Analyzer (`ai/features/news_analyzer.py`)

**Status:** ✅ Module ready, cog integration pending

Summarizes articles, generates structured analysis, extracts key topics. Supports cybersecurity-specific analysis prompts.

| Aspect | Details |
|--------|---------|
| AI Feature | `news` |
| Capabilities | Summarize, analyze, batch summarize, extract topics |
| Best models | `qwen3:8b`, `qwen3:14b`, `qwen2.5:7b` |
| Temperature | 0.2-0.3 (factual) |
| Timeout | 30-45 seconds |

**Usage in code:**
```python
from ai import get_ai_manager

manager = get_ai_manager()

# One-line summary
summary = await manager.news.summarize(
    title="Critical Log4j Vulnerability Found in Apache Kafka",
    content="Researchers have discovered...",
    source="BleepingComputer"
)

# Structured analysis
analysis = await manager.news.analyze(
    title="EU AI Act Implementation Timeline Announced",
    content="The European Commission today...",
    category="legislation"
)

# Key topics
topics = await manager.news.extract_key_topics(title, content)
# → ['AI regulation', 'EU policy', 'compliance', 'machine learning']
```

### 3. CVE Analyzer (`ai/features/cve_analyzer.py`)

**Status:** ✅ Module ready, cog integration pending

Provides plain-English vulnerability assessments with severity ratings and actionable remediation.

| Aspect | Details |
|--------|---------|
| AI Feature | `cve` |
| Capabilities | Full analysis, summary, severity assessment |
| Best models | `qwen3:14b`, `llama3.1:8b` |
| Temperature | 0.1 (very low — factual/security-critical) |
| Timeout | 20-30 seconds |

**Usage in code:**
```python
# Full analysis with remediation steps
analysis = await manager.cve.analyze(
    cve_id="CVE-2024-12345",
    description="A use-after-free vulnerability in...",
    cvss_score=9.8,
    affected_products="Linux kernel 6.1-6.8"
)

# Quick severity assessment
severity = await manager.cve.assess_severity(
    description="Buffer overflow in OpenSSL...",
    cvss_score=7.5
)
# → {'level': 'HIGH', 'reason': 'Remote code execution in widely-deployed crypto library'}
```

### 4. Moderation Analyzer (`ai/features/moderation.py`)

**Status:** 🔧 Stub — interface defined, not yet wired to cogs

Foundation for AI-powered content moderation that understands context rather than relying on regex.

| Aspect | Details |
|--------|---------|
| AI Feature | `moderation` |
| Capabilities | Content classification, safety check, context-aware analysis |
| Best models | `llama-guard3:8b`, `llama-guard3:1b` |
| Temperature | 0.1 (deterministic) |
| Timeout | 15 seconds |

**Moderation categories:** safe, harassment, hate_speech, sexual_content, violence, self_harm, spam, misinformation

**Design philosophy:** Err on the side of permissiveness. Tech communities use informal language. Arch Linux jokes, friendly banter, and mild profanity are acceptable. The system flags genuinely harmful content while respecting community culture.

---

## Recommended Future AI Features

Based on analysis of all 26 cogs in Penguin Overlord, these are the highest-value AI enhancements ranked by impact:

### Tier 1: High Impact, AI Modules Already Exist

#### 1. KEV/CVE AI Triage
**Cogs:** `kev.py`, `cve.py` | **Module:** `CVEAnalyzer` (ready)

Wire the existing `CVEAnalyzer` into CVE/KEV post embeds to add:
- Plain-English impact assessment ("Who's affected and how")
- AI-assessed urgency vs. raw CVSS score
- Specific remediation steps ("Patch OpenSSL to 3.2.1+")
- Affected stack identification ("Impacts: Nginx, Apache, Node.js")

This is the **highest security value** enhancement. CISA KEVs are actively exploited vulns — AI triage helps teams prioritize correctly.

#### 2. News AI Digest
**Cogs:** All 6 news cogs (cybersecurity, tech, gaming, general, apple/google, vendor alerts) | **Module:** `NewsAnalyzer` (ready)

- Add TL;DR summaries to auto-posted articles
- Cross-category `/news digest` command: "Today's top 5 stories"
- Cybersecurity threat briefings from aggregated sources
- Story deduplication across outlets (same event, multiple sources)

#### 3. Legislation Plain-English Summaries
**Cogs:** `us_legislation.py`, `eu_legislation.py`, `uk_legislation.py` | **Module:** `NewsAnalyzer` (can be reused)

Bills are posted with opaque official titles. AI adds:
- "What this means for tech" one-liner
- Privacy/security relevance flagging
- Impact tags (encryption, Section 230, GDPR, AI regulation)

### Tier 2: High Impact, New Modules Needed

#### 4. AI Man Page Explainer
**Cog:** `manpage.py`

New command: `/man explain "find . -name '*.log' -mtime +30 -delete"`
- AI explains arbitrary commands in plain English
- Warns about dangerous flags (`rm -rf`, `dd`, `chmod 777`)
- Suggests safer alternatives
- Command safety checker for user-pasted commands

#### 5. HAM Radio AI Propagation Advisor
**Cog:** `radiohead.py`

Natural language questions about radio conditions using live NOAA solar data:
- "Can I reach Japan from the east coast on 20m tonight?"
- AI combines SFI, K-index, and band condition data into conversational answers
- Daily AI propagation forecast

#### 6. PatchGremlin + CVE Integration
**Cog:** `patchgremlin.py`

AI-generated topical patch reminders referencing actual recent CVEs:
> "PATCH GREMLIN SAYS: That libwebp vuln from last week? It's in your Chrome, your Electron apps, and probably your toaster. PATCH NOW. 🔧"

#### 7. Intelligent Fortune Cookies
**Cog:** `fortune.py`

AI-generated context-aware cyber fortunes referencing recent news:
> "Today's fortune: Your Log4j patch from 2021 is doing great. The 3 others you missed? Not so much. 🔮"

### Tier 3: Medium Impact, Nice-to-Have

#### 8. XKCD AI Explainer
**Cogs:** `xkcd.py`, `comics.py`

`/xkcd explain 2900` — AI-generated breakdown of XKCD jokes without relying on the explainxkcd API (which lags behind new comics).

#### 9. Natural Language Help
**Cog:** `help_categorized.py`

`/help ask "how do I track CVEs?"` — AI routes users to the right command based on what they want to do, instead of browsing categories.

#### 10. SIGINT Signal Identifier
**Cog:** `sigint.py`

`/sigint identify "buzzing sound on 4.625 MHz"` → AI identifies signals from user descriptions (numbers stations, military comms, etc.).

#### 11. Event Conference Pitch Generator
**Cog:** `eventpinger.py`

AI-generated "why you should attend" pitches for cybersecurity conferences, CFP deadline reminders.

#### 12. Vendor Alert Impact Assessment
**Cog:** `vendor_alerts.py`

AI assesses business impact of vendor incidents: "Zscaler ZIA tunnel disruption affects all internet-bound traffic for users behind ZIA — HIGH impact."

### Implementation Priority

For maximum ROI, the recommended implementation order is:

1. **KEV/CVE AI Triage** — Highest security value, module exists
2. **News TL;DR Summaries** — Most visible improvement, module exists
3. **Legislation Summaries** — Reuses news module, high value
4. **Moderation** — Wire up the stub when ready for content moderation
5. **Man Page Explainer** — New module, high community value
6. **PatchGremlin + CVE** — Fun, topical, relatively easy

---

## Troubleshooting

### Ollama Not Connecting

```bash
# Check Ollama is running
curl http://localhost:11434/api/tags

# Check model is available
ollama list

# Check from the bot's perspective (if remote)
curl http://your-ollama-server:11434/api/tags
```

**Common fixes:**
- Start Ollama: `systemctl start ollama` or `ollama serve`
- Check firewall: Ollama must be accessible on its port from the bot
- For remote servers: Ollama must bind to `0.0.0.0`, not just `127.0.0.1`
  ```bash
  # Set in /etc/systemd/system/ollama.service or via FrankenLLM
  Environment="OLLAMA_HOST=0.0.0.0:11434"
  ```

### AI Responses Are Slow

| Symptom | Cause | Fix |
|---------|-------|-----|
| 10+ seconds per response | Large model on small GPU | Use a smaller model |
| Intermittent slowness | Multiple features competing | Reduce `AI_MAX_CONCURRENT_REQUESTS` |
| First request slow, rest fast | Model loading from disk | Use FrankenLLM warmup service or `OLLAMA_KEEP_ALIVE=-1` |
| Always slow | CPU-only inference | Add a GPU or use Gemini as primary |

### Empty or Bad Responses

- **Thinking model returns empty:** The thinking token budget may be too low. Increase `AI_THINKING_TOKEN_MULTIPLIER` (default: 4.0).
- **Responses are cut off:** Increase `AI_{FEATURE}_MAX_TOKENS`.
- **Model hallucinating:** Lower the temperature. CVE/news features use 0.1-0.3 for factual accuracy.

### Gemini Fallback Not Working

```bash
# Test your API key
curl "https://generativelanguage.googleapis.com/v1beta/models?key=YOUR_KEY"
```

- Verify `GEMINI_API_KEY` is set (check Doppler or `.env`)
- Verify `google-genai` is installed: `pip install google-genai`
- Free tier has rate limits (15 RPM for Flash). If hitting limits, increase `AI_MIN_DELAY_BETWEEN_REQUESTS`.

### Checking AI System Status

In Discord (if admin cog is extended):
```
!ai_status  # (future command)
```

In Python:
```python
from ai import get_ai_manager
manager = get_ai_manager()
print(manager.provider_status)  # Shows all providers and connection state
print(manager.queue_stats)       # Shows request queue metrics
print(manager.is_feature_enabled('roasting'))  # Per-feature check
```

### Disabling AI Entirely

```env
AI_ENABLED=false
```

Or remove the `ollama` and `google-genai` packages — the bot will start normally with all AI features gracefully degraded.
