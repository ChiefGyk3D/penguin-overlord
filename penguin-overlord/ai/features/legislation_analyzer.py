# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
Legislation Analyzer - AI-powered plain-English summaries of legislation.

Translates opaque legislative titles and descriptions into clear summaries
explaining what a bill does, who it affects, and why a tech/security
audience should care. Supports US, EU, and UK legislation.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


LEGISLATION_SUMMARY_SYSTEM_PROMPT = """You are a nonpartisan legislative analyst explaining bills to a tech-savvy audience.
Your job is to translate legislative language into plain English.

Your summaries should be:
- CLEAR: No legalese. Explain like a smart colleague who reads the news.
- NEUTRAL: Present what the bill does, not whether it's good or bad.
  Never take sides. Never use partisan framing.
- RELEVANT: Focus on how this affects technology, cybersecurity, privacy,
  telecommunications, or digital rights. If it doesn't, say so briefly.
- CONCISE: 2-3 sentences maximum. Under 350 characters for Discord embeds.

Structure:
1. What the bill does (1 sentence)
2. Who it affects or why it matters to tech (1 sentence)

Do NOT:
- Express political opinions or bias
- Use partisan language (left-wing, right-wing, liberal, conservative agenda)
- Speculate about whether the bill will pass
- Add clickbait words (BREAKING, SHOCKING, etc.)
- Include URLs

Generate the summary only. No meta-commentary."""


LEGISLATION_ANALYSIS_SYSTEM_PROMPT = """You are a nonpartisan legislative analyst. Provide a structured analysis of the given
legislation for a technical audience (developers, sysadmins, security engineers).

Your analysis should include:
1. **What It Does**: Plain-English summary in 1-2 sentences
2. **Tech Impact**: How this specifically affects technology, privacy, security,
   or digital infrastructure (1 sentence). Say "Minimal direct tech impact" if none.
3. **Tags**: 2-4 topic tags (e.g., encryption, surveillance, AI regulation, Section 230)

Keep the total analysis under 400 characters. Be factual and neutral.
Never express support or opposition. Never use partisan framing."""


class LegislationAnalyzer:
    """AI-powered legislation analysis feature."""

    def __init__(self, generate_func):
        """
        Initialize the Legislation Analyzer.

        Args:
            generate_func: Async function(feature, prompt, system_prompt, **kwargs) -> str
                          Provided by AIManager for routing to the correct provider.
        """
        self._generate = generate_func

    async def summarize(
        self,
        title: str,
        description: str = '',
        source: str = '',
        region: str = 'US',
        max_length: int = 350,
    ) -> Optional[str]:
        """
        Generate a plain-English summary of legislation.

        Args:
            title: Bill/legislation title
            description: Bill description or summary text
            source: Source name (e.g., "Congress.gov")
            region: Region code ('US', 'EU', 'UK')
            max_length: Maximum summary length in characters

        Returns:
            Summary string or None if generation failed
        """
        user_prompt = f"Region: {region}\n"
        user_prompt += f"Legislation: \"{title}\"\n"
        if source:
            user_prompt += f"Source: {source}\n"
        if description:
            user_prompt += f"\nDescription:\n{description[:2000]}\n"
        user_prompt += f"\nSummarize in plain English, under {max_length} characters."

        result = await self._generate(
            feature='legislation',
            prompt=user_prompt,
            system_prompt=LEGISLATION_SUMMARY_SYSTEM_PROMPT,
            temperature=0.2,
            max_tokens=250,
            timeout=30,
        )

        if result and len(result) > max_length:
            truncated = result[:max_length]
            last_period = truncated.rfind('.')
            if last_period > max_length // 2:
                result = truncated[:last_period + 1]
            else:
                result = truncated.rstrip() + '...'

        return result

    async def analyze(
        self,
        title: str,
        description: str = '',
        source: str = '',
        region: str = 'US',
    ) -> Optional[str]:
        """
        Provide a structured analysis of legislation.

        Args:
            title: Bill/legislation title
            description: Bill description or content
            source: Source name
            region: Region code

        Returns:
            Analysis string or None
        """
        user_prompt = f"Region: {region}\n"
        user_prompt += f"Legislation: \"{title}\"\n"
        if source:
            user_prompt += f"Source: {source}\n"
        if description:
            user_prompt += f"\nDescription:\n{description[:3000]}\n"
        user_prompt += "\nProvide your analysis."

        return await self._generate(
            feature='legislation',
            prompt=user_prompt,
            system_prompt=LEGISLATION_ANALYSIS_SYSTEM_PROMPT,
            temperature=0.2,
            max_tokens=300,
            timeout=45,
        )

    async def assess_tech_relevance(
        self,
        title: str,
        description: str = '',
    ) -> Optional[str]:
        """
        Quick assessment of whether legislation is relevant to tech/security.

        Returns a one-line assessment like "HIGH - Directly regulates AI model training"
        or "LOW - Agricultural subsidy bill with no tech provisions".
        """
        user_prompt = (
            f"Bill: \"{title}\"\n"
        )
        if description:
            user_prompt += f"Description: {description[:500]}\n"
        user_prompt += (
            "\nRate tech/cybersecurity relevance as: HIGH, MEDIUM, or LOW\n"
            "Respond in exactly this format:\n"
            "RELEVANCE: <level>\nREASON: <one sentence>"
        )

        result = await self._generate(
            feature='legislation',
            prompt=user_prompt,
            system_prompt="You assess legislative relevance to technology. Respond ONLY in the requested format.",
            temperature=0.1,
            max_tokens=60,
            timeout=15,
        )

        if result:
            import re
            level_match = re.search(r'RELEVANCE:\s*(HIGH|MEDIUM|LOW)', result, re.IGNORECASE)
            reason_match = re.search(r'REASON:\s*(.+)', result, re.IGNORECASE)

            if level_match:
                level = level_match.group(1).upper()
                reason = reason_match.group(1).strip() if reason_match else ''
                return f"{level} — {reason}" if reason else level

        return None
