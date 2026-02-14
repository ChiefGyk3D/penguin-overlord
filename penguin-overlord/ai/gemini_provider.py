# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
Gemini Provider - Google Gemini API fallback for when Ollama is unavailable.

Used as a per-feature fallback when the assigned Ollama server is down
or unreachable. Each feature can optionally specify a Gemini model to
fall back to (default: gemini-2.0-flash).
"""

import asyncio
import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)

# Guard google-genai import
try:
    import google.genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    logger.info("google-genai not installed - Gemini fallback disabled")


class GeminiProvider:
    """
    Google Gemini API provider for fallback LLM generation.

    Uses the google-genai SDK (not the older google-generativeai).
    Shared across all features; the model is specified per-call.
    """

    def __init__(self, api_key: str = '', max_retries: int = 3, retry_delay_base: int = 2):
        """
        Initialize Gemini provider.

        Args:
            api_key: Google Gemini API key
            max_retries: Max retries for transient errors
            retry_delay_base: Base delay for exponential backoff
        """
        self.api_key = api_key
        self.client = None
        self.connected = False
        self.max_retries = max_retries
        self.retry_delay_base = retry_delay_base

        if api_key and GEMINI_AVAILABLE:
            self._authenticate()

    def _authenticate(self) -> bool:
        """Authenticate with Google Gemini API."""
        if not GEMINI_AVAILABLE:
            logger.error("google-genai not installed. Run: pip install google-genai")
            return False

        if not self.api_key:
            logger.warning("No Gemini API key provided - Gemini fallback disabled")
            return False

        try:
            self.client = google.genai.Client(api_key=self.api_key)
            self.connected = True
            logger.info("✓ Gemini API authenticated successfully")
            return True
        except Exception as e:
            logger.error(f"✗ Gemini authentication failed: {e}")
            self.connected = False
            return False

    async def generate(
        self,
        model: str,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 150,
        top_p: float = 0.9,
        timeout: int = 30,
    ) -> Optional[str]:
        """
        Generate text using Google Gemini.

        Args:
            model: Gemini model name (e.g., 'gemini-2.0-flash')
            prompt: User prompt
            system_prompt: Optional system context
            temperature: Creativity level
            max_tokens: Maximum response tokens
            top_p: Nucleus sampling threshold
            timeout: Request timeout in seconds

        Returns:
            Generated text or None on failure
        """
        if not self.connected or not self.client:
            if self.api_key and GEMINI_AVAILABLE:
                self._authenticate()
            if not self.connected:
                return None

        # Build the full prompt (Gemini uses a single content string with system instruction)
        full_prompt = prompt
        if system_prompt:
            full_prompt = f"{system_prompt}\n\n{prompt}"

        config = {
            'temperature': temperature,
            'max_output_tokens': max_tokens,
            'top_p': top_p,
        }

        for attempt in range(self.max_retries + 1):
            try:
                loop = asyncio.get_running_loop()
                client = self.client

                response = await asyncio.wait_for(
                    loop.run_in_executor(
                        None,
                        lambda: client.models.generate_content(
                            model=model,
                            contents=full_prompt,
                            config=config,
                        )
                    ),
                    timeout=timeout,
                )

                # Extract text from Gemini response
                if hasattr(response, 'text') and response.text:
                    return response.text.strip()

                # Try candidate extraction
                if hasattr(response, 'candidates') and response.candidates:
                    candidate = response.candidates[0]
                    if hasattr(candidate, 'content') and candidate.content:
                        parts = candidate.content.parts
                        if parts:
                            return parts[0].text.strip()

                logger.warning(f"Empty response from Gemini ({model})")
                return None

            except asyncio.TimeoutError:
                logger.warning(
                    f"Gemini timeout ({timeout}s) for {model} "
                    f"(attempt {attempt + 1}/{self.max_retries + 1})"
                )
                if attempt >= self.max_retries:
                    return None

            except Exception as e:
                error_str = str(e).lower()
                is_retryable = any(
                    t in error_str for t in ['503', '429', 'overloaded', 'quota', 'timeout', 'rate']
                )

                if not is_retryable or attempt >= self.max_retries:
                    logger.error(f"Gemini generation error ({model}): {e}")
                    return None

                delay = self.retry_delay_base ** attempt
                logger.warning(
                    f"Retryable Gemini error ({model}): {e} "
                    f"(retry {attempt + 1} in {delay}s)"
                )
                await asyncio.sleep(delay)

        return None

    @property
    def is_available(self) -> bool:
        """Check if Gemini provider is ready."""
        return GEMINI_AVAILABLE and self.connected
