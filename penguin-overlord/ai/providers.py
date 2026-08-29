# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""LLM providers.

OllamaProvider is fully async (ollama.AsyncClient) — no blocking connect
or generate calls ever touch the event loop, and every network operation
carries a timeout. GeminiProvider is the optional remote fallback, used
only for features that explicitly allow it (never moderation).
"""

import asyncio
import logging
import time

logger = logging.getLogger(__name__)

try:
    import ollama
    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False

try:
    from google import genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False


class OllamaProvider:
    """One async Ollama client per host, with rate-limited reconnects."""

    CONNECT_TIMEOUT = 5.0

    def __init__(self, host: str, reconnect_interval: float = 60.0):
        self.host = host
        self.reconnect_interval = reconnect_interval
        self.connected = False
        self._client = None
        self._last_connect_attempt = 0.0
        self._connect_lock = asyncio.Lock()

    @property
    def available(self) -> bool:
        return OLLAMA_AVAILABLE

    async def ensure_connected(self) -> bool:
        """Verify the host is reachable, at most once per reconnect_interval.

        Fully async with a hard timeout — the old implementation ran a
        synchronous, timeout-less client.list() on the event loop and froze
        the whole bot when the host blackholed packets.
        """
        if not OLLAMA_AVAILABLE:
            return False
        if self.connected:
            return True

        async with self._connect_lock:
            if self.connected:
                return True
            now = time.monotonic()
            if now - self._last_connect_attempt < self.reconnect_interval:
                return False
            self._last_connect_attempt = now

            try:
                self._client = ollama.AsyncClient(host=self.host)
                await asyncio.wait_for(self._client.list(), timeout=self.CONNECT_TIMEOUT)
                self.connected = True
                logger.info(f"✓ Ollama connected: {self.host}")
                return True
            except Exception as e:
                logger.warning(f"Ollama unreachable at {self.host}: {type(e).__name__}")
                self.connected = False
                return False

    async def generate(self, model: str, prompt: str, system_prompt: str = None,
                       temperature: float = 0.7, max_tokens: int = 256,
                       timeout: float = 30.0):
        """Generate a completion. Returns the text or None."""
        if not await self.ensure_connected():
            return None

        messages = []
        if system_prompt:
            messages.append({'role': 'system', 'content': system_prompt})
        messages.append({'role': 'user', 'content': prompt})

        try:
            response = await asyncio.wait_for(
                self._client.chat(
                    model=model,
                    messages=messages,
                    # Thinking models (gemma4, qwen3, ...) otherwise burn the
                    # whole num_predict budget on reasoning and return empty
                    # content. Every feature here wants a direct answer;
                    # non-thinking models ignore the flag (verified on
                    # Ollama 0.33). The thinking-field fallback below stays
                    # for servers that don't honor it.
                    think=False,
                    options={
                        'temperature': temperature,
                        'num_predict': max_tokens,
                    },
                ),
                timeout=timeout,
            )
            message = response.get('message', {}) if isinstance(response, dict) else response.message
            content = message.get('content') if isinstance(message, dict) else message.content
            # Qwen3-style thinking models can put text in a separate field
            if not content:
                thinking = message.get('thinking') if isinstance(message, dict) else getattr(message, 'thinking', None)
                content = thinking or ''
            return content.strip() or None
        except asyncio.TimeoutError:
            logger.warning(f"Ollama generate timed out after {timeout}s ({self.host}, {model})")
            return None
        except Exception as e:
            logger.error(f"Ollama generate failed ({self.host}, {model}): {type(e).__name__}: {e}")
            # Connection-level failures trigger a reconnect on the next call
            self.connected = False
            return None


class GeminiProvider:
    """Optional Google Gemini fallback (async API)."""

    def __init__(self, api_key: str, model: str = 'gemini-2.0-flash'):
        self.model = model
        self._client = None
        if GEMINI_AVAILABLE and api_key:
            try:
                self._client = genai.Client(api_key=api_key)
            except Exception as e:
                logger.error(f"Gemini client init failed: {type(e).__name__}")

    @property
    def available(self) -> bool:
        return self._client is not None

    async def generate(self, model: str = None, prompt: str = '', system_prompt: str = None,
                       temperature: float = 0.7, max_tokens: int = 256,
                       timeout: float = 30.0):
        if not self.available:
            return None
        try:
            contents = prompt if not system_prompt else f"{system_prompt}\n\n---\n\n{prompt}"
            response = await asyncio.wait_for(
                self._client.aio.models.generate_content(
                    model=model or self.model,
                    contents=contents,
                    config={
                        'temperature': temperature,
                        'max_output_tokens': max_tokens,
                    },
                ),
                timeout=timeout,
            )
            text = getattr(response, 'text', None)
            return text.strip() if text else None
        except asyncio.TimeoutError:
            logger.warning(f"Gemini generate timed out after {timeout}s")
            return None
        except Exception as e:
            logger.error(f"Gemini generate failed: {type(e).__name__}")
            return None
