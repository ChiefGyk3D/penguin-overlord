# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
Moderation Analyzer - AI-powered content moderation with human-in-the-loop.

Provides contextual moderation using Llama Guard or similar safety models.
Goes beyond simple keyword matching to detect nuanced policy violations
including doxxing attempts, PII exposure, coordinated harassment, and
social engineering.

Model recommendations by VRAM budget:
    ┌──────────────────────────────────────────────────────────────────────┐
    │  Model                 │ VRAM    │ Speed   │ Accuracy │ Notes      │
    ├──────────────────────────────────────────────────────────────────────┤
    │  llama-guard3:1b       │ ~1.5 GB │ Fast    │ Good     │ CPU viable │
    │  llama-guard3:8b-q4_0  │ ~4.5 GB │ Medium  │ Better   │ 3070 ideal │
    │  llama-guard3:8b-q5_1  │ ~6.0 GB │ Medium  │ Better+  │ 3070 tight │
    │  llama-guard3:8b       │ ~8.0 GB │ Slower  │ Best     │ Needs ≥10GB│
    └──────────────────────────────────────────────────────────────────────┘

    For an RTX 3070 (8 GB VRAM):
        - Best: ``llama-guard3:8b-q4_0`` — quantized to 4-bit, fits in ~4.5 GB
          leaving room for KV cache.  Good accuracy/speed balance.
        - Alternative: ``llama-guard3:1b`` at full precision — fastest, lower
          accuracy but still catches obvious violations.
        - NOT recommended: full ``llama-guard3:8b`` at fp16 — will OOM or
          spill to system RAM on 8 GB cards.

    To pull a quantized model::

        ollama pull llama-guard3:8b-q4_0

    Or create a custom Modelfile for specific quantization::

        FROM llama-guard3:8b
        PARAMETER num_gpu 99
        PARAMETER num_ctx 4096
"""

import logging
import re
from typing import Optional, List
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class ModerationCategory(Enum):
    """Categories of content that may require moderation."""
    SAFE = 'safe'
    # Core toxicity categories
    HARASSMENT = 'harassment'
    HATE_SPEECH = 'hate_speech'
    SEXUAL_CONTENT = 'sexual_content'
    VIOLENCE = 'violence'
    SELF_HARM = 'self_harm'
    SPAM = 'spam'
    MISINFORMATION = 'misinformation'
    # Privacy & security categories
    DOXXING = 'doxxing'
    PII_EXPOSURE = 'pii_exposure'
    SOCIAL_ENGINEERING = 'social_engineering'
    # Coordination categories
    RAID = 'raid'
    EVASION = 'evasion'
    UNKNOWN = 'unknown'


# Map suggested actions to severity tiers
ACTION_SEVERITY = {
    'none': 0,
    'warn': 1,
    'delete': 2,
    'mute': 3,
    'timeout': 3,
    'kick': 4,
    'ban': 5,
    'review': 2,
}

# Actions that REQUIRE human-in-the-loop approval
ACTIONS_REQUIRING_REVIEW = {'kick', 'ban'}

# Actions the bot can take automatically (below the review threshold)
AUTO_ACTIONS = {'none', 'warn', 'delete', 'mute', 'timeout'}


@dataclass
class ModerationResult:
    """Result of a moderation analysis."""
    is_safe: bool
    category: ModerationCategory
    confidence: float  # 0.0 to 1.0
    reason: str
    suggested_action: str  # 'none', 'warn', 'delete', 'mute', 'timeout', 'kick', 'ban', 'review'
    raw_response: str = ''
    pii_detected: List[str] = field(default_factory=list)  # Types of PII found


MODERATION_SYSTEM_PROMPT = """You are a Discord server content moderation assistant. Analyze the given
message for policy violations. Consider context — sarcasm, jokes, and tech banter
are generally acceptable. Focus on genuine harmful intent.

Categories (choose the MOST specific one):
- safe: No issues
- harassment: Targeting individuals with sustained hostile intent
- hate_speech: Discrimination/slurs based on protected characteristics (race, gender, orientation, religion, disability)
- sexual_content: Explicit sexual material or unsolicited sexual messages
- violence: Credible threats of violence, glorification of real-world violence, or instructions to harm
- self_harm: Content promoting, encouraging, or instructing self-harm or suicide
- spam: Commercial spam, unsolicited advertising, or bot-like behavior
- misinformation: Deliberately false claims presented as fact (especially health/safety)
- doxxing: Sharing or threatening to share someone's private information (real name, address, phone number, workplace, school, IP address, photos) WITHOUT their consent
- pii_exposure: Accidentally or carelessly posting personal identifiable information (own or others')
- social_engineering: Attempting to manipulate users into revealing credentials, clicking malicious links, or bypassing security
- raid: Coordinated disruptive behavior, mass spam, or organized trolling
- evasion: Attempting to bypass moderation (Unicode tricks, leetspeak to dodge filters, alt accounts)

Severity-based actions:
- none: Safe content, no action needed
- warn: Minor issue, inform the user
- delete: Remove the message (moderate violations)
- mute: Temporarily mute the user (repeated offenses or moderate-high severity)
- timeout: Timeout the user for a configurable duration
- kick: Remove from server (requires human moderator approval)
- ban: Permanent ban (requires human moderator approval)
- review: Send to human moderators for manual review (when uncertain)

IMPORTANT GUIDELINES:
- Tech communities are informal. Arch Linux jokes, friendly banter, and mild profanity are FINE.
- Err on the side of permissiveness for ambiguous cases — use 'review' when unsure.
- Doxxing is ALWAYS high severity regardless of context.
- PII exposure should list WHAT types of PII were found (comma-separated).
- For kick/ban recommendations, you must be highly confident (>0.85).
- Consider repeat offender context when provided.

Respond in EXACTLY this format:
SAFE: true/false
CATEGORY: <category>
CONFIDENCE: <0.0-1.0>
REASON: <brief explanation>
ACTION: none/warn/delete/mute/timeout/kick/ban/review
PII: <comma-separated list of PII types found, or 'none'>"""


class ModerationAnalyzer:
    """
    AI-powered content moderation with escalation tiers.

    Supports:
    - 13 violation categories including doxxing and PII detection
    - Automatic actions for low/medium severity (warn, delete, mute)
    - Human-in-the-loop escalation for high severity (kick, ban)
    - Configurable timeout durations
    - Repeat offender awareness (when history is provided)
    - Pre-filter heuristics for obvious PII before sending to LLM

    Model recommendations for RTX 3070 (8 GB VRAM):
    - llama-guard3:8b-q4_0: Best balance of accuracy and VRAM usage (~4.5 GB)
    - llama-guard3:1b: Fastest, lowest VRAM, good for high-throughput servers
    """

    # Regex heuristics for obvious PII (pre-LLM fast path)
    _PII_PATTERNS = {
        'email': re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'),
        'phone': re.compile(r'(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}'),
        'ssn': re.compile(r'\b\d{3}-\d{2}-\d{4}\b'),
        'ip_address': re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b'),
        'credit_card': re.compile(r'\b(?:\d{4}[-\s]?){3}\d{4}\b'),
        'address': re.compile(
            r'\b\d{1,5}\s+\w+\s+(?:St|Street|Ave|Avenue|Blvd|Boulevard|Dr|Drive|Ln|Lane|Rd|Road|Ct|Court|Way|Pl|Place)\b',
            re.IGNORECASE,
        ),
    }

    def __init__(self, generate_func):
        """
        Initialize the Moderation Analyzer.

        Args:
            generate_func: Async function(feature, prompt, system_prompt, **kwargs) -> str
                          Provided by AIManager for routing to the correct provider.
        """
        self._generate = generate_func

    def pre_scan_pii(self, text: str) -> List[str]:
        """
        Fast regex-based PII scan (runs BEFORE sending to the LLM).

        Returns a list of PII types detected (e.g., ['email', 'phone']).
        """
        found = []
        for pii_type, pattern in self._PII_PATTERNS.items():
            if pattern.search(text):
                found.append(pii_type)
        return found

    async def analyze(
        self,
        message_content: str,
        username: str = '',
        channel_name: str = '',
        context_messages: Optional[List[str]] = None,
        infraction_count: int = 0,
        default_timeout_minutes: int = 10,
    ) -> Optional[ModerationResult]:
        """
        Analyze a message for moderation.

        Args:
            message_content: The message to analyze
            username: Author's username for context
            channel_name: Channel name for context
            context_messages: Optional list of recent messages for context
            infraction_count: Number of prior infractions for this user
            default_timeout_minutes: Default timeout duration in minutes

        Returns:
            ModerationResult or None if analysis failed
        """
        # Fast PII pre-scan
        pii_types = self.pre_scan_pii(message_content)

        # Build the analysis prompt
        user_prompt = f"Message from '{username}'"
        if channel_name:
            user_prompt += f" in #{channel_name}"
        user_prompt += f":\n\"{message_content[:1500]}\"\n"

        if infraction_count > 0:
            user_prompt += f"\n⚠️ This user has {infraction_count} prior infraction(s).\n"

        if pii_types:
            user_prompt += f"\n🔍 Pre-scan detected potential PII: {', '.join(pii_types)}\n"

        if context_messages:
            user_prompt += "\nRecent context:\n"
            for msg in context_messages[-5:]:
                user_prompt += f"- {msg[:200]}\n"

        user_prompt += "\nAnalyze this message for moderation."

        result = await self._generate(
            feature='moderation',
            prompt=user_prompt,
            system_prompt=MODERATION_SYSTEM_PROMPT,
            temperature=0.1,
            max_tokens=150,
            timeout=15,
        )

        if result:
            mod_result = self._parse_moderation_result(result)
            if mod_result:
                # Merge PII from pre-scan with LLM detection
                if pii_types and not mod_result.pii_detected:
                    mod_result.pii_detected = pii_types
                elif pii_types:
                    mod_result.pii_detected = list(set(mod_result.pii_detected + pii_types))

                # If PII was found but category is SAFE, override
                if mod_result.pii_detected and mod_result.category == ModerationCategory.SAFE:
                    mod_result.is_safe = False
                    mod_result.category = ModerationCategory.PII_EXPOSURE
                    if mod_result.suggested_action == 'none':
                        mod_result.suggested_action = 'delete'

                # Escalate action for repeat offenders
                if infraction_count >= 5 and mod_result.suggested_action in ('warn', 'delete'):
                    mod_result.suggested_action = 'timeout'
                elif infraction_count >= 10 and mod_result.suggested_action in ('warn', 'delete', 'mute', 'timeout'):
                    mod_result.suggested_action = 'review'

                return mod_result

        return None

    async def is_safe(self, message_content: str) -> bool:
        """
        Quick safety check for a message.

        Returns True if the message appears safe, False if it may need review.
        Defaults to True (safe) if analysis fails — errs on the side of permissiveness.
        """
        if self.pre_scan_pii(message_content):
            return False

        result = await self.analyze(message_content)
        if result is None:
            return True
        return result.is_safe

    def needs_human_review(self, result: ModerationResult) -> bool:
        """
        Check if a moderation result requires human moderator approval.

        Returns True for:
        - Kick/ban actions (always require approval)
        - Doxxing (always escalate)
        - Low-confidence high-severity detections
        """
        if result.suggested_action in ACTIONS_REQUIRING_REVIEW:
            return True
        if result.category == ModerationCategory.DOXXING:
            return True
        if not result.is_safe and result.confidence < 0.6:
            return True
        return False

    def _parse_moderation_result(self, raw_response: str) -> Optional[ModerationResult]:
        """Parse the structured moderation response from the LLM."""
        try:
            safe_match = re.search(r'SAFE:\s*(true|false)', raw_response, re.IGNORECASE)
            cat_match = re.search(r'CATEGORY:\s*([\w_]+)', raw_response, re.IGNORECASE)
            conf_match = re.search(r'CONFIDENCE:\s*([\d.]+)', raw_response, re.IGNORECASE)
            reason_match = re.search(r'REASON:\s*(.+?)(?:\n|$)', raw_response, re.IGNORECASE)
            action_match = re.search(r'ACTION:\s*(\w+)', raw_response, re.IGNORECASE)
            pii_match = re.search(r'PII:\s*(.+?)(?:\n|$)', raw_response, re.IGNORECASE)

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

            pii_detected = []
            if pii_match:
                pii_raw = pii_match.group(1).strip().lower()
                if pii_raw != 'none':
                    pii_detected = [p.strip() for p in pii_raw.split(',') if p.strip()]

            return ModerationResult(
                is_safe=is_safe,
                category=category,
                confidence=confidence,
                reason=reason,
                suggested_action=action,
                raw_response=raw_response,
                pii_detected=pii_detected,
            )

        except Exception as e:
            logger.error(f"Failed to parse moderation result: {e}")
            return None
