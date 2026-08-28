# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Arch Roaster - AI-powered Arch Linux roasting.

Generates contextual, witty roasts for Arch Linux users based on what they
said. The caller (arch_banter cog) always keeps the static joke list as
the fallback, so a failed or guardrail-blocked generation costs nothing.
"""

import logging

from ai.guardrails import sanitize_input

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
- SAFE: Never be racist, sexist, homophobic, transphobic, antisemitic, or genuinely cruel

You are roasting the DISTRO CHOICE, not the person. Keep it fun.

Generate ONE short roast only. No explanations, no quotes, no preamble — just the roast."""


class ArchRoaster:
    """AI-powered Arch Linux roaster feature."""

    def __init__(self, manager):
        self._manager = manager

    async def roast(self, message_content: str, username: str, context: str = None):
        """Generate a contextual Arch Linux roast, or None on any failure."""
        safe_content = sanitize_input(message_content, max_length=300)
        safe_username = sanitize_input(username, max_length=64)

        user_prompt = f"User '{safe_username}' said: \"{safe_content}\"\n\n"
        if context:
            user_prompt += f"Context: {sanitize_input(context, max_length=100)}\n\n"
        user_prompt += "Generate a playful Arch Linux roast for them. Under 120 characters with one emoji."

        return await self._manager.generate(
            feature='roasting',
            prompt=user_prompt,
            system_prompt=ARCH_ROAST_SYSTEM_PROMPT,
            temperature=0.85,
            max_tokens=80,
            timeout=15,
        )
