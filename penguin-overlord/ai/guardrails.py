# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
Guardrails - Multi-layer content safety and quality pipeline for AI outputs.

Adapted from Stream Daemon and Boon Tube Daemon guardrail patterns.
Provides output sanitization, content filtering, hallucination detection,
quality scoring, deduplication, and Discord-specific validation.

Each AI feature can configure which guardrails are active and at what
sensitivity level. The pipeline applies checks in order and can either
fix issues automatically or flag them for retry.
"""

import logging
import re
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


# ── Configuration ──────────────────────────────────────────────────────────


class ProfanitySeverity(str, Enum):
    MILD = 'mild'
    MODERATE = 'moderate'
    SEVERE = 'severe'


@dataclass
class GuardrailConfig:
    """Per-feature guardrail settings."""

    # Length enforcement
    max_length: int = 400
    min_length: int = 10

    # Content filtering
    enable_profanity_filter: bool = False
    profanity_severity: str = 'moderate'
    enable_clickbait_filter: bool = True
    enable_hallucination_check: bool = True

    # Output sanitization
    strip_meta_text: bool = True
    strip_urls: bool = True
    fix_escaped_chars: bool = True
    max_emoji_count: int = 2

    # Quality
    enable_quality_scoring: bool = False
    min_quality_score: int = 5

    # Deduplication
    enable_deduplication: bool = True
    dedup_cache_size: int = 50

    # Discord-specific
    enable_discord_validation: bool = True

    # Input sanitization
    enable_input_sanitization: bool = True
    max_input_length: int = 3000

    # Feature-specific patterns
    feature_hallucination_patterns: List[str] = field(default_factory=list)
    custom_forbidden_patterns: List[str] = field(default_factory=list)

    # Strict-mode retry
    enable_strict_retry: bool = True


# Default configs per feature
FEATURE_GUARDRAIL_DEFAULTS: Dict[str, GuardrailConfig] = {
    'roasting': GuardrailConfig(
        max_length=200,
        min_length=10,
        enable_profanity_filter=False,  # Roasts can be edgy
        enable_clickbait_filter=False,
        enable_hallucination_check=False,
        max_emoji_count=3,
        enable_quality_scoring=False,
        strip_urls=True,
        enable_deduplication=True,
        dedup_cache_size=30,
    ),
    'news': GuardrailConfig(
        max_length=400,
        min_length=30,
        enable_profanity_filter=True,
        profanity_severity='moderate',
        enable_clickbait_filter=True,
        enable_hallucination_check=True,
        max_emoji_count=1,
        enable_quality_scoring=True,
        min_quality_score=5,
        strip_urls=True,
        enable_deduplication=True,
        dedup_cache_size=100,
        feature_hallucination_patterns=[
            r'(?:according to (?:unnamed|anonymous) sources)',
            r'(?:breaking|exclusive|shocking)\s*:',
            r'(?:millions|billions)\s+(?:of\s+)?(?:users?|people)\s+affected',
        ],
    ),
    'cve': GuardrailConfig(
        max_length=450,
        min_length=30,
        enable_profanity_filter=True,
        profanity_severity='severe',
        enable_clickbait_filter=True,
        enable_hallucination_check=True,
        max_emoji_count=0,
        enable_quality_scoring=True,
        min_quality_score=6,
        strip_urls=True,
        enable_deduplication=True,
        dedup_cache_size=200,
        feature_hallucination_patterns=[
            r'CVE-\d{4}-\d{4,}',  # Don't invent CVE IDs not in the prompt
            r'CVSS\s*(?:score)?\s*:?\s*\d+\.?\d*\s*/\s*10',  # Don't invent scores
            r'(?:confirmed|verified)\s+(?:by|with)\s+(?:the\s+)?vendor',
            r'(?:patch|fix)\s+(?:is\s+)?(?:already\s+)?available\s+at',
        ],
    ),
    'moderation': GuardrailConfig(
        max_length=200,
        min_length=5,
        enable_profanity_filter=False,  # Must be able to output profanity categories
        enable_clickbait_filter=False,
        enable_hallucination_check=False,
        max_emoji_count=0,
        enable_quality_scoring=False,
        strip_urls=True,
        enable_deduplication=False,
    ),
    'legislation': GuardrailConfig(
        max_length=400,
        min_length=30,
        enable_profanity_filter=True,
        profanity_severity='severe',
        enable_clickbait_filter=True,
        enable_hallucination_check=True,
        max_emoji_count=1,
        enable_quality_scoring=True,
        min_quality_score=5,
        strip_urls=True,
        enable_deduplication=True,
        dedup_cache_size=100,
        feature_hallucination_patterns=[
            r'(?:this bill will|this law will)\s+(?:definitely|certainly|surely)',
            r'(?:all\s+)?(?:democrats?|republicans?)\s+(?:oppose|support)',
            r'(?:sources?\s+say|insiders?\s+report)',
        ],
        custom_forbidden_patterns=[
            r'\b(?:liberal|conservative)\s+agenda\b',
            r'\b(?:left-wing|right-wing)\s+(?:plot|scheme|conspiracy)\b',
        ],
    ),
}


# ── Result Types ───────────────────────────────────────────────────────────


@dataclass
class GuardrailResult:
    """Result of running text through the guardrail pipeline."""
    text: str
    passed: bool
    issues: List[str] = field(default_factory=list)
    was_modified: bool = False
    score: Optional[int] = None
    blocked: bool = False  # Hard block — don't use this text at all


# ── Word Lists ─────────────────────────────────────────────────────────────


CLICKBAIT_WORDS = [
    'insane', 'epic', 'crazy', 'smash', 'unmissable',
    'incredible', 'amazing', 'lit', 'fire', 'legendary',
    'mind-blowing', 'jaw-dropping', 'unbelievable', 'shocking',
    'bombshell', 'game-changing', 'devastating', 'explosive',
]

PROFANITY_MILD = ['damn', 'hell', 'crap', 'suck', 'sucks', 'piss', 'pissed']
PROFANITY_MODERATE = ['ass', 'bastard', 'bitch', 'dick', 'cock', 'pussy', 'slut', 'whore']
PROFANITY_SEVERE = ['fuck', 'fucking', 'shit', 'shitty', 'motherfucker', 'asshole', 'cunt']

META_TEXT_PATTERNS = [
    r'^(?:Here\'?s?|Okay,?\s*here\'?s?|Alright,?\s*here\'?s?)\s+.*?:\s*',
    r'^(?:Here you go|Sure thing|Certainly|Of course).*?:\s*',
    r'^(?:Post|Draft|Output|Response|Answer|Summary|Analysis|Result).*?:\s*',
    r'^(?:I\'d\s+(?:say|suggest|recommend)|Let me|I\'ll)\s+.*?:\s*',
    r'^(?:Based on|According to|Given (?:the|this)).*?,\s*',
    r'^"',   # Leading quote
    r'"$',   # Trailing quote
]

GENERIC_PHRASES = [
    'in today\'s digital landscape',
    'it\'s important to note',
    'in conclusion',
    'in summary',
    'it goes without saying',
    'needless to say',
    'at the end of the day',
    'it remains to be seen',
    'only time will tell',
    'moving forward',
    'stay tuned',
    'watch this space',
    'the bottom line is',
    'there\'s no denying',
]

EMOJI_PATTERN = re.compile(
    "["
    "\U0001F600-\U0001F64F"  # emoticons
    "\U0001F300-\U0001F5FF"  # symbols & pictographs
    "\U0001F680-\U0001F6FF"  # transport & map
    "\U0001F1E0-\U0001F1FF"  # flags
    "\U00002702-\U000027B0"  # dingbats
    "\U000024C2-\U0001F251"  # enclosed chars
    "\U0001F900-\U0001F9FF"  # supplemental symbols
    "\U0001FA00-\U0001FA6F"  # chess symbols
    "\U0001FA70-\U0001FAFF"  # symbols extended-A
    "]", flags=re.UNICODE
)


# ── Guardrails Engine ──────────────────────────────────────────────────────


class Guardrails:
    """
    Multi-layer content safety and quality pipeline.

    Applies sanitization, content filtering, hallucination detection,
    quality scoring, and Discord-specific validation to AI outputs.

    Usage:
        guardrails = Guardrails()
        result = guardrails.apply(ai_output, config, feature='cve')
        if result.passed:
            use(result.text)
        elif result.blocked:
            fall_back()
        else:
            retry_with_strict_mode()
    """

    def __init__(self):
        # Per-feature dedup caches: feature -> deque of normalized texts
        self._dedup_caches: Dict[str, deque] = {}

    # ── Public API ──────────────────────────────────────────────────────

    def sanitize_input(self, text: str, max_length: int = 3000) -> str:
        """
        Sanitize user-provided input before interpolating into prompts.

        Prevents prompt injection and limits input size.

        Args:
            text: Raw user input (message content, titles, descriptions)
            max_length: Maximum allowed length

        Returns:
            Sanitized input string
        """
        if not text:
            return ''

        # Truncate to max length
        text = text[:max_length]

        # Strip control characters (keep newlines, tabs)
        text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)

        # Neutralize potential prompt injection markers
        injection_patterns = [
            (r'(?i)\b(?:ignore\s+(?:all\s+)?(?:previous|above|prior)\s+instructions?)\b', '[filtered]'),
            (r'(?i)\b(?:disregard\s+(?:all\s+)?(?:previous|above|prior)\s+(?:instructions?|prompts?))\b', '[filtered]'),
            (r'(?i)\b(?:you\s+are\s+now|act\s+as|pretend\s+(?:to\s+be|you\s+are))\b', '[filtered]'),
            (r'(?i)\b(?:system\s*(?:prompt|message|instruction))\s*:', '[filtered]:'),
            (r'(?i)<<\s*(?:SYS|SYSTEM|INST)\s*>>', '[filtered]'),
        ]
        for pattern, replacement in injection_patterns:
            text = re.sub(pattern, replacement, text)

        # Strip Discord mentions that shouldn't be in AI prompts
        text = re.sub(r'<@!?\d+>', '[user]', text)
        text = re.sub(r'<@&\d+>', '[role]', text)
        text = re.sub(r'<#\d+>', '[channel]', text)

        return text.strip()

    def apply(
        self,
        text: str,
        config: GuardrailConfig,
        feature: str = 'default',
        original_prompt: str = '',
    ) -> GuardrailResult:
        """
        Run text through the full guardrail pipeline.

        Args:
            text: AI-generated text to check
            config: Guardrail configuration for this feature
            feature: Feature name (for dedup caching and logging)
            original_prompt: Original prompt (for hallucination cross-checking)

        Returns:
            GuardrailResult with cleaned text, pass/fail status, and issues
        """
        if not text:
            return GuardrailResult(
                text='', passed=False, blocked=True,
                issues=['Empty AI response'],
            )

        issues: List[str] = []
        was_modified = False
        original_text = text

        # 1. Fix escaped characters
        if config.fix_escaped_chars:
            text = self._fix_escaped_chars(text)
            if text != original_text:
                was_modified = True

        # 2. Strip meta-text preambles
        if config.strip_meta_text:
            cleaned = self._strip_meta_text(text)
            if cleaned != text:
                text = cleaned
                was_modified = True

        # 3. Strip URLs from AI output
        if config.strip_urls:
            cleaned = self._strip_urls(text)
            if cleaned != text:
                text = cleaned
                was_modified = True
                issues.append('Stripped URL(s) from AI output')

        # 4. Discord-specific validation and cleanup
        if config.enable_discord_validation:
            cleaned, discord_issues = self._validate_discord(text)
            if discord_issues:
                issues.extend(discord_issues)
            if cleaned != text:
                text = cleaned
                was_modified = True

        # 5. Check forbidden/clickbait words
        if config.enable_clickbait_filter:
            has_clickbait, found = self._check_clickbait(text)
            if has_clickbait:
                issues.append(f'Clickbait words: {", ".join(found)}')

        # 6. Check custom forbidden patterns
        if config.custom_forbidden_patterns:
            for pattern in config.custom_forbidden_patterns:
                if re.search(pattern, text, re.IGNORECASE):
                    issues.append(f'Forbidden pattern matched: {pattern}')

        # 7. Profanity filter
        if config.enable_profanity_filter:
            has_profanity, found = self._check_profanity(text, config.profanity_severity)
            if has_profanity:
                issues.append(f'Profanity detected ({config.profanity_severity}): {", ".join(found)}')

        # 8. Emoji count
        emoji_count = self._count_emojis(text)
        if emoji_count > config.max_emoji_count:
            text = self._trim_emojis(text, config.max_emoji_count)
            was_modified = True
            issues.append(f'Emoji count {emoji_count} exceeded max {config.max_emoji_count}')

        # 9. Hallucination detection
        if config.enable_hallucination_check:
            hallucination_issues = self._check_hallucinations(
                text, feature, config.feature_hallucination_patterns, original_prompt
            )
            if hallucination_issues:
                issues.extend(hallucination_issues)

        # 10. Check minimum length
        stripped_text = text.strip()
        if len(stripped_text) < config.min_length:
            return GuardrailResult(
                text=stripped_text, passed=False, blocked=True,
                issues=issues + [f'Too short ({len(stripped_text)} < {config.min_length})'],
                was_modified=was_modified,
            )

        # 11. Enforce maximum length with safe trim
        if len(stripped_text) > config.max_length:
            stripped_text = self._safe_trim(stripped_text, config.max_length)
            was_modified = True
            issues.append(f'Trimmed to {config.max_length} chars')

        text = stripped_text

        # 12. Quality scoring
        score = None
        if config.enable_quality_scoring:
            score = self._score_quality(text)
            if score < config.min_quality_score:
                issues.append(f'Low quality score: {score}/{10} (min: {config.min_quality_score})')

        # 13. Deduplication check
        if config.enable_deduplication:
            is_dup = self._is_duplicate(text, feature, config.dedup_cache_size)
            if is_dup:
                issues.append('Duplicate of recent output')

        # Determine overall pass/fail
        # "Blocking" issues = those that should prevent usage entirely
        blocking_issues = [
            i for i in issues if any(b in i.lower() for b in [
                'profanity', 'duplicate', 'too short', 'low quality',
            ])
        ]

        passed = len(blocking_issues) == 0

        # If passed, record in dedup cache
        if passed and config.enable_deduplication:
            self._add_to_dedup_cache(text, feature, config.dedup_cache_size)

        return GuardrailResult(
            text=text,
            passed=passed,
            issues=issues,
            was_modified=was_modified,
            score=score,
            blocked=False,
        )

    def get_strict_prompt_prefix(self) -> str:
        """Get a prefix to prepend to prompts when retrying after guardrail failures."""
        return (
            "⚠️ CRITICAL: Your previous response violated content rules. "
            "FOLLOW INSTRUCTIONS EXACTLY this time.\n"
            "Rules:\n"
            "- NO clickbait words (insane, epic, amazing, incredible, mind-blowing, etc.)\n"
            "- NO profanity\n"
            "- NO speculation or fabricated details\n"
            "- NO URLs\n"
            "- NO meta-commentary (don't say 'Here's...' or 'Sure...')\n"
            "- Stay within the character limit\n"
            "- Be factual, concise, and direct\n\n"
        )

    # ── Internal pipeline stages ────────────────────────────────────────

    @staticmethod
    def _fix_escaped_chars(text: str) -> str:
        """Fix escaped newlines and tabs from LLM output."""
        if '\\n' in text:
            # Check if the whole thing is a quoted string
            if (text.startswith('"') and text.endswith('"')) or \
               (text.startswith("'") and text.endswith("'")):
                text = text[1:-1]
            text = text.replace('\\n', '\n')
        text = text.replace('\\t', '\t')
        text = text.replace('\\r', '')
        return text

    @staticmethod
    def _strip_meta_text(text: str) -> str:
        """Strip LLM meta-text preambles like 'Here's your response:'."""
        for pattern in META_TEXT_PATTERNS:
            text = re.sub(pattern, '', text, count=1, flags=re.IGNORECASE | re.MULTILINE)
        # Clean up any leading/trailing whitespace or quotes left behind
        text = text.strip().strip('"\'').strip()
        return text

    @staticmethod
    def _strip_urls(text: str) -> str:
        """Remove URLs that the LLM may have hallucinated."""
        return re.sub(r'https?://[^\s\)]+', '', text).strip()

    @staticmethod
    def _validate_discord(text: str) -> Tuple[str, List[str]]:
        """Discord-specific validation and cleanup."""
        issues = []

        # Remove @everyone and @here
        if '@everyone' in text or '@here' in text:
            text = text.replace('@everyone', '[everyone]').replace('@here', '[here]')
            issues.append('Stripped @everyone/@here mentions')

        # Remove Discord user/role/channel mentions
        if re.search(r'<@[!&]?\d+>|<#\d+>', text):
            text = re.sub(r'<@!?\d+>', '[user]', text)
            text = re.sub(r'<@&\d+>', '[role]', text)
            text = re.sub(r'<#\d+>', '[channel]', text)
            issues.append('Stripped Discord mentions from output')

        # Check for unmatched markdown formatting
        bold_count = text.count('**')
        if bold_count % 2 != 0:
            # Remove the last unpaired **
            last_pos = text.rfind('**')
            text = text[:last_pos] + text[last_pos + 2:]
            issues.append('Fixed unmatched bold markdown')

        italic_count = text.count('*') - (text.count('**') * 2)
        # Only flag if truly unmatched (heuristic — not perfect)
        if italic_count % 2 != 0 and italic_count > 0:
            issues.append('Possibly unmatched italic markdown')

        return text, issues

    @staticmethod
    def _check_clickbait(text: str) -> Tuple[bool, List[str]]:
        """Check for clickbait/hype words."""
        text_lower = text.lower()
        found = []
        for word in CLICKBAIT_WORDS:
            if re.search(rf'\b{re.escape(word)}\b', text_lower):
                found.append(word)
        return (len(found) > 0, found)

    @staticmethod
    def _check_profanity(text: str, severity: str = 'moderate') -> Tuple[bool, List[str]]:
        """Check for profanity at the given severity level."""
        check_words = list(PROFANITY_MILD)
        if severity in ('moderate', 'severe'):
            check_words.extend(PROFANITY_MODERATE)
        if severity == 'severe':
            check_words.extend(PROFANITY_SEVERE)

        text_lower = text.lower()
        found = []
        for word in check_words:
            if re.search(rf'\b{re.escape(word)}\b', text_lower):
                found.append(word)
        return (len(found) > 0, found)

    @staticmethod
    def _count_emojis(text: str) -> int:
        """Count Unicode emojis in text."""
        return len(EMOJI_PATTERN.findall(text))

    @staticmethod
    def _trim_emojis(text: str, max_count: int) -> str:
        """Remove excess emojis, keeping only the first max_count."""
        found = list(EMOJI_PATTERN.finditer(text))
        if len(found) <= max_count:
            return text
        # Remove emojis beyond the limit (from the end)
        for match in reversed(found[max_count:]):
            text = text[:match.start()] + text[match.end():]
        return text.strip()

    @staticmethod
    def _check_hallucinations(
        text: str,
        feature: str,
        feature_patterns: List[str],
        original_prompt: str = '',
    ) -> List[str]:
        """
        Check for hallucinated content.

        For CVE feature: verifies any CVE IDs or CVSS scores in the output
        actually appeared in the original prompt.
        """
        issues = []

        # CVE-specific hallucination checks
        if feature == 'cve':
            # Extract CVE IDs from output and prompt
            output_cves = set(re.findall(r'CVE-\d{4}-\d{4,}', text, re.IGNORECASE))
            prompt_cves = set(re.findall(r'CVE-\d{4}-\d{4,}', original_prompt, re.IGNORECASE))
            hallucinated_cves = output_cves - prompt_cves
            if hallucinated_cves:
                issues.append(f'Hallucinated CVE IDs: {", ".join(hallucinated_cves)}')

            # Check for invented CVSS scores not in the prompt
            output_scores = set(re.findall(r'(\d+\.\d+)/10', text))
            prompt_scores = set(re.findall(r'(\d+\.\d+)/10', original_prompt))
            # Also check plain scores in prompt
            prompt_scores.update(re.findall(r'CVSS[:\s]*(\d+\.\d+)', original_prompt, re.IGNORECASE))
            hallucinated_scores = output_scores - prompt_scores
            if hallucinated_scores:
                issues.append(f'Potentially hallucinated CVSS scores: {", ".join(hallucinated_scores)}')

        # Apply feature-specific hallucination patterns
        # (These flag potential issues but don't cross-check against the prompt)
        for pattern in feature_patterns:
            if feature == 'cve' and pattern == r'CVE-\d{4}-\d{4,}':
                continue  # Already handled above with cross-checking
            if feature == 'cve' and 'CVSS' in pattern:
                continue  # Already handled above
            if re.search(pattern, text, re.IGNORECASE):
                issues.append(f'Possible hallucination pattern: {pattern}')

        return issues

    @staticmethod
    def _safe_trim(text: str, limit: int) -> str:
        """Trim text to limit at a word boundary, preserving sentence endings."""
        text = text.strip()
        if len(text) <= limit:
            return text

        truncated = text[:limit]

        # Try to end at a sentence boundary
        last_period = truncated.rfind('.')
        last_exclaim = truncated.rfind('!')
        last_question = truncated.rfind('?')
        last_sentence = max(last_period, last_exclaim, last_question)

        if last_sentence > limit * 0.6:
            return truncated[:last_sentence + 1].strip()

        # Fall back to word boundary
        last_space = truncated.rfind(' ')
        if last_space > limit * 0.7:
            return truncated[:last_space].rstrip() + '...'

        # Last resort: hard cut
        return truncated.rstrip() + '...'

    @staticmethod
    def _score_quality(text: str) -> int:
        """
        Score text quality from 1-10.

        Checks for: generic phrases, repetition, length, substance.
        """
        score = 10
        text_lower = text.lower()

        # Generic phrases: -1 each, max -3
        generic_count = sum(1 for p in GENERIC_PHRASES if p in text_lower)
        score -= min(generic_count, 3)

        # Word count checks
        words = text.split()
        word_count = len(words)
        if word_count < 5:
            score -= 3  # Too short to be useful
        elif word_count < 10:
            score -= 1  # Borderline

        # Repetition: unique word ratio
        if word_count > 0:
            unique_ratio = len(set(w.lower() for w in words)) / word_count
            if unique_ratio < 0.5:
                score -= 3  # Very repetitive
            elif unique_ratio < 0.7:
                score -= 1

        # All caps segments
        caps_words = sum(1 for w in words if w.isupper() and len(w) > 2)
        if caps_words > 3:
            score -= 1

        # Exclamation mark overuse
        exclaim_count = text.count('!')
        if exclaim_count > 3:
            score -= 2
        elif exclaim_count > 1:
            score -= 1

        return max(1, min(10, score))

    def _is_duplicate(self, text: str, feature: str, cache_size: int) -> bool:
        """Check if text is a duplicate of recent output for this feature."""
        cache = self._dedup_caches.get(feature, deque(maxlen=cache_size))
        normalized = self._normalize_for_dedup(text)

        for cached in cache:
            if normalized == cached:
                return True
            # Word overlap check: >80% = duplicate
            msg_words = set(normalized.split())
            cached_words = set(cached.split())
            if not msg_words or not cached_words:
                continue
            overlap = len(msg_words & cached_words) / max(len(msg_words), len(cached_words))
            if overlap > 0.8:
                return True

        return False

    def _add_to_dedup_cache(self, text: str, feature: str, cache_size: int):
        """Add text to the dedup cache for a feature."""
        if feature not in self._dedup_caches:
            self._dedup_caches[feature] = deque(maxlen=cache_size)
        self._dedup_caches[feature].append(self._normalize_for_dedup(text))

    @staticmethod
    def _normalize_for_dedup(text: str) -> str:
        """Normalize text for deduplication comparison."""
        normalized = text.lower()
        normalized = re.sub(r'#\w+', '', normalized)  # Strip hashtags
        normalized = EMOJI_PATTERN.sub('', normalized)  # Strip emojis
        normalized = re.sub(r'[^\w\s]', '', normalized)  # Strip punctuation
        normalized = re.sub(r'\s+', ' ', normalized).strip()
        return normalized
