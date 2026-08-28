# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Guardrails for LLM input and output.

Input side: prompt-injection neutralization and mention stripping before
user text is interpolated into prompts.

Output side: artifact cleanup (think-tags, preambles, quoting), an emoji
cap, a dedup cache — and a hard deny-list that blocks slurs and hate terms
in ANY model output regardless of per-feature settings. The deny-list is
normalization-aware (leetspeak, separators, repeated letters) and can be
extended by operators via a blocklist.txt file in the data directory.

The deny-list is a backstop, not the moderation system: model output goes
to public channels with a user @mention attached, so a hard floor applies
to every feature, roasting included.
"""

import logging
import re
import unicodedata
from pathlib import Path

from utils.state import resolve_data_dir

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Input sanitization
# ---------------------------------------------------------------------------

_INJECTION_PATTERNS = [
    (re.compile(r'(?i)\b(?:ignore\s+(?:all\s+)?(?:previous|above|prior)\s+instructions?)\b'), '[filtered]'),
    (re.compile(r'(?i)\b(?:disregard\s+(?:all\s+)?(?:previous|above|prior)\s+(?:instructions?|prompts?))\b'), '[filtered]'),
    (re.compile(r'(?i)\b(?:you\s+are\s+now|act\s+as|pretend\s+(?:to\s+be|you\s+are))\b'), '[filtered]'),
    (re.compile(r'(?i)\b(?:system\s*(?:prompt|message|instruction))\s*:'), '[filtered]:'),
    (re.compile(r'(?i)<<\s*(?:SYS|SYSTEM|INST)\s*>>'), '[filtered]'),
]


def sanitize_input(text: str, max_length: int = 3000) -> str:
    """Sanitize user-provided text before interpolating it into a prompt."""
    if not text:
        return ''

    text = text[:max_length]
    # Strip control characters (keep newlines, tabs)
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)

    for pattern, replacement in _INJECTION_PATTERNS:
        text = pattern.sub(replacement, text)

    # Discord mentions never belong in prompts (or in echoed output)
    text = re.sub(r'<@!?\d+>', '[user]', text)
    text = re.sub(r'<@&\d+>', '[role]', text)
    text = re.sub(r'<#\d+>', '[channel]', text)

    return text.strip()


# ---------------------------------------------------------------------------
# Hard deny-list
# ---------------------------------------------------------------------------

# Severe slurs and hate terms that must never appear in bot output, in any
# feature. Matched against a normalized form (lowercased, leetspeak mapped,
# separators removed, repeated letters collapsed), so cheap evasions like
# "n1gg3r" or "k i k e" are caught too. False positives are acceptable here:
# a blocked output just falls back to non-AI behavior.
_DENY_TERMS = (
    # racial / ethnic
    'nigger', 'niger', 'nigga', 'coon', 'spic', 'wetback', 'chink', 'gook',
    'beaner', 'porchmonkey', 'junglebunny', 'raghead', 'towelhead', 'zipperhead',
    # antisemitic
    'kike', 'heeb', 'sheeny', 'yid', 'jewrat', 'holohoax', 'zog',
    # homophobic / transphobic
    'faggot', 'fagot', 'fag', 'dyke', 'tranny', 'shemale', 'trannie',
    # ableist (severe)
    'retard', 'retarded', 'mongoloid',
    # violent extremism catchphrases
    'gasthejews', 'killalljews', 'whitepower', '1488', 'heilhitler',
)

_LEET_MAP = str.maketrans({
    '0': 'o', '1': 'i', '3': 'e', '4': 'a', '5': 's', '7': 't', '8': 'b',
    '$': 's', '@': 'a', '!': 'i', '+': 't', '|': 'i',
})

# Terms that stay checked with word boundaries in the raw text instead of
# substring-matched in the collapsed form (too many innocent collisions:
# "fag" in "fagend", "yid" in "yiddish", ...)
_BOUNDARY_ONLY = {'fag', 'yid', 'zog', 'coon', 'spic', 'heeb'}


def _load_operator_blocklist() -> tuple:
    """Optional operator-extended blocklist: one term per line, # comments."""
    path = Path(resolve_data_dir()) / 'blocklist.txt'
    try:
        if path.exists():
            terms = []
            for line in path.read_text(encoding='utf-8').splitlines():
                line = line.strip().lower()
                if line and not line.startswith('#'):
                    terms.append(line)
            if terms:
                logger.info(f"Loaded {len(terms)} operator blocklist terms from {path}")
            return tuple(terms)
    except OSError as e:
        logger.error(f"Could not read operator blocklist {path}: {e}")
    return ()


def _normalize(text: str) -> str:
    """Normalize for deny-list matching: fold case/accents, map leetspeak,
    drop separators, collapse repeated letters."""
    text = unicodedata.normalize('NFKD', text)
    text = ''.join(c for c in text if not unicodedata.combining(c))
    text = text.lower().translate(_LEET_MAP)
    text = re.sub(r'[^a-z0-9]', '', text)
    text = re.sub(r'(.)\1{2,}', r'\1\1', text)  # coooool -> cool-ish
    return text


def find_blocked_terms(text: str, extra_terms: tuple = None) -> list:
    """Return the deny-list terms found in *text* (empty list = clean)."""
    if not text:
        return []

    hits = []
    lowered = text.lower()
    normalized = _normalize(text)
    collapsed = re.sub(r'(.)\1+', r'\1', normalized)  # full repeat collapse

    terms = _DENY_TERMS + (extra_terms if extra_terms is not None else _load_operator_blocklist())
    for term in terms:
        if term in _BOUNDARY_ONLY:
            if re.search(rf'\b{re.escape(term)}\b', lowered):
                hits.append(term)
            continue
        norm_term = _normalize(term)
        if not norm_term:
            continue
        if norm_term in normalized or re.sub(r'(.)\1+', r'\1', norm_term) in collapsed:
            hits.append(term)
    return hits


# ---------------------------------------------------------------------------
# Output cleanup
# ---------------------------------------------------------------------------

_THINK_TAG_RE = re.compile(r'<think>.*?</think>', re.DOTALL | re.IGNORECASE)
_PREAMBLE_RE = re.compile(
    r'^(?:sure[!,.]?|okay[!,.]?|here(?:\'s| is)[^:\n]*:|roast:|response:|answer:)\s*',
    re.IGNORECASE,
)
_EMOJI_RE = re.compile(
    '[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF❤️]',
)


def clean_output(text: str, max_length: int = 400, max_emoji: int = 2) -> str:
    """Strip common LLM artifacts from generated text."""
    if not text:
        return ''

    text = _THINK_TAG_RE.sub('', text)
    text = text.strip()

    # Unwrap a fully-quoted response
    if len(text) >= 2 and text[0] in '"\'' and text[-1] == text[0]:
        text = text[1:-1].strip()

    text = _PREAMBLE_RE.sub('', text).strip()

    # Never let the model @-mention anyone on its own
    text = re.sub(r'<@!?&?\d+>', '', text)
    text = text.replace('@everyone', 'everyone').replace('@here', 'here')

    # Cap emoji count (small models love confetti)
    emoji_seen = 0

    def _cap(match):
        nonlocal emoji_seen
        emoji_seen += 1
        return match.group(0) if emoji_seen <= max_emoji else ''

    text = _EMOJI_RE.sub(_cap, text)

    text = re.sub(r'[ \t]{2,}', ' ', text).strip()
    if len(text) > max_length:
        text = text[:max_length - 3].rstrip() + '...'
    return text


class Guardrails:
    """Combined output pipeline with per-instance dedup cache."""

    def __init__(self, dedup_cache_size: int = 20):
        self._recent_outputs = []
        self._dedup_cache_size = dedup_cache_size

    def check_output(self, text: str, max_length: int = 400,
                     max_emoji: int = 2, dedup: bool = True):
        """Clean and validate model output.

        Returns (ok, cleaned_text, issues). ok=False means the output must
        not be posted; the caller falls back to non-AI behavior.
        """
        issues = []
        cleaned = clean_output(text, max_length=max_length, max_emoji=max_emoji)

        if not cleaned or len(cleaned) < 3:
            issues.append('empty')
            return False, cleaned, issues

        blocked = find_blocked_terms(cleaned)
        if blocked:
            # Log the categories, never echo the matched slurs at info level
            logger.warning(f"Blocked model output: deny-list hit ({len(blocked)} term(s))")
            issues.append('deny-list')
            return False, '', issues

        if dedup:
            fingerprint = _normalize(cleaned)[:120]
            if fingerprint in self._recent_outputs:
                issues.append('duplicate')
                return False, cleaned, issues
            self._recent_outputs.append(fingerprint)
            if len(self._recent_outputs) > self._dedup_cache_size:
                self._recent_outputs.pop(0)

        return True, cleaned, issues
