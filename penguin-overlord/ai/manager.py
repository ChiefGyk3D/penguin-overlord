# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""AIManager — the single entry point for every AI feature.

Routes each feature to its configured Ollama host/model, applies the
bounded queue and output guardrails, retries transient failures, and
optionally falls back to Gemini for features that allow it (moderation
never does).

Usage:
    manager = await get_ai_manager()
    text = await manager.generate('roasting', prompt, system_prompt=...)

Everything degrades to None: callers must treat None as "use the non-AI
path", so a dead Ollama box is invisible to Discord users.
"""

import asyncio
import logging

from ai import config as ai_config
from ai.guardrails import Guardrails
from ai.providers import GeminiProvider, OllamaProvider
from ai.queue import BoundedRequestQueue

logger = logging.getLogger(__name__)


class AIManager:
    def __init__(self):
        runtime = ai_config.get_runtime_config()
        self._runtime = runtime
        self._ollama_providers = {}  # host -> OllamaProvider
        self._gemini = GeminiProvider(ai_config.gemini_api_key(), runtime.gemini_model)
        self._queue = BoundedRequestQueue(
            max_concurrent=runtime.max_concurrent,
            max_pending=runtime.max_pending,
            min_delay=runtime.min_delay,
        )
        self._guardrails = Guardrails()
        self._provider_lock = asyncio.Lock()

    # -- provider plumbing --------------------------------------------------

    async def _provider_for(self, host: str) -> OllamaProvider:
        async with self._provider_lock:
            provider = self._ollama_providers.get(host)
            if provider is None:
                provider = OllamaProvider(host, self._runtime.reconnect_interval)
                self._ollama_providers[host] = provider
            return provider

    @property
    def queue(self) -> BoundedRequestQueue:
        return self._queue

    @property
    def guardrails(self) -> Guardrails:
        return self._guardrails

    def status(self) -> dict:
        return {
            'enabled': ai_config.ai_enabled(),
            'gemini_available': self._gemini.available,
            'queue_pending': self._queue.pending,
            'queue_rejected': self._queue.rejected_count,
            'ollama_hosts': {
                host: provider.connected
                for host, provider in self._ollama_providers.items()
            },
        }

    # -- generation ---------------------------------------------------------

    async def generate(self, feature: str, prompt: str, system_prompt: str = None,
                       temperature: float = None, max_tokens: int = None,
                       timeout: float = None, raw: bool = False):
        """Generate text for *feature*. Returns cleaned text or None.

        raw=True skips output cleanup/dedup (used by structured analyzers
        that parse the response themselves) — the deny-list still applies
        to anything a caller might post.
        """
        cfg = ai_config.get_feature_config(feature)
        if not cfg.enabled:
            return None

        temperature = cfg.temperature if temperature is None else temperature
        max_tokens = cfg.max_tokens if max_tokens is None else max_tokens
        timeout = cfg.timeout if timeout is None else timeout

        result = await self._queue.submit(
            self._generate_with_fallback, cfg, prompt, system_prompt,
            temperature, max_tokens, timeout,
        )
        if result is None:
            return None

        if raw:
            return result

        ok, cleaned, issues = self._guardrails.check_output(result)
        if not ok:
            logger.info(f"AI output rejected for {feature}: {issues}")
            return None
        return cleaned

    async def _generate_with_fallback(self, cfg, prompt, system_prompt,
                                      temperature, max_tokens, timeout):
        provider = await self._provider_for(cfg.host)

        for attempt in range(self._runtime.max_retries + 1):
            result = await provider.generate(
                model=cfg.model, prompt=prompt, system_prompt=system_prompt,
                temperature=temperature, max_tokens=max_tokens, timeout=timeout,
            )
            if result:
                return result
            if not provider.connected:
                break  # host is down; retrying won't help within this call
            if attempt < self._runtime.max_retries:
                await asyncio.sleep(self._runtime.retry_delay_base * (attempt + 1))

        if cfg.gemini_fallback and self._gemini.available:
            logger.warning(
                f"Falling back to Gemini for feature '{cfg.feature}' "
                f"(Ollama at {cfg.host} unavailable) — content leaves the local network"
            )
            return await self._gemini.generate(
                prompt=prompt, system_prompt=system_prompt,
                temperature=temperature, max_tokens=max_tokens, timeout=timeout,
            )
        return None


_manager = None
_manager_lock = asyncio.Lock()


async def get_ai_manager() -> AIManager:
    """Process-wide AIManager singleton (lock-guarded)."""
    global _manager
    if _manager is None:
        async with _manager_lock:
            if _manager is None:
                _manager = AIManager()
    return _manager


def reset_ai_manager():
    """Testing hook."""
    global _manager
    _manager = None
