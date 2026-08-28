# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""AI subsystem: local-first LLM features backed by Ollama, with optional
Gemini fallback for non-sensitive features.

Everything is opt-in: AI_ENABLED defaults to false, and each feature is
additionally gated behind its own AI_<FEATURE>_ENABLED flag. When disabled
or unreachable, every consumer falls back to its pre-AI behavior.

Entry point: `from ai.manager import get_ai_manager`.
"""
