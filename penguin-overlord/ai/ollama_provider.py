# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
Ollama Provider - Async client for Ollama LLM servers.

Handles connection management, thinking model support (Qwen3/DeepSeek-R1),
automatic reconnection, and retry logic with exponential backoff.

Supports multiple server instances for FrankenLLM-style multi-server setups
where different Ollama servers handle different workloads.
"""

import asyncio
import logging
import re
import time
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# Guard ollama import
try:
    import ollama
    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False
    logger.warning("ollama package not installed - Ollama features will be disabled")


class OllamaProvider:
    """
    Async Ollama LLM provider with reconnection and thinking model support.

    Each instance connects to a single Ollama server. The AIManager may
    create multiple instances for multi-server routing.
    """

    def __init__(
        self,
        host: str = 'http://localhost:11434',
        enable_auto_reconnect: bool = True,
        reconnect_interval: int = 60,
        max_reconnect_attempts: int = 0,
        max_retries: int = 3,
        retry_delay_base: int = 2,
    ):
        """
        Initialize Ollama provider for a specific server.

        Args:
            host: Full Ollama server URL (e.g., http://gpu-server:11434)
            enable_auto_reconnect: Attempt reconnection on connection loss
            reconnect_interval: Seconds between reconnect attempts
            max_reconnect_attempts: Max reconnects (0 = unlimited)
            max_retries: Max retries for transient errors per request
            retry_delay_base: Base delay for exponential backoff
        """
        self.host = host
        self.client: Optional[Any] = None
        self.connected = False
        self.available_models: list = []

        # Reconnection state
        self.enable_auto_reconnect = enable_auto_reconnect
        self.reconnect_interval = reconnect_interval
        self.max_reconnect_attempts = max_reconnect_attempts
        self._last_reconnect_attempt: float = 0
        self._reconnect_attempt_count: int = 0
        self._ever_connected: bool = False

        # Retry config
        self.max_retries = max_retries
        self.retry_delay_base = retry_delay_base

    def connect(self) -> bool:
        """
        Establish connection to the Ollama server and verify it's running.

        Returns:
            True if connection successful
        """
        if not OLLAMA_AVAILABLE:
            logger.error("ollama package not installed. Run: pip install ollama")
            return False

        try:
            self.client = ollama.Client(host=self.host)
            models_response = self.client.list()

            # Handle both dict and attribute-style responses
            self.available_models = []
            models_list = None
            if hasattr(models_response, 'models'):
                models_list = models_response.models
            elif isinstance(models_response, dict) and 'models' in models_response:
                models_list = models_response['models']

            if models_list:
                for m in models_list:
                    name = None
                    if isinstance(m, dict):
                        name = m.get('name') or m.get('model')
                    elif hasattr(m, 'model'):
                        name = m.model
                    elif hasattr(m, 'name'):
                        name = m.name
                    if name:
                        self.available_models.append(name)

            self.connected = True
            self._ever_connected = True
            self._reconnect_attempt_count = 0
            logger.info(
                f"✓ Connected to Ollama at {self.host} "
                f"({len(self.available_models)} models available)"
            )
            return True

        except Exception as e:
            logger.warning(f"✗ Failed to connect to Ollama at {self.host}: {e}")
            self.connected = False
            self.client = None
            return False

    def attempt_reconnect(self) -> bool:
        """
        Attempt to reconnect to the Ollama server.

        Respects cooldown interval and max attempts. Returns True on success.
        """
        if not self.enable_auto_reconnect:
            return False

        if (self.max_reconnect_attempts > 0 and
                self._reconnect_attempt_count >= self.max_reconnect_attempts):
            logger.debug(f"Max reconnect attempts ({self.max_reconnect_attempts}) reached for {self.host}")
            return False

        now = time.time()
        if now - self._last_reconnect_attempt < self.reconnect_interval:
            return False

        self._last_reconnect_attempt = now
        self._reconnect_attempt_count += 1
        logger.info(
            f"Attempting Ollama reconnect to {self.host} "
            f"(attempt {self._reconnect_attempt_count})"
        )
        return self.connect()

    async def generate(
        self,
        model: str,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 150,
        top_p: float = 0.9,
        top_k: int = 40,
        context_window: int = 8192,
        enable_thinking: bool = False,
        thinking_token_multiplier: float = 4.0,
        timeout: int = 30,
    ) -> Optional[str]:
        """
        Generate text using Ollama with retry logic.

        Handles thinking models (Qwen3, DeepSeek-R1) which put their
        reasoning in a separate 'thinking' field and may return empty 'content'.

        Args:
            model: Model name to use
            prompt: User prompt
            system_prompt: Optional system context
            temperature: Creativity level (0.0-1.0)
            max_tokens: Maximum response tokens
            top_p: Nucleus sampling threshold
            top_k: Top-k sampling
            context_window: Context window size
            enable_thinking: Handle thinking model output format
            thinking_token_multiplier: Token budget multiplier for thinking models
            timeout: Request timeout in seconds

        Returns:
            Generated text or None on failure
        """
        if not self.connected:
            if not self.attempt_reconnect():
                return None

        # Thinking models need more tokens to include reasoning
        effective_max_tokens = max_tokens
        if enable_thinking:
            effective_max_tokens = int(max_tokens * thinking_token_multiplier)

        options = {
            'temperature': temperature,
            'num_predict': effective_max_tokens,
            'top_p': top_p,
            'top_k': top_k,
            'num_ctx': context_window,
        }

        messages = []
        if system_prompt:
            messages.append({'role': 'system', 'content': system_prompt})
        messages.append({'role': 'user', 'content': prompt})

        for attempt in range(self.max_retries + 1):
            try:
                loop = asyncio.get_running_loop()
                client = self.client

                response = await asyncio.wait_for(
                    loop.run_in_executor(
                        None,
                        lambda: client.chat(
                            model=model,
                            messages=messages,
                            options=options,
                        )
                    ),
                    timeout=timeout,
                )

                # Extract content, handling thinking models
                content = self._extract_response(response, enable_thinking)
                if content:
                    return content

                logger.warning(f"Empty response from {model} at {self.host}")
                return None

            except asyncio.TimeoutError:
                logger.warning(
                    f"Ollama timeout ({timeout}s) for {model} at {self.host} "
                    f"(attempt {attempt + 1}/{self.max_retries + 1})"
                )
                if attempt >= self.max_retries:
                    return None

            except Exception as e:
                error_str = str(e).lower()
                is_connection_error = any(
                    t in error_str for t in ['connection refused', 'unreachable', 'no route']
                )
                is_retryable = any(
                    t in error_str for t in ['503', '429', 'overloaded', 'timeout', 'busy']
                )

                if is_connection_error:
                    logger.error(f"Connection lost to Ollama at {self.host}: {e}")
                    self.connected = False
                    return None

                if not is_retryable or attempt >= self.max_retries:
                    logger.error(
                        f"Ollama generation error ({model}@{self.host}): {e}"
                    )
                    return None

                delay = self.retry_delay_base ** attempt
                logger.warning(
                    f"Retryable error from {model}@{self.host}: {e} "
                    f"(retry {attempt + 1} in {delay}s)"
                )
                await asyncio.sleep(delay)

        return None

    def _extract_response(self, response: Any, enable_thinking: bool) -> Optional[str]:
        """
        Extract text content from Ollama response.

        Thinking models (Qwen3, DeepSeek-R1) structure:
            {"message": {"content": "final answer", "thinking": "chain of thought"}}

        Sometimes thinking models return empty content with all reasoning
        in the thinking field. In that case, we attempt to extract a usable
        answer from the thinking text.
        """
        message = None
        if isinstance(response, dict):
            message = response.get('message', {})
        elif hasattr(response, 'message'):
            msg = response.message
            message = msg if isinstance(msg, dict) else {}
            if hasattr(msg, 'content'):
                message = {'content': msg.content}
                if hasattr(msg, 'thinking'):
                    message['thinking'] = msg.thinking

        if not message:
            return None

        content = ''
        if isinstance(message, dict):
            content = message.get('content', '').strip()
        elif hasattr(message, 'content'):
            content = (message.content or '').strip()

        # If we got content, return it directly
        if content:
            return content

        # For thinking models with empty content, try to extract from thinking
        if enable_thinking:
            thinking = ''
            if isinstance(message, dict):
                thinking = message.get('thinking', '')
            elif hasattr(message, 'thinking'):
                thinking = message.thinking or ''

            if thinking:
                extracted = self._extract_from_thinking(thinking)
                if extracted:
                    return extracted

        return None

    @staticmethod
    def _extract_from_thinking(thinking: str) -> Optional[str]:
        """
        Extract a usable response from thinking model's reasoning text.

        Uses cascading strategies:
        1. Look for explicit final answer markers
        2. Look for quoted output lines
        3. Look for the last substantial paragraph
        4. Give up if nothing usable found
        """
        if not thinking:
            return None

        # Strategy 1: Explicit markers like "Final answer:", "Here's the response:", etc.
        marker_patterns = [
            r'(?:final\s+(?:answer|response|output|post|message)):\s*["\']?(.*?)(?:["\']?\s*$)',
            r'(?:here\'?s?\s+(?:the|my)\s+(?:response|answer|post|message)):\s*["\']?(.*?)(?:["\']?\s*$)',
            r'(?:output|result):\s*["\']?(.*?)(?:["\']?\s*$)',
        ]
        for pattern in marker_patterns:
            match = re.search(pattern, thinking, re.IGNORECASE | re.DOTALL)
            if match:
                result = match.group(1).strip().strip('"\'')
                if len(result) >= 10:
                    return result

        # Strategy 2: Quoted lines (lines starting with >)
        quoted = [
            line.lstrip('>').strip()
            for line in thinking.split('\n')
            if line.strip().startswith('>')
        ]
        if quoted:
            result = ' '.join(quoted).strip()
            if 10 <= len(result) <= 500:
                return result

        # Strategy 3: Last substantial paragraph
        paragraphs = [p.strip() for p in thinking.split('\n\n') if p.strip()]
        for para in reversed(paragraphs):
            # Skip meta-commentary about the thinking process
            if any(skip in para.lower() for skip in [
                'let me', 'i should', 'i need to', 'thinking about',
                'considering', 'the user', 'i think', 'my approach'
            ]):
                continue
            if 20 <= len(para) <= 500:
                return para

        return None

    def is_model_available(self, model: str) -> bool:
        """Check if a specific model is available on this server."""
        if not self.available_models:
            return True  # Assume available if we can't check (auto-pull)
        return any(model in m for m in self.available_models)

    @property
    def is_available(self) -> bool:
        """Check if this provider is connected and ready."""
        return OLLAMA_AVAILABLE and self.connected
