# Ollama LLM Integration (Legacy)

> **This document is superseded.** See **[AI_LLM_INTEGRATION.md](AI_LLM_INTEGRATION.md)** for the comprehensive AI & LLM guide covering multi-server setup, hardware recommendations, model selection, Doppler/secrets integration, and all AI-powered features.

## Quick Migration

The original `OLLAMA_*` environment variables still work for backward compatibility, but the new `AI_*` system is recommended:

| Old Variable | New Variable |
|-------------|-------------|
| `OLLAMA_ENABLED` | `AI_ENABLED` |
| `OLLAMA_HOST` + `OLLAMA_PORT` | `AI_DEFAULT_OLLAMA_HOST` (full URL) |
| `OLLAMA_MODEL` | `AI_DEFAULT_MODEL` |

The new system adds per-feature model routing, multi-server support, Gemini fallback, thinking model support, and request queuing. See the [full guide](AI_LLM_INTEGRATION.md) for details.
