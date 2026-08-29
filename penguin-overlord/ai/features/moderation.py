# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Moderation analyzer: LLM classification plus the policy layer that
decides what may happen with a verdict.

Design stance (Phase 2 = alert-first):
- The LLM only ever *proposes*. The policy layer decides, and in dry-run
  (the default) the only output is an alert to the mod channel.
- hate_speech, doxxing, self_harm, and violence ALWAYS require a human —
  they are never auto-actioned, at any confidence, in any mode. These are
  exactly the harms where evidence must be preserved and a person paged.
- kick/ban proposals always require a human click.
- Moderation inference is local-only (enforced in ai/config.py — the
  Gemini fallback flag is ignored for this feature).
"""

import ipaddress
import logging
import re
from dataclasses import dataclass, field

from ai.guardrails import find_blocked_terms, sanitize_input

logger = logging.getLogger(__name__)


CATEGORIES = (
    'safe', 'harassment', 'hate_speech', 'sexual_content', 'violence',
    'self_harm', 'spam', 'misinformation', 'doxxing', 'pii_exposure',
    'social_engineering', 'raid', 'evasion', 'unknown',
)

# Never auto-actioned; a human is always paged with evidence preserved.
FORCED_REVIEW_CATEGORIES = frozenset({'hate_speech', 'doxxing', 'self_harm', 'violence'})

# Only ever executed by a moderator clicking a button.
HUMAN_ONLY_ACTIONS = frozenset({'kick', 'ban'})

# The only actions the bot may ever take on its own (Phase 3, opt-in per action).
AUTO_CAPABLE_ACTIONS = frozenset({'delete', 'timeout'})


@dataclass
class ModerationResult:
    is_safe: bool
    category: str
    confidence: float
    reason: str
    suggested_action: str  # none/warn/delete/mute/timeout/kick/ban/review
    pii_detected: list = field(default_factory=list)
    denylist_hit: bool = False
    raw_response: str = ''


@dataclass
class ModerationDecision:
    """What the policy layer allows for a given result."""
    alert: bool                 # post to the mod channel
    requires_human: bool        # decision buttons instead of auto-action
    auto_action: str            # 'none' | 'delete' | 'timeout' (only when allowed)
    reason: str


MODERATION_SYSTEM_PROMPT = """You are a Discord server content moderation assistant. Analyze the given
message for policy violations. Consider context — sarcasm, jokes, and tech banter
are generally acceptable. Focus on genuine harmful intent.

Categories (choose the MOST specific one):
- safe: No issues
- harassment: Targeting individuals with sustained hostile intent
- hate_speech: Discrimination, slurs, or dehumanization based on protected characteristics (race, ethnicity, religion — including antisemitism — gender, sexual orientation, disability). Includes coded language, dog whistles, and slur evasions (leetspeak, spacing, homoglyphs).
- sexual_content: Explicit sexual material or unsolicited sexual messages
- violence: Credible threats of violence, glorification of real-world violence, or instructions to harm
- self_harm: Content promoting, encouraging, or instructing self-harm or suicide
- spam: Commercial spam, unsolicited advertising, or bot-like behavior
- misinformation: Deliberately false claims presented as fact (especially health/safety)
- doxxing: Sharing or threatening to share someone's private information (real name, address, phone number, workplace, school, IP address, photos) WITHOUT their consent
- pii_exposure: Accidentally or carelessly posting personal identifiable information (own or others')
- social_engineering: Attempting to manipulate users into revealing credentials, clicking malicious links, or bypassing security
- raid: Coordinated disruptive behavior, mass spam, or organized trolling
- evasion: Attempting to bypass moderation (Unicode tricks, alt accounts)

Severity-based actions:
- none: Safe content
- warn: Minor issue, inform the user
- delete: Remove the message
- timeout: Timeout the user
- kick: Remove from server (always requires human approval)
- ban: Permanent ban (always requires human approval)
- review: Send to human moderators (when uncertain)

IMPORTANT GUIDELINES:
- Tech communities are informal. Linux distro jokes, friendly banter, and mild profanity are FINE.
- Hate speech and slurs are NOT banter — flag them even when phrased as a "joke",
  and watch for evasions written to dodge filters.
- Doxxing is ALWAYS high severity regardless of context.
- When genuinely uncertain, use 'review' rather than 'safe'.
- For kick/ban recommendations you must be highly confident (>0.85).
- Consider repeat-offender context when provided.

Respond in EXACTLY this format:
SAFE: true/false
CATEGORY: <category>
CONFIDENCE: <0.0-1.0>
REASON: <brief explanation>
ACTION: none/warn/delete/timeout/kick/ban/review
PII: <comma-separated list of PII types found, or 'none'>"""


# Regex heuristics for obvious PII (pre-LLM fast path, runs on every message)
PII_PATTERNS = {
    'email': re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'),
    # Digit guards: a phone must not be a slice of a longer digit run —
    # Discord snowflakes pasted in chat used to flag as phone numbers.
    'phone': re.compile(r'(?<![\d.])(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}(?![\d.])'),
    'ssn': re.compile(r'\b\d{3}-\d{2}-\d{4}\b'),
    'ip_address': re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b'),
    'credit_card': re.compile(r'\b(?:\d{4}[-\s]?){3}\d{4}\b'),
    'address': re.compile(
        r'\b\d{1,5}\s+\w+\s+(?:St|Street|Ave|Avenue|Blvd|Boulevard|Dr|Drive|Ln|Lane|Rd|Road|Ct|Court|Way|Pl|Place)\b',
        re.IGNORECASE,
    ),
}


def _is_public_ip(candidate: str) -> bool:
    """Only globally-routable IPs count as PII. Tech servers paste LAN and
    loopback addresses (192.168.x, 10.x, 127.0.0.1) constantly — flagging
    those buried the mod channel in pii_exposure false positives. Invalid
    dotted quads (an octet > 255) are rejected too."""
    try:
        return ipaddress.ip_address(candidate).is_global
    except ValueError:
        return False


def pre_scan_pii(text: str) -> list:
    """Fast regex PII scan; returns the PII types found."""
    found = []
    for name, pattern in PII_PATTERNS.items():
        if name == 'ip_address':
            if any(_is_public_ip(m.group(0)) for m in pattern.finditer(text)):
                found.append(name)
        elif pattern.search(text):
            found.append(name)
    return found


# Llama Guard hazard taxonomy (S-codes) -> our categories. Guard models
# ignore the instruction template and answer in their own fixed protocol:
# "safe", or "unsafe" followed by one or more S-codes. Codes without a
# sensible mapping stay 'unknown', which forces human review.
GUARD_CATEGORY_MAP = {
    'S1': 'violence',        # violent crimes
    'S3': 'sexual_content',  # sex-related crimes
    'S4': 'sexual_content',  # child sexual exploitation
    'S5': 'harassment',      # defamation
    'S7': 'doxxing',         # privacy
    'S9': 'violence',        # indiscriminate weapons
    'S10': 'hate_speech',
    'S11': 'self_harm',
    'S12': 'sexual_content',
    'S13': 'misinformation', # elections
}

# Guard models emit a verdict with no confidence score; treat their
# fixed-taxonomy verdicts as high- but not denylist-level confidence.
GUARD_VERDICT_CONFIDENCE = 0.85

_GUARD_UNSAFE_RE = re.compile(r'^unsafe\b[\s,]*((?:S\d{1,2}[\s,]*)*)$',
                              re.IGNORECASE)


def _parse_guard_response(raw: str):
    """Parse Llama Guard's native output. Returns None when the text is not
    guard-protocol, so the template parser can have a go at it."""
    text = raw.strip()
    if text.lower() == 'safe':
        return ModerationResult(True, 'safe', GUARD_VERDICT_CONFIDENCE,
                                'guard model verdict: safe', 'none',
                                [], False, raw)
    match = _GUARD_UNSAFE_RE.match(text)
    if match:
        codes = [c.upper() for c in re.findall(r'[sS]\d{1,2}', match.group(1) or '')]
        category = next(
            (GUARD_CATEGORY_MAP[c] for c in codes if c in GUARD_CATEGORY_MAP),
            'unknown',
        )
        reason = f"guard model verdict: unsafe ({', '.join(codes) or 'no code'})"
        return ModerationResult(False, category, GUARD_VERDICT_CONFIDENCE,
                                reason, 'review', [], False, raw)
    return None


def parse_moderation_response(raw: str) -> ModerationResult:
    """Parse a moderation verdict: Llama Guard's native protocol first, then
    the SAFE/CATEGORY/... instruction template. Malformed responses become
    'unknown' at 0 confidence with action 'review' — never silently safe."""
    if not raw:
        return ModerationResult(False, 'unknown', 0.0, 'empty model response', 'review')

    guard_result = _parse_guard_response(raw)
    if guard_result is not None:
        return guard_result

    def _field(name, default=''):
        match = re.search(rf'^{name}\s*:\s*(.+)$', raw, re.IGNORECASE | re.MULTILINE)
        return match.group(1).strip() if match else default

    safe_str = _field('SAFE').lower()
    category = _field('CATEGORY').lower().replace(' ', '_')
    reason = _field('REASON', 'no reason given')
    action = _field('ACTION', 'review').lower()
    pii_str = _field('PII', 'none').lower()

    try:
        confidence = min(1.0, max(0.0, float(_field('CONFIDENCE', '0'))))
    except ValueError:
        confidence = 0.0

    if category not in CATEGORIES:
        category = 'unknown'
    if action not in ('none', 'warn', 'delete', 'mute', 'timeout', 'kick', 'ban', 'review'):
        action = 'review'
    if action == 'mute':
        action = 'timeout'

    is_safe = safe_str == 'true' and category == 'safe'
    pii = [] if pii_str in ('none', '') else [p.strip() for p in pii_str.split(',') if p.strip()]

    if safe_str not in ('true', 'false'):
        # Template not followed — treat as unparseable, force review
        return ModerationResult(False, 'unknown', 0.0, f'unparseable response: {raw[:100]}', 'review', pii, False, raw)

    return ModerationResult(is_safe, category, confidence, reason, action, pii, False, raw)


def decide(result: ModerationResult, *, dry_run: bool, min_confidence: float,
           auto_delete: bool, auto_timeout: bool,
           alert_min_confidence: float = 0.0) -> ModerationDecision:
    """Policy layer: what is allowed to happen with this verdict."""
    if result.is_safe and not result.denylist_hit and not result.pii_detected:
        return ModerationDecision(False, False, 'none', 'safe')

    # Anything non-safe is at least worth an alert
    if result.category in FORCED_REVIEW_CATEGORIES or result.denylist_hit:
        return ModerationDecision(True, True, 'none', 'forced human review category')

    # Operators can raise a floor for the remaining (non-forced) alerts to
    # cut low-confidence noise; forced-review categories are never muted.
    if result.confidence < alert_min_confidence:
        return ModerationDecision(False, False, 'none', 'below alert confidence floor')

    if result.suggested_action in HUMAN_ONLY_ACTIONS:
        return ModerationDecision(True, True, 'none', 'kick/ban always needs a human')

    if result.suggested_action == 'review' or result.category == 'unknown':
        return ModerationDecision(True, True, 'none', 'model requested review')

    if dry_run:
        return ModerationDecision(True, False, 'none', 'dry-run: alert only')

    if result.confidence < min_confidence:
        return ModerationDecision(True, False, 'none', 'below confidence threshold')

    if result.suggested_action == 'delete' and auto_delete:
        return ModerationDecision(True, False, 'delete', 'auto-delete enabled')
    if result.suggested_action == 'timeout' and auto_timeout:
        return ModerationDecision(True, False, 'timeout', 'auto-timeout enabled')

    return ModerationDecision(True, False, 'none', f"action '{result.suggested_action}' not enabled for automation")


class ModerationAnalyzer:
    """LLM-backed message analysis. The cog owns scoping and rate limits."""

    def __init__(self, manager):
        self._manager = manager

    async def analyze(self, message_content: str, username: str,
                      channel_name: str = '', context_messages: list = None,
                      infraction_count: int = 0) -> ModerationResult:
        """Analyze one message. Never raises; returns a ModerationResult."""
        # Hard deny-list first: a slur in chat is a hate_speech alert even if
        # the model is down or waffles.
        denylist_hits = find_blocked_terms(message_content)

        safe_content = sanitize_input(message_content, max_length=1500)
        prompt_parts = [f"Message from '{sanitize_input(username, 64)}'"]
        if channel_name:
            prompt_parts.append(f"in #{sanitize_input(channel_name, 64)}")
        prompt = ' '.join(prompt_parts) + f':\n"""\n{safe_content}\n"""\n'

        if infraction_count:
            prompt += f"\nNote: this user has {infraction_count} prior flagged message(s) in the last 30 days.\n"
        if context_messages:
            joined = '\n'.join(
                f"- {sanitize_input(m, 200)}" for m in context_messages[-5:]
            )
            prompt += f"\nRecent channel context (oldest first):\n{joined}\n"
        prompt += "\nAnalyze the message (not the context) and respond in the required format."

        raw = None
        try:
            raw = await self._manager.generate(
                feature='moderation', prompt=prompt,
                system_prompt=MODERATION_SYSTEM_PROMPT,
                raw=True,
            )
        except Exception as e:
            logger.error(f"Moderation generate failed: {type(e).__name__}")

        if raw is None:
            if denylist_hits:
                return ModerationResult(
                    False, 'hate_speech', 0.99,
                    'blocklisted term detected (regex; model unavailable)',
                    'review', [], True, '',
                )
            # Model unavailable and no regex hit: nothing to report
            return ModerationResult(True, 'safe', 0.0, 'model unavailable', 'none')

        result = parse_moderation_response(raw)
        if denylist_hits:
            result.denylist_hit = True
            result.is_safe = False
            if result.category in ('safe', 'unknown'):
                result.category = 'hate_speech'
                result.reason = 'blocklisted term detected (regex)'
            result.confidence = max(result.confidence, 0.95)
        return result
