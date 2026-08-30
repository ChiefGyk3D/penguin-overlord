# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Community profiles — what counts as normal talk here.

A general-purpose Discord and a cybersecurity Discord disagree about what
an IP address means, what "how would you doxx someone" means, and whether
a lockpicking video is a red flag. Tuning one prompt to satisfy both fills
one community's moderator channel with noise.

Profiles **compose**, because real communities are several things at once:
`MOD_PROFILE=cybersecurity,hobbyist` is a security server that also talks
about locksport and range days. Merging takes the union of what each
profile considers ordinary, the union of their context checks, and the most
permissive threshold per category — every listed topic is normal here.

Each profile carries:

1. **What is ordinary here** — bullets injected into the model's system
   prompt. The strongest, cheapest lever: telling the model what this room
   is about fixes more false positives than any threshold.
2. **Alert thresholds per category**, so a category that is mostly shop
   talk needs more confidence before it pages a human.
3. **Context checks** — which second-stage adjudications earn their model
   call in this community.

What no profile may do is relax hate speech, harassment, self-harm, or
sexual-content handling. `PROTECTED_FLOORS` is enforced at build time, and
`DIVERSITY_FLOOR` is appended to every composed context: a community being
technical does not make slurs aimed at its members more acceptable. A
server that is openly LGBTQ+ and diverse needs that floor held *while* the
technical noise around it is turned down — those are not in tension, and
the prompt says so explicitly.
"""

from dataclasses import dataclass, field

# Thresholds a profile can never raise. Hate speech and harassment protect
# people; the rest are life-safety.
PROTECTED_FLOORS = {
    'hate_speech': 0.0,
    'harassment': 0.0,
    'self_harm': 0.0,
    'sexual_content': 0.0,
}

# Appended to every non-empty composed context, once, regardless of how many
# profiles are combined.
DIVERSITY_FLOOR = (
    "This community is openly LGBTQ+ and diverse. Hate speech, slurs aimed "
    "at people, dehumanisation, and harassment are judged NO less strictly "
    "here than anywhere else — the topics above being on-topic does not "
    "soften that in any way."
)

_PREAMBLE = (
    "COMMUNITY CONTEXT: this community covers {summary}. Its members are "
    "enthusiasts and professionals in those areas. The following is "
    "ORDINARY, ON-TOPIC conversation here and is NOT a policy violation:"
)


@dataclass(frozen=True)
class CommunityProfile:
    name: str
    summary: str
    # Bullets describing ordinary conversation for this community.
    normal_here: tuple = ()
    # What still counts as a violation despite the above.
    violation_note: str = ''
    # category -> minimum confidence before an alert is worth a human.
    thresholds: dict = field(default_factory=dict)
    # Second-stage adjudications enabled here.
    context_checks: frozenset = frozenset()

    @property
    def context(self) -> str:
        """The system-prompt block for this community."""
        if not self.normal_here:
            return ''
        bullets = '\n'.join(f'- {line}' for line in self.normal_here)
        parts = [_PREAMBLE.format(summary=self.summary), bullets]
        if self.violation_note:
            parts.append(
                f'What remains a violation is TARGETING: {self.violation_note}. '
                'The line is the target, not the topic.')
        parts.append(DIVERSITY_FLOOR)
        return '\n'.join(parts)

    def threshold_for(self, category: str, default: float) -> float:
        return self.thresholds.get(category, default)

    def enables(self, check: str) -> bool:
        return check in self.context_checks


_BASE_CHECKS = frozenset({'reclaimed_slur', 'address', 'dogwhistle'})

_GENERAL = CommunityProfile(
    name='general',
    summary='general-purpose conversation',
    context_checks=_BASE_CHECKS,
)

_CYBERSECURITY = CommunityProfile(
    name='cybersecurity',
    summary='cybersecurity, hacking, and homelab work',
    normal_here=(
        'IP addresses, domains, and hashes as indicators of compromise, C2 '
        'infrastructure, scan output, log excerpts, or lab equipment',
        'discussing how attacks work — doxxing, OSINT, phishing, social '
        'engineering, malware, exploits — as education, research, defence, '
        'news commentary, or war stories',
        'offensive-security tooling, CTF challenges, and authorised '
        'penetration testing',
    ),
    violation_note=(
        'applying a technique to a real, identifiable person without their '
        'consent, soliciting others to do it, or sharing a specific '
        "person's private information"
    ),
    thresholds={
        'pii_exposure': 0.9,
        'social_engineering': 0.9,
        'misinformation': 0.95,
        'spam': 0.9,
    },
    context_checks=_BASE_CHECKS | {'ip_address', 'security_topic'},
)

_HOBBYIST = CommunityProfile(
    name='hobbyist',
    summary=('hands-on hobbies — amateur radio, lockpicking, making, and '
             'lawful firearms ownership'),
    normal_here=(
        'locksport, physical-security research, and lock and safe mechanics',
        'lawful firearms ownership: collecting, maintenance, range days, '
        'competition, and hardware discussion',
        "amateur radio and electronics, where operators sign off with '73' "
        "and '88'",
    ),
    violation_note=('threatening a person or place, planning harm, or '
                    'instructions intended to hurt someone specific'),
    thresholds={'violence': 0.9, 'misinformation': 0.95},
    context_checks=_BASE_CHECKS | {'weapons_hobby'},
)

PROFILES = {p.name: p for p in (_GENERAL, _CYBERSECURITY, _HOBBYIST)}
DEFAULT_PROFILE = 'general'


def compose(profiles: list) -> CommunityProfile:
    """Merge profiles into one: every listed topic is normal here.

    Thresholds take the highest (most permissive) value any profile sets,
    checks are unioned, and the shared bullets are concatenated in the order
    given so the prompt reads as one description of one community.
    """
    profiles = [p for p in profiles if p is not None]
    if not profiles:
        return PROFILES[DEFAULT_PROFILE]
    if len(profiles) == 1:
        return profiles[0]

    thresholds: dict = {}
    for profile in profiles:
        for category, value in profile.thresholds.items():
            thresholds[category] = max(thresholds.get(category, 0.0), value)

    summaries = [p.summary for p in profiles if p.normal_here]
    normal_here, seen = [], set()
    for profile in profiles:
        for line in profile.normal_here:
            if line not in seen:
                seen.add(line)
                normal_here.append(line)
    notes = [p.violation_note for p in profiles if p.violation_note]

    return CommunityProfile(
        name='+'.join(p.name for p in profiles),
        summary='; and '.join(summaries) if summaries else
                PROFILES[DEFAULT_PROFILE].summary,
        normal_here=tuple(normal_here),
        violation_note='; '.join(notes),
        thresholds=thresholds,
        context_checks=frozenset().union(*(p.context_checks for p in profiles)),
    )


def get_profile(spec: str) -> CommunityProfile:
    """Resolve `MOD_PROFILE` — one name or a comma-separated combination.

    Unknown names are skipped rather than fatal: a typo in one env var must
    not take moderation offline, and a partially-recognised list still gives
    the community most of what it asked for.
    """
    names = [n.strip().lower() for n in (spec or '').split(',') if n.strip()]
    resolved = [PROFILES[n] for n in names if n in PROFILES]
    if not resolved:
        return PROFILES[DEFAULT_PROFILE]

    merged = compose(resolved)
    unsafe = {c: t for c, t in merged.thresholds.items()
              if c in PROTECTED_FLOORS and t > PROTECTED_FLOORS[c]}
    if unsafe:
        # Belt and braces: no shipped profile does this, and a future one
        # that tries gets clamped rather than quietly weakening a floor.
        clamped = dict(merged.thresholds)
        for category in unsafe:
            clamped[category] = PROTECTED_FLOORS[category]
        return CommunityProfile(
            name=merged.name, summary=merged.summary,
            normal_here=merged.normal_here, violation_note=merged.violation_note,
            thresholds=clamped, context_checks=merged.context_checks,
        )
    return merged
