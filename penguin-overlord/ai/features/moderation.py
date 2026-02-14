# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
Moderation Analyzer - AI-powered content moderation (stub for future).

This module provides the foundation for AI-based content moderation using
models like Llama Guard. Instead of pure regex matching, this enables
contextual understanding of messages for moderation decisions.

Future capabilities:
    - Context-aware toxicity detection
    - Intent analysis (is this a joke or genuine harassment?)
    - Severity scoring for automated action thresholds
    - Multi-language moderation
    - Appeal context analysis

Currently implemented as a stub that defines the interface. The actual
moderation logic will be built out as the feature matures.

Recommended models:
    - llama-guard3:8b: Meta's purpose-built moderation model
    - llama-guard3:1b: Lighter version for faster responses
"""

import logging
from typing import Optional, Dict, List
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class ModerationCategory(Enum):
    """Categories of content that may require moderation."""
    SAFE = 'safe'
    HARASSMENT = 'harassment'
    HATE_SPEECH = 'hate_speech'
    SEXUAL_CONTENT = 'sexual_content'
    VIOLENCE = 'violence'
    SELF_HARM = 'self_harm'
    SPAM = 'spam'
    MISINFORMATION = 'misinformation'
    UNKNOWN = 'unknown'


@dataclass
class ModerationResult:
    """Result of a moderation analysis."""
    is_safe: bool
    category: ModerationCategory
    confidence: float  # 0.0 to 1.0
    reason: str
    suggested_action: str  # 'none', 'warn', 'delete', 'mute', 'ban', 'review'
    raw_response: str = ''


MODERATION_SYSTEM_PROMPT = """You are a content moderation assistant. Analyze the given message
for policy violations. Consider context — sarcasm, jokes, and tech banter
are generally acceptable. Focus on genuine harmful intent.

Categories:
- safe: No issues
- harassment: Targeting individuals with harmful intent
- hate_speech: Discrimination based on protected characteristics
- sexual_content: Explicit sexual content
- violence: Threats or glorification of violence
- self_harm: Content promoting self-harm
- spam: Commercial spam or unsolicited advertising
- misinformation: Deliberately false information presented as fact

Respond in EXACTLY this format:
SAFE: true/false
CATEGORY: <category>
CONFIDENCE: <0.0-1.0>
REASON: <brief explanation>
ACTION: none/warn/delete/mute/review

Err on the side of permissiveness. Tech communities are informal.
Arch Linux jokes, friendly banter, and mild profanity are fine."""


class ModerationAnalyzer:
    """
    AI-powered content moderation feature.

    Currently a foundational stub — provides the interface and basic
    analysis capability. Future versions will add:
    - Conversation context analysis (not just single messages)
    - User history consideration
    - Custom server rules integration
    - Automated action pipelines
    """

    def __init__(self, generate_func):
        """
        Initialize the Moderation Analyzer.

        Args:
            generate_func: Async function(feature, prompt, system_prompt, **kwargs) -> str
                          Provided by AIManager for routing to the correct provider.
        """
        self._generate = generate_func

    async def analyze(
        self,
        message_content: str,
        username: str = '',
        channel_name: str = '',
        context_messages: Optional[List[str]] = None,
    ) -> Optional[ModerationResult]:
        """
        Analyze a message for moderation.

        Args:
            message_content: The message to analyze
            username: Author's username for context
            channel_name: Channel name for context
            context_messages: Optional list of recent messages for context

        Returns:
            ModerationResult or None if analysis failed
        """
        user_prompt = f"Message from '{username}'"
        if channel_name:
            user_prompt += f" in #{channel_name}"
        user_prompt += f":\n\"{message_content[:1000]}\"\n"

        if context_messages:
            user_prompt += "\nRecent context:\n"
            for msg in context_messages[-5:]:  # Last 5 messages
                user_prompt += f"- {msg[:200]}\n"

        user_prompt += "\nAnalyze this message for moderation."

        result = await self._generate(
            feature='moderation',
            prompt=user_prompt,
            system_prompt=MODERATION_SYSTEM_PROMPT,
            temperature=0.1,  # Very low creativity for moderation
            max_tokens=100,
            timeout=15,
        )

        if result:
            return self._parse_moderation_result(result)

        return None

    async def is_safe(self, message_content: str) -> bool:
        """
        Quick safety check for a message.

        Returns True if the message appears safe, False if it may need review.
        Defaults to True (safe) if analysis fails — errs on the side of permissiveness.
        """
        result = await self.analyze(message_content)
        if result is None:
            return True  # Default to safe if AI is unavailable
        return result.is_safe

    def _parse_moderation_result(self, raw_response: str) -> Optional[ModerationResult]:
        """Parse the structured moderation response from the LLM."""
        import re

        try:
            safe_match = re.search(r'SAFE:\s*(true|false)', raw_response, re.IGNORECASE)
            cat_match = re.search(r'CATEGORY:\s*(\w+)', raw_response, re.IGNORECASE)
            conf_match = re.search(r'CONFIDENCE:\s*([\d.]+)', raw_response, re.IGNORECASE)
            reason_match = re.search(r'REASON:\s*(.+?)(?:\n|$)', raw_response, re.IGNORECASE)
            action_match = re.search(r'ACTION:\s*(\w+)', raw_response, re.IGNORECASE)

            is_safe = True
            if safe_match:
                is_safe = safe_match.group(1).lower() == 'true'

            category = ModerationCategory.UNKNOWN
            if cat_match:
                try:
                    category = ModerationCategory(cat_match.group(1).lower())
                except ValueError:
                    category = ModerationCategory.UNKNOWN

            confidence = 0.5
            if conf_match:
                confidence = max(0.0, min(1.0, float(conf_match.group(1))))

            reason = ''
            if reason_match:
                reason = reason_match.group(1).strip()

            action = 'none' if is_safe else 'review'
            if action_match:
                action = action_match.group(1).lower()

            return ModerationResult(
                is_safe=is_safe,
                category=category,
                confidence=confidence,
                reason=reason,
                suggested_action=action,
                raw_response=raw_response,
            )

        except Exception as e:
            logger.error(f"Failed to parse moderation result: {e}")
            return None
