# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
Ollama LLM Client - DEPRECATED backward-compatibility wrapper.

This module is retained for backward compatibility only.
New code should use the ai.manager.AIManager instead:

    from ai import get_ai_manager
    manager = get_ai_manager()
    result = await manager.roaster.roast(message, username)
    result = await manager.news.summarize(title, content)
    result = await manager.cve.analyze(cve_id, description)

The old OllamaClient class and get_ollama_client() function below
delegate to the new AI system when available, and fall back to
direct Ollama calls for backward compatibility.
"""

import logging
import os
import warnings
from typing import Optional
from functools import lru_cache

logger = logging.getLogger(__name__)

# Try to use the new AI system
_USE_NEW_AI = False
try:
    from ai import get_ai_manager
    _USE_NEW_AI = True
except ImportError:
    try:
        from penguin_overlord.ai import get_ai_manager
        _USE_NEW_AI = True
    except ImportError:
        pass


class OllamaClient:
    """
    DEPRECATED: Backward-compatible wrapper around the new AI system.

    Use ai.manager.AIManager instead for new code.
    """

    def __init__(self, model: str = "gemma3:4b", enabled: bool = True,
                 host: str = None, port: str = None):
        warnings.warn(
            "OllamaClient is deprecated. Use 'from ai import get_ai_manager' instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        self.model = model
        self.enabled = enabled
        self._ai_manager = None

        if _USE_NEW_AI and enabled:
            try:
                self._ai_manager = get_ai_manager()
                self.enabled = self._ai_manager.enabled
            except Exception as e:
                logger.warning(f"Failed to initialize AI manager in compat wrapper: {e}")
                self.enabled = False

    async def generate(self, prompt: str, system_prompt: Optional[str] = None,
                       temperature: Optional[float] = None,
                       max_tokens: Optional[int] = None,
                       timeout: int = 10) -> Optional[str]:
        """Generate text - delegates to new AI system."""
        if self._ai_manager:
            kwargs = {}
            if temperature is not None:
                kwargs['temperature'] = temperature
            if max_tokens is not None:
                kwargs['max_tokens'] = max_tokens
            return await self._ai_manager.generate(
                feature='roasting',
                prompt=prompt,
                system_prompt=system_prompt,
                timeout=timeout,
                **kwargs,
            )
        return None

    async def generate_arch_roast(self, message_content: str, username: str,
                                  context: Optional[str] = None) -> Optional[str]:
        """Generate arch roast - delegates to new AI system."""
        if self._ai_manager and self._ai_manager.roaster:
            return await self._ai_manager.roaster.roast(
                message_content=message_content,
                username=username,
                context=context,
            )
        return None

    def is_enabled(self) -> bool:
        """Check if AI features are enabled."""
        if self._ai_manager:
            return self._ai_manager.is_feature_enabled('roasting')
        return False


@lru_cache(maxsize=1)
def get_ollama_client() -> OllamaClient:
    """DEPRECATED: Get or create global Ollama client. Use get_ai_manager() instead."""
    model = os.getenv('OLLAMA_MODEL', os.getenv('AI_DEFAULT_MODEL', 'gemma3:4b'))
    enabled = os.getenv('AI_ENABLED', os.getenv('OLLAMA_ENABLED', 'true')).lower() in ('true', '1', 'yes')
    host = os.getenv('OLLAMA_HOST', 'http://localhost')
    port = os.getenv('OLLAMA_PORT', '11434')
    return OllamaClient(model=model, enabled=enabled, host=host, port=port)
