# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Small text helpers shared by the roaster and the roast eval script.

Code does the counting and comparing; the model only writes prose. Nothing
here calls a model.
"""

import re

EM_DASH = '—'

# One emoji "cluster": a flag (two regional indicators) or a base symbol with
# optional variation selector / skin tone / keycap, joined by ZWJ.
_BASE = ('[\U0001F000-\U0001FAFF☀-➿⬀-⯿⌚-⏿'
         '‼⁉™ℹⓂ▪-◾⤴⤵〰〽㊗㊙]')
_MOD = '[️\U0001F3FB-\U0001F3FF⃣]*'
EMOJI_RE = re.compile(
    '[\U0001F1E6-\U0001F1FF]{2}|' + _BASE + _MOD + '(?:‍' + _BASE + _MOD + ')*')

_WORD_RE = re.compile(r"\w+(?:'\w+)*")


def tokens(text: str) -> set:
    """Normalised word set: lowercase, punctuation and emoji dropped."""
    return set(_WORD_RE.findall(text.lower()))


def token_list(text: str) -> list:
    """Normalised words in order (for n-grams)."""
    return _WORD_RE.findall(text.lower())


def jaccard(a: set, b: set) -> float:
    """Jaccard similarity of two sets; 0.0 when both are empty."""
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


def ngrams(words: list, n: int) -> list:
    return [tuple(words[i:i + n]) for i in range(len(words) - n + 1)]


def count_emoji(text: str) -> int:
    return len(EMOJI_RE.findall(text))


def trim_extra_emoji(text: str) -> str:
    """Keep the first emoji cluster and drop the rest; untouched if <= 1."""
    seen = 0

    def keep_first(match):
        nonlocal seen
        seen += 1
        return match.group(0) if seen == 1 else ''

    if count_emoji(text) <= 1:
        return text
    trimmed = EMOJI_RE.sub(keep_first, text)
    return re.sub(r'[ \t]{2,}', ' ', trimmed).strip()
