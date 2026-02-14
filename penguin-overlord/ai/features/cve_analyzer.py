# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
CVE Analyzer - AI-powered vulnerability analysis.

Provides intelligent analysis of CVEs (Common Vulnerabilities and Exposures),
including severity assessment, impact analysis, and actionable remediation
guidance for security teams.
"""

import logging
from typing import Optional, Dict

logger = logging.getLogger(__name__)


CVE_ANALYSIS_SYSTEM_PROMPT = """You are a senior cybersecurity analyst providing CVE intelligence briefings.
Your audience is system administrators, security engineers, and DevOps teams
who need to quickly assess whether a vulnerability affects them and what to do.

Your analysis should be:
- ACTIONABLE: What should the reader DO about this?
- SPECIFIC: Which systems, versions, and configurations are affected?
- PRIORITIZED: Help the reader understand urgency (patch now vs. schedule vs. monitor)
- CONCISE: Under 400 characters for Discord embed compatibility

Structure your response as:
**Severity**: CRITICAL/HIGH/MEDIUM/LOW
**Impact**: What an attacker can do
**Affected**: Specific products/versions
**Action**: What to do right now

No speculation. No FUD. Just the facts and the fix."""


CVE_SUMMARY_SYSTEM_PROMPT = """You are a cybersecurity expert. Summarize the given CVE in 2 sentences maximum.
First sentence: what the vulnerability is and what's affected.
Second sentence: severity and recommended action.
Keep under 250 characters. Be specific about affected software versions."""


class CVEAnalyzer:
    """AI-powered CVE analysis feature."""

    def __init__(self, generate_func):
        """
        Initialize the CVE Analyzer.

        Args:
            generate_func: Async function(feature, prompt, system_prompt, **kwargs) -> str
                          Provided by AIManager for routing to the correct provider.
        """
        self._generate = generate_func

    async def analyze(
        self,
        cve_id: str,
        description: str,
        cvss_score: Optional[float] = None,
        affected_products: Optional[str] = None,
        references: Optional[str] = None,
    ) -> Optional[str]:
        """
        Provide a structured analysis of a CVE.

        Args:
            cve_id: CVE identifier (e.g., CVE-2024-12345)
            description: CVE description from NVD or other source
            cvss_score: Optional CVSS score (0.0-10.0)
            affected_products: Optional affected product list
            references: Optional reference URLs or advisory text

        Returns:
            Analysis string or None if generation failed
        """
        user_prompt = f"CVE ID: {cve_id}\n"
        if cvss_score is not None:
            user_prompt += f"CVSS Score: {cvss_score}/10.0\n"
        if affected_products:
            user_prompt += f"Affected Products: {affected_products}\n"
        user_prompt += f"\nDescription:\n{description[:2000]}\n"
        if references:
            user_prompt += f"\nReferences:\n{references[:500]}\n"
        user_prompt += "\nProvide your analysis."

        return await self._generate(
            feature='cve',
            prompt=user_prompt,
            system_prompt=CVE_ANALYSIS_SYSTEM_PROMPT,
            temperature=0.1,  # Low creativity for security analysis
            max_tokens=300,
            timeout=30,
        )

    async def summarize(
        self,
        cve_id: str,
        description: str,
        cvss_score: Optional[float] = None,
    ) -> Optional[str]:
        """
        Generate a brief CVE summary for embed descriptions.

        Args:
            cve_id: CVE identifier
            description: CVE description
            cvss_score: Optional CVSS score

        Returns:
            Brief summary string or None
        """
        user_prompt = f"CVE: {cve_id}\n"
        if cvss_score is not None:
            user_prompt += f"CVSS: {cvss_score}\n"
        user_prompt += f"Description: {description[:1000]}\n\n"
        user_prompt += "Summarize in 2 sentences, under 250 characters."

        result = await self._generate(
            feature='cve',
            prompt=user_prompt,
            system_prompt=CVE_SUMMARY_SYSTEM_PROMPT,
            temperature=0.1,
            max_tokens=150,
            timeout=20,
        )

        if result and len(result) > 250:
            truncated = result[:250]
            last_period = truncated.rfind('.')
            if last_period > 100:
                result = truncated[:last_period + 1]
            else:
                result = truncated.rstrip() + '...'

        return result

    async def assess_severity(
        self,
        description: str,
        cvss_score: Optional[float] = None,
    ) -> Optional[Dict[str, str]]:
        """
        Quick severity assessment for a CVE.

        Returns a dict with 'level' (CRITICAL/HIGH/MEDIUM/LOW) and 'reason'.
        """
        user_prompt = f"CVE Description: {description[:500]}\n"
        if cvss_score is not None:
            user_prompt += f"CVSS Score: {cvss_score}\n"
        user_prompt += (
            "\nRate severity as one of: CRITICAL, HIGH, MEDIUM, LOW\n"
            "Respond in exactly this format:\n"
            "LEVEL: <level>\nREASON: <one sentence>"
        )

        result = await self._generate(
            feature='cve',
            prompt=user_prompt,
            system_prompt="You are a CVE severity assessor. Respond ONLY in the requested format.",
            temperature=0.1,
            max_tokens=60,
            timeout=15,
        )

        if result:
            import re
            level_match = re.search(r'LEVEL:\s*(CRITICAL|HIGH|MEDIUM|LOW)', result, re.IGNORECASE)
            reason_match = re.search(r'REASON:\s*(.+)', result, re.IGNORECASE)

            if level_match:
                return {
                    'level': level_match.group(1).upper(),
                    'reason': reason_match.group(1).strip() if reason_match else '',
                }

        return None
