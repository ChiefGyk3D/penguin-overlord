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
- This is a diverse community: members of a marginalized group using
  reclaimed slurs among THEMSELVES in a friendly register is in-group
  banter, not hate speech. Judge target and intent, not just the word.
  The same word aimed at someone with hostility IS hate speech.
- Public, famous, or business addresses (the White House, a company HQ,
  a venue) are NOT doxxing. Doxxing is exposing a PRIVATE individual's
  personal information without consent.
- DISCUSSING, quoting, or warning about slurs, hate symbols, or dog
  whistles (educational talk, moderation work, news) is not hate speech —
  distinguish USING a slur or code from MENTIONING it. Ham radio
  operators sign off with '73' and '88'; that 88 is not a hate code.
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


# Well-known public infrastructure IPs everyone pastes in tech chat
# (resolvers, quad-style anycast). Not anyone's personal information.
WELL_KNOWN_IPS = frozenset({
    '8.8.8.8', '8.8.4.4',            # Google DNS
    '1.1.1.1', '1.0.0.1',            # Cloudflare DNS
    '9.9.9.9', '149.112.112.112',    # Quad9
    '208.67.222.222', '208.67.220.220',  # OpenDNS
    '4.2.2.2', '4.2.2.1',            # Level3
})

# Discord markup whose payload is an ID, not PII: user/role mentions,
# channel links, custom emoji, timestamps. A pasted <@205412…> mention
# used to flag as pii_exposure.
_DISCORD_SYNTAX_RE = re.compile(
    r'<(?:@[!&]?|#|a?:\w+:|t:)\d+(?::[a-zA-Z])?>'
)


def strip_discord_syntax(text: str) -> str:
    """Remove Discord mention/emoji/channel/timestamp markup before regex
    scans — their embedded snowflake IDs are not personal information."""
    return _DISCORD_SYNTAX_RE.sub(' ', text)


def _is_public_ip(candidate: str) -> bool:
    """Only globally-routable, non-well-known IPs count as PII. Tech servers
    paste LAN and loopback addresses (192.168.x, 10.x, 127.0.0.1) and public
    resolvers (8.8.8.8, 1.1.1.1) constantly — flagging those buried the mod
    channel in pii_exposure false positives. Invalid dotted quads (an octet
    > 255) are rejected too."""
    if candidate in WELL_KNOWN_IPS:
        return False
    try:
        return ipaddress.ip_address(candidate).is_global
    except ValueError:
        return False


def pre_scan_pii(text: str) -> list:
    """Fast regex PII scan; returns the PII types found."""
    text = strip_discord_syntax(text)
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
    'S2': 'social_engineering',  # non-violent crimes: fraud/scams — labeled
                                 # so operators can mute via
                                 # MOD_IGNORED_CATEGORIES in scam-joke-heavy
                                 # security communities
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


def is_guard_model(model: str) -> bool:
    """Guard-style classifiers (llama-guard*, *guard*) answer in a fixed
    protocol and must be prompted with bare content only."""
    return 'guard' in (model or '').lower()


def _moderation_uses_guard_model() -> bool:
    from ai import config as ai_config
    return is_guard_model(ai_config.get_feature_config('moderation').model)


def _second_opinion_model() -> str:
    """Optional second-stage model (AI_MODERATION_SECOND_MODEL). Runs the
    rich template prompt on messages the primary called safe; only its
    verdicts in SECOND_OPINION_CATEGORIES count. Measured rationale: a
    bare-prompted guard model is precise but blind to context and coded
    hate (58.7% Vicomtech recall), while gemma3:12b on the template prompt
    caught 100% of golden-set hate with zero clean hate FPs — but its
    non-hate verdicts (violence on game vocab, spam on scam jokes) are
    noise, so those are ignored."""
    from ai.config import _env
    return _env('AI_MODERATION_SECOND_MODEL') or ''


def _second_opinion_categories() -> frozenset:
    # hate_speech AND harassment: gemma labels coded dehumanization
    # ("your kind always ruins...") harassment at 0.95, while its
    # rude-banter harassment FPs sit at ~0.75 — the confidence floor
    # separates them.
    from ai.config import _env
    raw = _env('AI_MODERATION_SECOND_CATEGORIES', 'hate_speech,harassment')
    return frozenset(c.strip().lower() for c in raw.split(',') if c.strip())


def _second_opinion_min_confidence() -> float:
    from ai.config import _env
    try:
        return float(_env('AI_MODERATION_SECOND_MIN_CONFIDENCE', '0.85'))
    except (TypeError, ValueError):
        return 0.85

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

        if _moderation_uses_guard_model():
            # Llama Guard's chat template wraps whatever we send in its own
            # classification task and assesses the ENTIRE user turn as the
            # conversation. Any metadata we add — username wrapper, channel
            # context, prior-flag notes, our instruction system prompt — is
            # classified as content, and context quoting a prior SSN or slur
            # poisons the verdict for an innocent message (measured live:
            # "Nigerian Prince" -> unsafe S7 with contaminated context, safe
            # bare). Guard models get the bare message and nothing else.
            prompt = safe_content
            system_prompt = None
        else:
            prompt = self._template_prompt(safe_content, username, channel_name,
                                           context_messages, infraction_count)
            system_prompt = MODERATION_SYSTEM_PROMPT

        raw = None
        try:
            raw = await self._manager.generate(
                feature='moderation', prompt=prompt,
                system_prompt=system_prompt,
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

        if result.is_safe:
            second = await self._second_opinion(
                safe_content, username, channel_name, context_messages,
                infraction_count,
            )
            if second is not None:
                return second
        return result

    @staticmethod
    def _template_prompt(safe_content: str, username: str, channel_name: str,
                         context_messages: list, infraction_count: int) -> str:
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
        return prompt

    async def _second_opinion(self, safe_content: str, username: str,
                              channel_name: str, context_messages: list,
                              infraction_count: int):
        """Optional second-stage pass on primary-safe messages: a template
        model with full context, whose verdict counts only for the
        configured categories (default hate_speech). Returns a
        ModerationResult to use instead, or None to keep the primary."""
        model = _second_opinion_model()
        if not model:
            return None
        if is_guard_model(model):
            # A guard model can't consume the template prompt (that's the
            # contamination bug this design avoids) — misconfiguration.
            logger.error('AI_MODERATION_SECOND_MODEL must be a template '
                         'model, not a guard model; ignoring %s', model)
            return None

        prompt = self._template_prompt(safe_content, username, channel_name,
                                       context_messages, infraction_count)
        try:
            raw = await self._manager.generate(
                feature='moderation', prompt=prompt,
                system_prompt=MODERATION_SYSTEM_PROMPT,
                raw=True, model=model,
            )
        except Exception as e:
            logger.error(f"Second-opinion generate failed: {type(e).__name__}")
            return None
        if raw is None:
            return None

        second = parse_moderation_response(raw)
        if (second.is_safe
                or second.category not in _second_opinion_categories()
                or second.confidence < _second_opinion_min_confidence()):
            return None
        second.reason = f"second opinion ({model}): {second.reason}"
        return second

    # ------------------------------------------------- context adjudication

    _ADJUDICATIONS = {
        'reclaimed_slur': (
            "You judge messages in a diverse, LGBTQ-friendly Discord "
            "community. Members of a marginalized group using reclaimed "
            "slurs among THEMSELVES in a friendly register is in-group "
            "banter. The same word aimed at someone with hostility, "
            "mockery, or exclusion is an attack. Judge target and intent "
            "from the message and context.\n"
            "Respond in EXACTLY this format:\n"
            "VERDICT: banter/attack/uncertain\n"
            "REASON: <one short sentence>",
            frozenset({'banter', 'attack', 'uncertain'}),
        ),
        'address': (
            "You judge whether a Discord message exposes a PRIVATE "
            "individual's real-world address (doxxing) or merely mentions "
            "a public, famous, business, government, or fictional address "
            "(the White House, a company HQ, a venue — not doxxing).\n"
            "Respond in EXACTLY this format:\n"
            "VERDICT: private/public/uncertain\n"
            "REASON: <one short sentence>",
            frozenset({'private', 'public', 'uncertain'}),
        ),
        'dogwhistle': (
            "A message in a ham-radio/tech Discord community matched a "
            "pattern that white supremacists use as a coded hate signal "
            "(ADL Hate on Display), but the same pattern has common benign "
            "readings. Decide from the message and context:\n"
            "- hateful: used as the coded hate signal (e.g. '88' as Heil "
            "Hitler, echo parentheses around a name or group)\n"
            "- benign: an innocent reading — ham radio operators sign off "
            "with '73' and '88' (best regards / love and kisses); years, "
            "prices, quantities, piano keys, frequencies\n"
            "- mention: DISCUSSING, quoting, or warning about the code "
            "itself (educational or moderation talk about dog whistles)\n"
            "Humor matters: jokes MOCKING nazis or extremists, and absurdist "
            "meme humor between friends, are benign or mention. 'Irony' that "
            "still functions as the signal — asserting the coded claim, or "
            "aimed at a group or person — is hateful. When a joke is "
            "genuinely ambiguous, answer uncertain.\n"
            "Respond in EXACTLY this format:\n"
            "VERDICT: hateful/benign/mention/uncertain\n"
            "REASON: <one short sentence>",
            frozenset({'hateful', 'benign', 'mention', 'uncertain'}),
        ),
    }

    async def adjudicate(self, kind: str, message_content: str, username: str,
                         context_messages: list = None, note: str = None) -> str:
        """Ask the context-capable second-stage model one focused question.

        Returns the verdict word, or 'uncertain' when no second model is
        configured, the model is down, or the answer doesn't parse —
        callers must FAIL OPEN (treat 'uncertain' as 'alert anyway')."""
        model = _second_opinion_model()
        if not model or is_guard_model(model):
            return 'uncertain'

        system_prompt, allowed = self._ADJUDICATIONS[kind]
        prompt = self._template_prompt(
            sanitize_input(message_content, max_length=1500),
            username, '', context_messages, 0,
        ).replace('respond in the required format', 'answer the question')
        if note:
            prompt += f"\nFlagged pattern(s): {sanitize_input(note, 200)}"

        try:
            raw = await self._manager.generate(
                feature='moderation', prompt=prompt,
                system_prompt=system_prompt, raw=True, model=model,
                max_tokens=80,
            )
        except Exception as e:
            logger.error(f"Adjudication ({kind}) failed: {type(e).__name__}")
            return 'uncertain'
        if not raw:
            return 'uncertain'
        match = re.search(r'VERDICT\s*:\s*(\w+)', raw, re.IGNORECASE)
        verdict = match.group(1).lower() if match else 'uncertain'
        return verdict if verdict in allowed else 'uncertain'


# ---------------------------------------------------------------------------
# Golden corpus & benchmarking
# ---------------------------------------------------------------------------

def load_golden_corpus() -> dict:
    """The labeled hate/clean corpus shipped with the bot (ai/moderation_golden.json).
    Used by the CI golden gate, the live-model pytest tier, and /mod benchmark."""
    import json
    from pathlib import Path
    path = Path(__file__).resolve().parents[1] / 'moderation_golden.json'
    return json.loads(path.read_text(encoding='utf-8'))


async def benchmark_golden(analyzer: 'ModerationAnalyzer', corpus: dict = None) -> dict:
    """Run the golden corpus through *analyzer* and summarize accuracy.

    Sequential on purpose: one live-model call per example.
    """
    corpus = corpus or load_golden_corpus()
    rows = []
    for label, cases in (('hate', corpus['hate']), ('clean', corpus['clean'])):
        for case in cases:
            result = await analyzer.analyze(case['text'], 'goldenset')
            rows.append({
                'label': label,
                'regex_tier': case.get('regex_must_catch', False),
                'flagged': not result.is_safe,
                'category': result.category,
                'confidence': result.confidence,
                'text': case['text'],
                'note': case['note'],
            })
    return summarize_benchmark(rows)


def summarize_benchmark(rows: list) -> dict:
    """Pure summary of benchmark rows (unit-testable without a model)."""
    hate = [r for r in rows if r['label'] == 'hate']
    model_tier = [r for r in hate if not r['regex_tier']]
    clean = [r for r in rows if r['label'] == 'clean']

    correct = sum(r['flagged'] for r in hate) + sum(not r['flagged'] for r in clean)
    return {
        'total': len(rows),
        'accuracy': correct / len(rows) if rows else 0.0,
        'hate_recall': sum(r['flagged'] for r in hate) / len(hate) if hate else 0.0,
        'model_recall': (sum(r['flagged'] for r in model_tier) / len(model_tier)
                         if model_tier else 1.0),
        'clean_fp_rate': sum(r['flagged'] for r in clean) / len(clean) if clean else 0.0,
        'misses': [r for r in hate if not r['flagged']],
        'false_positives': [r for r in clean if r['flagged']],
        'rows': rows,
    }
