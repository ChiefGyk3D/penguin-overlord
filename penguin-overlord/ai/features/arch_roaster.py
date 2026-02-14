# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
Arch Roaster - AI-powered Arch Linux roasting.

Generates contextual, witty roasts for Arch Linux users based on
what they said, their username, and classic Arch stereotypes.
Powered by LLM for creative, non-repetitive roasts.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


ARCH_ROAST_SYSTEM_PROMPT = """You are a witty, sarcastic Linux expert who playfully roasts Arch Linux users.
You are the Gordon Ramsay of Linux distributions — brutally funny but never actually mean.

Your roasts should be:
- SHORT: Under 120 characters. Brevity is the soul of wit.
- FUNNY: Genuinely clever, not just "haha arch bad"
- CONTEXTUAL: Reference what the user actually said when possible
- STEREOTYPICAL: Play on classic Arch user stereotypes:
  * "BTW I use Arch" evangelism
  * Obsessive ricing and dotfile management
  * Breaking systems with rolling updates
  * Reading the Arch Wiki like scripture
  * Thinking GUIs are bloat
  * Spending hours on minimal installs
  * Compiling everything from source
  * Having strong opinions about init systems
  * Measuring boot times competitively
  * Considering Ubuntu "training wheels"
- EMOJI: Include exactly ONE appropriate emoji
- SAFE: Never be racist, sexist, homophobic, or genuinely cruel

You are roasting the DISTRO CHOICE, not the person. Keep it fun.

Generate ONE short roast only. No explanations, no quotes, no preamble — just the roast."""


class ArchRoaster:
    """AI-powered Arch Linux roaster feature."""

    def __init__(self, generate_func):
        """
        Initialize the Arch Roaster.

        Args:
            generate_func: Async function(feature, prompt, system_prompt, **kwargs) -> str
                          Provided by AIManager for routing to the correct provider.
        """
        self._generate = generate_func

    async def roast(
        self,
        message_content: str,
        username: str,
        context: Optional[str] = None,
    ) -> Optional[str]:
        """
        Generate a contextual Arch Linux roast.

        Args:
            message_content: The message that triggered the roast
            username: Username of the person to roast
            context: Optional additional context (e.g., channel name)

        Returns:
            A witty roast string or None if generation failed
        """
        user_prompt = f"User '{username}' said: \"{message_content[:300]}\"\n\n"
        if context:
            user_prompt += f"Context: {context}\n\n"
        user_prompt += "Generate a playful Arch Linux roast for them. Under 120 characters with one emoji."

        result = await self._generate(
            feature='roasting',
            prompt=user_prompt,
            system_prompt=ARCH_ROAST_SYSTEM_PROMPT,
            temperature=0.85,
            max_tokens=80,
            timeout=15,
        )

        if result:
            # Clean up common LLM artifacts
            result = result.strip().strip('"\'')
            # Ensure it's not too long for Discord
            if len(result) > 200:
                result = result[:197] + '...'

        return result

    async def roast_custom(
        self,
        target: str,
        topic: str = 'Arch Linux',
    ) -> Optional[str]:
        """
        Generate a custom roast on a specific topic.

        Args:
            target: Who/what to roast
            topic: Topic for the roast (default: Arch Linux)

        Returns:
            A witty roast string or None
        """
        user_prompt = (
            f"Generate a playful roast about '{target}' related to {topic}. "
            f"Under 120 characters with one emoji."
        )

        return await self._generate(
            feature='roasting',
            prompt=user_prompt,
            system_prompt=ARCH_ROAST_SYSTEM_PROMPT,
            temperature=0.9,
            max_tokens=80,
            timeout=15,
        )
