# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
News Analyzer - AI-powered article summarization and analysis.

Provides intelligent summaries of news articles, tech news, cybersecurity
news, and legislation. Can identify key takeaways, sentiment, and relevance.
"""

import logging
from typing import Optional, Dict, List

logger = logging.getLogger(__name__)


NEWS_SUMMARY_SYSTEM_PROMPT = """You are a sharp, concise news analyst. Your job is to summarize news articles
for a tech-savvy Discord community. Think of yourself as a well-informed colleague
giving a quick briefing.

Your summaries should be:
- CONCISE: 2-3 sentences maximum. Get to the point.
- INFORMATIVE: Cover the key facts — who, what, why it matters.
- CONTEXTUAL: Explain why a tech/security audience should care.
- OBJECTIVE: Present facts, not opinions. No editorializing.
- PLAIN LANGUAGE: No jargon soup. If you must use a technical term, it should be
  one your audience already knows.

Do NOT:
- Start with "This article discusses..." or "According to..."
- Use clickbait words (BREAKING, SHOCKING, INSANE, etc.)
- Add your own speculation beyond what the article says
- Include URLs or references — just the summary
- Use more than one emoji

Generate the summary only. No meta-commentary."""


NEWS_ANALYSIS_SYSTEM_PROMPT = """You are an expert news analyst specializing in technology, cybersecurity,
and policy. Provide a structured analysis of the given article.

Your analysis should include:
1. **Key Points**: 2-3 bullet points of the most important facts
2. **Impact**: Who is affected and how (1 sentence)
3. **Action Items**: What the reader should do, if anything (1 sentence)

Keep the total analysis under 300 characters for Discord embed compatibility.
Be direct and actionable. No fluff."""


CYBERSECURITY_NEWS_SYSTEM_PROMPT = """You are a cybersecurity expert analyst providing threat intelligence briefings.
Analyze the given cybersecurity news for a technical audience (sysadmins, security engineers, developers).

Your briefing should include:
1. **Threat Summary**: What happened in 1-2 sentences
2. **Severity**: Rate as CRITICAL / HIGH / MEDIUM / LOW with brief justification
3. **Affected Systems**: What platforms/software are impacted
4. **Recommended Action**: Specific steps to mitigate (patch, block, monitor, etc.)

Keep under 400 characters. Be specific and actionable. Skip the FUD."""


class NewsAnalyzer:
    """AI-powered news analysis and summarization feature."""

    def __init__(self, generate_func):
        """
        Initialize the News Analyzer.

        Args:
            generate_func: Async function(feature, prompt, system_prompt, **kwargs) -> str
                          Provided by AIManager for routing to the correct provider.
        """
        self._generate = generate_func

    async def summarize(
        self,
        title: str,
        content: str,
        source: str = '',
        max_length: int = 280,
    ) -> Optional[str]:
        """
        Generate a concise summary of a news article.

        Args:
            title: Article title
            content: Article content/description (can be truncated)
            source: Source name (e.g., "Ars Technica")
            max_length: Maximum summary length in characters

        Returns:
            Summary string or None if generation failed
        """
        user_prompt = f"Article title: \"{title}\"\n"
        if source:
            user_prompt += f"Source: {source}\n"
        user_prompt += f"\nContent:\n{content[:2000]}\n\n"
        user_prompt += f"Summarize this article in under {max_length} characters."

        result = await self._generate(
            feature='news',
            prompt=user_prompt,
            system_prompt=NEWS_SUMMARY_SYSTEM_PROMPT,
            temperature=0.3,
            max_tokens=200,
            timeout=30,
        )

        if result and len(result) > max_length:
            # Truncate at last sentence boundary
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
        content: str,
        source: str = '',
        category: str = 'technology',
    ) -> Optional[str]:
        """
        Provide a structured analysis of a news article.

        Args:
            title: Article title
            content: Article content/description
            source: Source name
            category: News category for context

        Returns:
            Analysis string or None
        """
        # Use cybersecurity prompt for security-related content
        system_prompt = NEWS_ANALYSIS_SYSTEM_PROMPT
        if category.lower() in ('cybersecurity', 'security', 'cve', 'vulnerability'):
            system_prompt = CYBERSECURITY_NEWS_SYSTEM_PROMPT

        user_prompt = f"Category: {category}\n"
        user_prompt += f"Article title: \"{title}\"\n"
        if source:
            user_prompt += f"Source: {source}\n"
        user_prompt += f"\nContent:\n{content[:3000]}\n\n"
        user_prompt += "Provide your analysis."

        return await self._generate(
            feature='news',
            prompt=user_prompt,
            system_prompt=system_prompt,
            temperature=0.2,
            max_tokens=300,
            timeout=45,
        )

    async def batch_summarize(
        self,
        articles: List[Dict[str, str]],
        max_per_article: int = 200,
    ) -> List[Optional[str]]:
        """
        Summarize multiple articles.

        Args:
            articles: List of dicts with 'title', 'content', and optional 'source'
            max_per_article: Max characters per summary

        Returns:
            List of summaries (None for failed ones)
        """
        import asyncio
        tasks = [
            self.summarize(
                title=article.get('title', ''),
                content=article.get('content', ''),
                source=article.get('source', ''),
                max_length=max_per_article,
            )
            for article in articles
        ]
        return await asyncio.gather(*tasks)

    async def extract_key_topics(
        self,
        title: str,
        content: str,
    ) -> Optional[List[str]]:
        """
        Extract key topics/tags from an article.

        Args:
            title: Article title
            content: Article content

        Returns:
            List of topic strings or None
        """
        user_prompt = (
            f"Article: \"{title}\"\n\n{content[:1500]}\n\n"
            "List 3-5 key topics as comma-separated tags (e.g., 'Linux, security, zero-day, kernel'). "
            "Tags only, no explanations."
        )

        result = await self._generate(
            feature='news',
            prompt=user_prompt,
            system_prompt="You extract key topics from articles. Respond with only comma-separated tags.",
            temperature=0.2,
            max_tokens=50,
            timeout=15,
        )

        if result:
            topics = [t.strip().strip('"\'') for t in result.split(',')]
            return [t for t in topics if t and len(t) < 50]

        return None
