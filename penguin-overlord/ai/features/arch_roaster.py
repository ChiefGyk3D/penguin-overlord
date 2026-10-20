# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Distro roasters - AI-powered Arch and NixOS roasting.

Generates contextual, witty roasts based on what the user said. The caller
(arch_banter cog) always keeps the static joke lists as the fallback, so a
failed or guardrail-blocked generation costs nothing.

The wording (system prompt, angles, formats, exemplars, banned phrases,
fallback jokes) lives in data files: see roast_loader.py and
docs/features/ROAST_DATA.md. This module owns structure only: per call it
samples a few angles and a format, avoiding what it used recently, injects
the last accepted roasts as an "avoid these" block, and rejects output that
repeats one of them. Ollama still writes the roast.
"""

import logging
import random
from collections import deque
from dataclasses import dataclass, field
from typing import Optional

from ai.features import roast_text
from ai.features.roast_loader import RoastData, RoastFormat, load_roast_data, render_system_prompt
from ai.guardrails import sanitize_input

logger = logging.getLogger(__name__)

# Raw templates (placeholders unfilled), kept as module constants for callers
# that only want the shipped persona text.
ARCH_ROAST_SYSTEM_PROMPT = load_roast_data('arch').system_prompt
NIX_ROAST_SYSTEM_PROMPT = load_roast_data('nix').system_prompt

_DISTRO_NAMES = {'arch': 'Arch Linux', 'nix': 'NixOS'}

RETRY_TEMPERATURE_CAP = 1.3
_AVOID_ENTRY_CHARS = 200


@dataclass(frozen=True)
class RoastSettings:
    """Knobs. Defaults reproduce the pre-rotation behaviour (0.85 / 80)."""

    angles_per_call: int = 2
    angle_window: int = 6          # avoid angles used in the last N calls
    ring_size: int = 12            # accepted roasts remembered per distro
    dup_threshold: float = 0.6     # token Jaccard at or above this is a duplicate
    temperature: float = 0.85
    max_tokens: int = 80
    retry_temperature_step: float = 0.15
    exemplars_per_call: int = 3
    timeout: float = 15

    @classmethod
    def from_banter(cls, banter) -> 'RoastSettings':
        """Build from the typed `banter` config section."""
        return cls(
            angles_per_call=banter.roast_angles_per_call,
            angle_window=banter.roast_angle_window,
            ring_size=banter.roast_recent,
            dup_threshold=banter.roast_dup_threshold,
            temperature=banter.roast_temperature,
            max_tokens=banter.roast_max_tokens,
        )


@dataclass
class RoastResult:
    """One roast() outcome with the structure that produced it."""

    text: Optional[str]
    angles: list = field(default_factory=list)      # angle texts used
    format: str = ''
    attempts: int = 0
    reasons: list = field(default_factory=list)     # why attempts were rejected


class ArchRoaster:
    """AI-powered distro roaster. Arch by default; `distro='nix'` for NixOS."""

    def __init__(self, manager, distro: str = 'arch', *, data: Optional[RoastData] = None,
                 settings: Optional[RoastSettings] = None, rng: Optional[random.Random] = None):
        if distro not in _DISTRO_NAMES:
            raise KeyError(distro)
        self._manager = manager
        self._distro_name = _DISTRO_NAMES[distro]
        self._data = data if data is not None else load_roast_data(distro)
        self._settings = settings or RoastSettings()
        self._rng = rng or random.Random()
        self._angle_history = deque(maxlen=max(self._settings.angle_window, 0))
        self._last_format: Optional[str] = None
        self._ring = deque(maxlen=max(self._settings.ring_size, 0))

    # -- rotation ---------------------------------------------------------

    def pick_angles(self) -> list:
        """Indices of the angles for one call.

        Prefers angles absent from the last `angle_window` calls. If the pool
        is too small to honour the window, the least recently used angles
        fill the gap, so picks stay distinct within a call and usage balanced.
        """
        total = len(self._data.angles)
        want = min(max(self._settings.angles_per_call, 1), total)
        recent = list(self._angle_history)
        used = set().union(*recent) if recent else set()
        fresh = [i for i in range(total) if i not in used]
        self._rng.shuffle(fresh)
        chosen = fresh[:want]
        if len(chosen) < want:
            last_seen = {}
            for position, call in enumerate(recent):
                for i in call:
                    last_seen[i] = position
            stale = sorted(used, key=lambda i: last_seen[i])
            # shuffle equal-age candidates so ties are not index-ordered
            stale = sorted(self._shuffled(stale), key=lambda i: last_seen[i])
            chosen += stale[:want - len(chosen)]
        if self._angle_history.maxlen:
            self._angle_history.append(tuple(chosen))
        return chosen

    def _shuffled(self, items):
        items = list(items)
        self._rng.shuffle(items)
        return items

    def pick_format(self) -> RoastFormat:
        """A format, avoiding the one used last when there is a choice."""
        formats = self._data.formats
        options = [f for f in formats if f.name != self._last_format] or list(formats)
        chosen = self._rng.choice(options)
        self._last_format = chosen.name
        return chosen

    # -- prompt -----------------------------------------------------------

    def _avoid_lines(self) -> list:
        return [sanitize_input(entry, max_length=_AVOID_ENTRY_CHARS) for entry in self._ring]

    def _exemplars(self) -> list:
        pool = list(self._data.exemplars)
        count = min(self._settings.exemplars_per_call, len(pool))
        return self._rng.sample(pool, count) if count > 0 else []

    # -- review -----------------------------------------------------------

    def _review(self, text: str):
        """(accepted text or None, rejection reason or None)."""
        if roast_text.EM_DASH in text:
            return None, 'em_dash'
        lowered = text.casefold()
        if any(phrase.casefold() in lowered for phrase in self._data.banned_phrases):
            return None, 'banned_phrase'
        text = roast_text.trim_extra_emoji(text)       # repair, never reject, on emoji count
        words = roast_text.tokens(text)
        if any(roast_text.jaccard(words, roast_text.tokens(old)) >= self._settings.dup_threshold
               for old in self._ring):
            return None, 'duplicate'
        return text, None

    # -- main -------------------------------------------------------------

    async def roast(self, message_content: str, username: str, context: str = None):
        """Generate a contextual distro roast, or None on any failure."""
        return (await self.generate(message_content, username, context)).text

    async def generate(self, message_content: str, username: str, context: str = None) -> RoastResult:
        """Like roast(), but reports the angles, format and rejections used."""
        safe_content = sanitize_input(message_content, max_length=300)
        safe_username = sanitize_input(username, max_length=64)

        angle_ids = self.pick_angles()
        fmt = self.pick_format()
        limit = fmt.max_length or self._data.max_length
        system_prompt = render_system_prompt(
            self._data, [self._data.angles[i] for i in angle_ids], fmt,
            self._avoid_lines(), self._exemplars())

        user_prompt = f"User '{safe_username}' said: \"{safe_content}\"\n\n"
        if context:
            user_prompt += f"Context: {sanitize_input(context, max_length=100)}\n\n"
        user_prompt += (self._data.user_prompt_tail
                        .replace('{distro_name}', self._distro_name)
                        .replace('{max_length}', str(limit)))

        result = RoastResult(None, [self._data.angles[i] for i in angle_ids], fmt.name)
        temperature = self._settings.temperature
        for attempt in (1, 2):
            result.attempts = attempt
            raw = await self._manager.generate(
                feature='roasting',
                prompt=user_prompt,
                system_prompt=system_prompt,
                temperature=temperature,
                max_tokens=self._settings.max_tokens,
                timeout=self._settings.timeout,
            )
            if not raw:
                return result          # the manager failed; repeating will not help
            text, reason = self._review(raw)
            if text is not None:
                if self._ring.maxlen:
                    self._ring.append(text)
                result.text = text
                return result
            result.reasons.append(reason)
            logger.info('Roast rejected (%s), attempt %d', reason, attempt)
            temperature = min(temperature + self._settings.retry_temperature_step,
                              RETRY_TEMPERATURE_CAP)
        return result
