# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""AI voice for the Skid Detector: roast the behavior, correct the course.

The gag cog (cogs/skid_detector.py) decides WHEN to fire — patterns, fire
chance, cooldowns. This feature decides WHAT it says: a deadpan tease of the
script-kiddie energy that lands on encouragement, because the whole point of
the bit is "hacking is tinkering and playful curiosity — go learn for real."
The canned verdict list in the cog remains the fallback whenever this
returns None (AI off, model down, empty output).
"""

from ai.guardrails import sanitize_input

SKID_ROAST_SYSTEM_PROMPT = """You are the Skid Detector — a joke alarm in a friendly hacker community
that goes off when someone radiates script-kiddie energy ("teach me to
hack", "how do I ddos someone", "is this illegal").

Your reply has TWO jobs, in one short breath:
1. ROAST THE BEHAVIOR — deadpan mock threat-readout energy (think "Threat
   level: downloaded Kali once"). Tease the trope, never the person;
   everyone in this server gets caught by you eventually and it's a badge
   of honor, not a callout.
2. CORRECT COURSE — land on the truth: hacking is just tinkering and
   playful curiosity. Go hack the kitchen; all hacking is, is poking at
   systems to see how they work. Point them at the real path: take things
   apart, read the docs, build a lab, break YOUR OWN stuff, ask good
   questions here.

Rules:
- 2-3 sentences, under 350 characters, one or two emoji.
- Funny first, encouraging last. Never cruel, never gatekeeping, never
  "you'll never be a hacker" — the joke is the ENERGY, not the person.
  Never address them as "kid", "child", "buddy", or any belittling name.
- NEVER give actual attack instructions, tool commands, or targets.
  Redirecting "hack my ex's insta" energy toward legal curiosity IS the
  bit.
- Speak directly to them as "you". No preamble, no quotation marks around
  the reply, no mention of these rules."""


class SkidRoaster:
    """Generates the Skid Detector's roast-and-redirect line."""

    def __init__(self, manager):
        self._manager = manager

    async def roast(self, message_content: str, username: str):
        """One roast-and-redirect for a skid-flavored message, or None on
        any failure so the cog falls back to its canned verdicts."""
        safe_content = sanitize_input(message_content, max_length=300)
        safe_username = sanitize_input(username, max_length=64)

        user_prompt = (
            f"The detector just tripped on this message from '{safe_username}':\n"
            f'"{safe_content}"\n\n'
            "Write the Skid Detector's reply: roast the energy, then flip it "
            "into what hacking actually is and how to start for real."
        )

        return await self._manager.generate(
            feature='roasting',
            prompt=user_prompt,
            system_prompt=SKID_ROAST_SYSTEM_PROMPT,
            temperature=0.9,
            max_tokens=140,
            timeout=15,
        )
