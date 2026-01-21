# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
Ollama LLM Client - Local LLM integration for Penguin Overlord.
Provides smart quote selection, contextual roasts, and conversational features.
"""

import logging
import os
from typing import Optional, Dict, Any
import asyncio
from functools import lru_cache

logger = logging.getLogger(__name__)

# Try to import Ollama - gracefully degrade if not available
try:
    import ollama
    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False
    logger.warning("Ollama not available - LLM features will be disabled")


class OllamaClient:
    """Client for interacting with local Ollama LLM."""
    
    # Model-specific configurations for optimal performance
    MODEL_CONFIGS = {
        # Gemma models
        'gemma2:2b': {'temperature': 0.7, 'num_predict': 150, 'context_window': 8192},
        'gemma2:9b': {'temperature': 0.7, 'num_predict': 200, 'context_window': 8192},
        'gemma3:4b': {'temperature': 0.7, 'num_predict': 200, 'context_window': 8192},
        'gemma3:12b': {'temperature': 0.7, 'num_predict': 250, 'context_window': 8192},
        
        # Llama models
        'llama3.2:1b': {'temperature': 0.7, 'num_predict': 120, 'context_window': 128000},
        'llama3.2:3b': {'temperature': 0.7, 'num_predict': 150, 'context_window': 128000},
        'llama3.1:8b': {'temperature': 0.7, 'num_predict': 200, 'context_window': 128000},
        'llama3.1:70b': {'temperature': 0.7, 'num_predict': 300, 'context_window': 128000},
        'llama3.3:70b': {'temperature': 0.7, 'num_predict': 300, 'context_window': 128000},
        
        # Phi models (Microsoft)
        'phi3:mini': {'temperature': 0.7, 'num_predict': 120, 'context_window': 128000},
        'phi3:medium': {'temperature': 0.7, 'num_predict': 180, 'context_window': 128000},
        'phi4:latest': {'temperature': 0.7, 'num_predict': 200, 'context_window': 16384},
        
        # Qwen models
        'qwen2.5:0.5b': {'temperature': 0.7, 'num_predict': 100, 'context_window': 32768},
        'qwen2.5:3b': {'temperature': 0.7, 'num_predict': 150, 'context_window': 32768},
        'qwen2.5:7b': {'temperature': 0.7, 'num_predict': 200, 'context_window': 128000},
        
        # Mistral models
        'mistral:7b': {'temperature': 0.7, 'num_predict': 200, 'context_window': 32000},
        'mixtral:8x7b': {'temperature': 0.7, 'num_predict': 250, 'context_window': 32000},
    }
    
    def __init__(self, model: str = "gemma2:2b", enabled: bool = True):
        """
        Initialize Ollama client.
        
        Args:
            model: Ollama model to use (default: gemma2:2b for speed/quality balance)
                  Supported: gemma2/3, llama3.x, phi3/4, qwen2.5, mistral, mixtral
            enabled: Whether LLM features are enabled (default: True, falls back if unavailable)
        """
        self.model = model
        self.enabled = enabled and OLLAMA_AVAILABLE
        self._model_config = self._get_model_config(model)
        self._check_availability()
    
    def _get_model_config(self, model: str) -> Dict[str, Any]:
        """Get configuration for specific model or use defaults."""
        # Try exact match first
        if model in self.MODEL_CONFIGS:
            return self.MODEL_CONFIGS[model]
        
        # Try partial match (e.g., "gemma3:4b-it" matches "gemma3:4b")
        for known_model, config in self.MODEL_CONFIGS.items():
            if model.startswith(known_model.split(':')[0]):
                logger.info(f"Using config from {known_model} for similar model {model}")
                return config
        
        # Default configuration for unknown models
        logger.info(f"Using default config for unknown model {model}")
        return {'temperature': 0.7, 'num_predict': 150, 'context_window': 8192}
    
    def _check_availability(self):
        """Check if Ollama is actually available and running."""
        if not self.enabled:
            return
        
        try:
            # Try to list models to verify Ollama is running
            ollama.list()
            logger.info(f"Ollama is available, using model: {self.model}")
        except Exception as e:
            logger.warning(f"Ollama is installed but not running or accessible: {e}")
            self.enabled = False
    
    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        timeout: int = 10
    ) -> Optional[str]:
        """
        Generate text using Ollama.
        
        Args:
            prompt: The user prompt
            system_prompt: Optional system prompt for context
            temperature: Creativity level (0.0-1.0), uses model default if None
            max_tokens: Maximum response length, uses model default if None
            timeout: Request timeout in seconds
            
        Returns:
            Generated text or None if failed/disabled
        """
        if not self.enabled:
            return None
        
        # Use model-specific defaults if not specified
        temperature = temperature if temperature is not None else self._model_config['temperature']
        max_tokens = max_tokens if max_tokens is not None else self._model_config['num_predict']
        
        try:
            # Run in executor to avoid blocking
            loop = asyncio.get_event_loop()
            response = await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    lambda: ollama.generate(
                        model=self.model,
                        prompt=prompt,
                        system=system_prompt,
                        options={
                            'temperature': temperature,
                            'num_predict': max_tokens,
                            'top_p': 0.9,
                            'top_k': 40,
                            'num_ctx': self._model_config.get('context_window', 8192)
                        }
                    )
                ),
                timeout=timeout
            )
            
            return response['response'].strip()
        
        except asyncio.TimeoutError:
            logger.error(f"Ollama request timed out after {timeout}s (model: {self.model})")
            return None
        except Exception as e:
            logger.error(f"Ollama generation error (model: {self.model}): {e}")
            return None
    
    async def generate_arch_roast(
        self,
        message_content: str,
        username: str,
        context: Optional[str] = None
    ) -> Optional[str]:
        """
        Generate a contextual Arch Linux roast.
        
        Args:
            message_content: The message that mentioned Arch
            username: User to roast
            context: Optional additional context
            
        Returns:
            Generated roast or None if failed
        """
        system_prompt = """You are a witty Linux expert who playfully roasts Arch Linux users. 
Keep roasts:
- Short (under 120 characters)
- Funny and lighthearted, never mean
- Related to Arch Linux stereotypes (btw I use arch, ricing, AUR, pacman, etc)
- Include an appropriate emoji
- Focus on the classic Arch user stereotypes: telling everyone, over-customization, breaking systems, reading wikis, etc.

Generate ONE short roast only. No explanations, just the roast."""

        user_prompt = f"""User '{username}' said: "{message_content[:200]}"

Generate a playful Arch Linux roast for them. Keep it under 120 characters with an emoji."""

        return await self.generate(
            prompt=user_prompt,
            system_prompt=system_prompt,
            temperature=0.8,
            max_tokens=80,
            timeout=8
        )
    
    async def analyze_quote_relevance(
        self,
        quote: str,
        author: str,
        search_query: str
    ) -> float:
        """
        Analyze how relevant a quote is to a search query.
        
        Args:
            quote: The quote text
            author: Quote author
            search_query: User's search query
            
        Returns:
            Relevance score (0.0-1.0) or 0.0 if failed
        """
        system_prompt = """You are a tech quote relevance analyzer. 
Rate how relevant a tech quote is to a search query on a scale of 0.0 to 1.0.
Consider: topic match, keyword overlap, thematic similarity, and context.
Respond with ONLY a number between 0.0 and 1.0, nothing else."""

        user_prompt = f"""Search query: "{search_query}"

Quote: "{quote}" - {author}

Relevance score (0.0-1.0):"""

        try:
            response = await self.generate(
                prompt=user_prompt,
                system_prompt=system_prompt,
                temperature=0.3,
                max_tokens=10,
                timeout=5
            )
            
            if response:
                # Extract first number found
                import re
                match = re.search(r'(\d+\.?\d*)', response)
                if match:
                    score = float(match.group(1))
                    return max(0.0, min(1.0, score))  # Clamp to 0-1
            
            return 0.0
        except Exception as e:
            logger.error(f"Error analyzing quote relevance: {e}")
            return 0.0
    
    async def generate_quote_insight(
        self,
        quote: str,
        author: str,
        author_bio: str
    ) -> Optional[str]:
        """
        Generate an insightful explanation or context for a quote.
        
        Args:
            quote: The quote text
            author: Quote author
            author_bio: Author's bio/description
            
        Returns:
            Generated insight or None if failed
        """
        system_prompt = """You are a tech historian and software engineering expert.
Provide brief, insightful context about tech quotes.
Keep explanations:
- Under 200 characters
- Educational yet conversational
- Focused on why the quote matters
- Related to software engineering, computer science, or tech culture

Generate ONE brief insight only."""

        user_prompt = f"""Quote: "{quote}"
Author: {author} ({author_bio})

Provide a brief insight about this quote's significance or context:"""

        return await self.generate(
            prompt=user_prompt,
            system_prompt=system_prompt,
            temperature=0.6,
            max_tokens=100,
            timeout=8
        )
    
    def is_enabled(self) -> bool:
        """Check if Ollama features are enabled and available."""
        return self.enabled


# Global instance - can be configured via environment variables
@lru_cache(maxsize=1)
def get_ollama_client() -> OllamaClient:
    """Get or create global Ollama client instance."""
    model = os.getenv('OLLAMA_MODEL', 'gemma2:2b')
    enabled = os.getenv('OLLAMA_ENABLED', 'true').lower() in ('true', '1', 'yes')
    return OllamaClient(model=model, enabled=enabled)
