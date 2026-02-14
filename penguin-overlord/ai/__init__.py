# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
AI Module - Multi-provider LLM integration for Penguin Overlord.

Supports multiple Ollama servers, per-feature model routing, Gemini fallback,
thinking model support (Qwen3), async request queuing, and auto-reconnect.

Architecture:
    AIManager -> Routes requests to the correct provider/model per feature
        -> OllamaProvider -> Connects to one or more Ollama servers
        -> GeminiProvider -> Google Gemini API fallback
        -> RequestQueue -> Async queue to prevent request overlap

Features:
    - ArchRoaster: Contextual Arch Linux roasts
    - NewsAnalyzer: Article summarization and analysis
    - CVEAnalyzer: Security vulnerability analysis
    - ModerationAnalyzer: Content moderation (stub for future)
"""

from .manager import AIManager, get_ai_manager

__all__ = ['AIManager', 'get_ai_manager']
