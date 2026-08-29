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
from functools import lru_cache
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
# feature. Each term compiles to an "elastic" regex — every letter may repeat
# and short separator runs may sit between letters — anchored on both sides
# by an alphanumeric boundary. That catches the common evasions ("k i k e",
# "n1gg3r", "kiiiike", "gas the jews") while never matching inside an
# innocent word: the first live deployment showed the previous
# substring-in-normalized-text approach flagged "Nigeria", "viable", and
# "diabetes" as hate speech. Precision comes first here — an alert-only
# system lives on moderator trust, and embedded-in-word evasions are still
# in front of the LLM layer and human eyes.
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

# Allow up to a few separator characters between the letters of a term
# ("k i k e", "t-r-a-n-n-y") without letting a term span half a sentence.
_GAP = r'[\W_]{0,3}'
_BOUNDARY_START = r'(?<![0-9a-z])'
_BOUNDARY_END = r'(?![0-9a-z])'


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


# ---------------------------------------------------------------------------
# Context-dependent dog-whistle watchlist (ADL Hate on Display)
# ---------------------------------------------------------------------------
# These coded terms all have COMMON benign readings — ham radio operators
# sign off with "73 and 88" (love and kisses), 88 is a birth year, piano
# keys, a price. So a watchlist hit never auto-alerts: it forces LLM
# analysis plus a context adjudication distinguishing hateful use from
# benign use from MENTION (discussing or warning about the code itself).
# Unambiguous coded phrases belong in the deny-list, not here.
# Text-expressible entries curated from the ADL Hate on Display database
# (https://www.adl.org/resources/hate-symbols/search). Deliberately
# excluded: purely visual symbols, and bare numbers/acronyms too common in
# ordinary chat to survive even adjudication volume (12, 13, 14, 18, 23,
# 100%, H8, WP, ORION — a spacecraft in this community, "moon man" —
# space talk, "storm front" — weather talk; 'stormfront' one word kept).
_DOGWHISTLE_PATTERNS = (
    # numeric codes
    ('88', r'\b88\b'),
    ('14 words', r'\b(?:14|fourteen)\s*words\b'),
    ('14/88', r'\b(?:14\s*[/-]\s*88|8814)\b'),
    ('14/23', r'\b14\s*/\s*23\b'),
    ('23/16', r'\b(?:23\s*/\s*16|16\s*/\s*23)\b'),
    ('109 countries', r'\b109\s+countries\b'),
    ('13/52', r'\b13\s*/\s*(?:5[02]|90)\b'),
    ('33/6', r'\b33\s*/\s*6\b'),
    ('6mwe', r'\b6mwe\b'),
    # coded punctuation
    ('echo parentheses', r'\(\(\([^()]{1,60}\)\)\)'),
    # acronyms
    ('zog', r'\bzog\b'),
    ('wpww', r'\bwpww\b'),
    ('gtkrwn', r'\bgtkrwn\b'),
    ('hffh', r'\bhffh\b'),
    ('swp', r'\bswp\b'),
    ('klan acronym', r'\b(?:akia|ayak|kigy|klasp|itsub|kabark|lotie|ofof|fgrn)\b'),
    # slogans and phrases
    ('great replacement', r'\bgreat\s+replacement\b'),
    ('groyper', r'\bgroypers?\b'),
    ('day of the rope', r'\bday\s+of\s+the\s+rope\b'),
    ('blood and soil', r'\bblood\s+and\s+soil\b'),
    ('blood and honour', r'\bblood\s+(?:and|&)\s+honou?r\b'),
    ('blut und ehre', r'\bblut\s+und\s+ehre\b'),
    ('meine ehre heisst treue', r'\bmeine\s+ehre\s+heisst\s+treue\b'),
    ('sieg heil', r'\bsieg\s+heil\b'),
    ('rahowa', r'\brahowa\b'),
    ('kalergi', r'\bkalergi\b'),
    ('white genocide', r'\bwhite\s+genocide\b'),
    ('white power', r'\bwhite\s+power\b'),
    ('white lives matter', r'\bwhite\s+lives\s+matter\b'),
    ('you will not replace us', r'\b(?:jews|you)\s+will\s+not\s+replace\s+us\b'),
    ('anti-racist code word', r'\bcode\s*word\s+for\s+anti[-\s]?white\b'),
    ("it's okay to be white", r"\bit'?s\s+ok(?:ay)?\s+to\s+be\s+white\b"),
    ('love your race', r'\blove\s+your\s+race\b'),
    ('race mixing', r'\brace[-\s]mixing\b'),
    ('non silba sed anthar', r'\bnon\s+silba\b'),
    # antisemitic meme phrases
    ('goyim know', r'\bgoyim\s+know\b'),
    ('anudda shoah', r'\banudda\s+shoah\b'),
    ('muh holocaust', r'\bmuh\s+holocaust\b'),
    ('six gorillion', r'\b(?:six|6)\s+gorillion\b'),
    ('happy merchant', r'\bhappy\s+merchant\b'),
    ('we wuz kangz', r'\bwe\s+wuz\s+kang[sz]\b'),
    ('zyklon', r'\bzyklon\b'),
    ('moonman', r'\bmoonman\b'),
    # movement/gang identifiers plausible in text
    ('peckerwood', r'\bpeckerwoods?\b'),
    ('featherwood', r'\bfeatherwoods?\b'),
    ('crazy white boy', r'\bcrazy\s+white\s+boys?\b'),
    ('stormfront', r'\bstormfront\b'),
)

_compiled_dogwhistles = tuple(
    (name, re.compile(pattern, re.IGNORECASE)) for name, pattern in _DOGWHISTLE_PATTERNS
)


def _load_operator_dogwhistles() -> tuple:
    """Optional operator extension: one term per line in data/dogwhistles.txt,
    matched with word boundaries; # comments."""
    path = Path(resolve_data_dir()) / 'dogwhistles.txt'
    try:
        if path.exists():
            terms = []
            for line in path.read_text(encoding='utf-8').splitlines():
                line = line.strip().lower()
                if line and not line.startswith('#'):
                    terms.append((line, re.compile(
                        r'\b' + re.escape(line).replace(r'\ ', r'\s+') + r'\b',
                        re.IGNORECASE)))
            if terms:
                logger.info(f"Loaded {len(terms)} operator dog-whistle terms from {path}")
            return tuple(terms)
    except (OSError, re.error) as e:
        logger.error(f"Could not read operator dog-whistle list {path}: {e}")
    return ()


def find_dogwhistles(text: str) -> list:
    """Return names of context-dependent dog-whistle patterns found in
    *text* (empty list = none). A hit means 'adjudicate with context',
    never 'alert' — see the moderation cog."""
    if not text:
        return []
    hits = [name for name, pattern in _compiled_dogwhistles if pattern.search(text)]
    hits += [name for name, pattern in _load_operator_dogwhistles()
             if pattern.search(text)]
    return hits


def _normalize(text: str) -> str:
    """Aggressive normalization for the output dedup fingerprint (NOT used
    for deny-list matching): fold case/accents, map leetspeak, drop
    separators, collapse repeated letters."""
    text = unicodedata.normalize('NFKD', text)
    text = ''.join(c for c in text if not unicodedata.combining(c))
    text = text.lower().translate(_LEET_MAP)
    text = re.sub(r'[^a-z0-9]', '', text)
    text = re.sub(r'(.)\1{2,}', r'\1\1', text)  # coooool -> cool-ish
    return text


def _fold(text: str) -> str:
    """Case/accent folding only — keeps separators so boundaries survive."""
    text = unicodedata.normalize('NFKD', text)
    text = ''.join(c for c in text if not unicodedata.combining(c))
    return text.lower()


def _build_term_pattern(term: str):
    """Compile one deny-term into its elastic, boundary-anchored regex.

    Letter terms match against leet-folded text; each letter becomes its
    own 'x+' group, so doubled letters stay required ('heeb' needs two e's
    and can never match the h-e-b inside "the best") while separators are
    allowed inside them ("t-r-a-n-n-y"). Digit-bearing terms ('1488')
    match literally against the raw folded text — leet-mapping would turn
    the term itself into letters that alias innocent words ("viable").
    Returns (pattern, matches_leet_text).
    """
    if any(c.isdigit() for c in term):
        body = _GAP.join(re.escape(c) for c in term)
        return re.compile(_BOUNDARY_START + body + _BOUNDARY_END), False

    # One 'x+' group per letter (not per run): 'tranny' keeps requiring two
    # n-groups so 'heeb' can't match the single e in "the best", while
    # separators are still allowed inside doubled letters ("t-r-a-n-n-y").
    body = _GAP.join(f'{re.escape(char)}+' for char in term)
    # Allow a plural/verb 's' tail ("k1kes", "retards") within the boundary.
    tail = r'(?:' + _GAP + r's+)?'
    return re.compile(_BOUNDARY_START + body + tail + _BOUNDARY_END), True


@lru_cache(maxsize=32)
def _compiled_terms(terms: tuple):
    return [(term,) + _build_term_pattern(term) for term in terms]


def find_blocked_terms(text: str, extra_terms: tuple = None) -> list:
    """Return the deny-list terms found in *text* (empty list = clean)."""
    if not text:
        return []

    folded = _fold(text)
    leet = folded.translate(_LEET_MAP)

    terms = _DENY_TERMS + (extra_terms if extra_terms is not None else _load_operator_blocklist())
    hits = []
    for term, pattern, use_leet in _compiled_terms(terms):
        if pattern.search(leet if use_leet else folded):
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
