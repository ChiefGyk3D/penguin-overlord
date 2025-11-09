# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
Base News Fetcher - Optimized RSS/feed fetching with caching and concurrency control.
"""

import logging
import aiohttp
import asyncio
import re
import json
import os
from datetime import datetime
from html import unescape
from html.parser import HTMLParser
from typing import Optional, Tuple, Dict, List
from collections import defaultdict

logger = logging.getLogger(__name__)


class HTMLStripper(HTMLParser):
    """Simple HTML stripper that removes all tags and keeps only text."""
    def __init__(self):
        super().__init__()
        self.reset()
        self.strict = False
        self.convert_charrefs = True
        self.text = []
    
    def handle_data(self, data):
        self.text.append(data)
    
    def get_text(self):
        return ''.join(self.text)


class OptimizedNewsFetcher:
    """Base class for optimized news fetching with ETag caching and rate limiting."""
    
    def __init__(self, cache_file: str = None):
        self.session = None
        self.cache_file = cache_file or 'data/feed_cache.json'
        self.feed_cache = self._load_cache()
        self._request_semaphore = None
        self._concurrency_limit = 5
    
    def _load_cache(self) -> Dict:
        """Load ETag and Last-Modified cache from file."""
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load feed cache: {e}")
        
        return {
            'etags': {},  # url -> etag
            'last_modified': {},  # url -> last-modified header
            'last_guids': defaultdict(list)  # url -> list of last N GUIDs
        }
    
    def _save_cache(self):
        """Save ETag and Last-Modified cache to file."""
        try:
            os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
            # Convert defaultdict to regular dict for JSON serialization
            cache_copy = {
                'etags': self.feed_cache['etags'],
                'last_modified': self.feed_cache['last_modified'],
                'last_guids': dict(self.feed_cache['last_guids'])
            }
            with open(self.cache_file, 'w') as f:
                json.dump(cache_copy, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save feed cache: {e}")
    
    def set_concurrency_limit(self, limit: int):
        """Set maximum concurrent requests."""
        self._concurrency_limit = limit
        if self._request_semaphore:
            # Create new semaphore with updated limit
            self._request_semaphore = asyncio.Semaphore(limit)
    
    async def _ensure_session(self):
        """Ensure aiohttp session exists."""
        if not self.session:
            timeout = aiohttp.ClientTimeout(total=10, connect=5)
            self.session = aiohttp.ClientSession(timeout=timeout)
        
        if not self._request_semaphore:
            self._request_semaphore = asyncio.Semaphore(self._concurrency_limit)
    
    async def fetch_feed_optimized(
        self,
        url: str,
        source_name: str,
        use_cache: bool = True
    ) -> Optional[Tuple[str, str, str, str]]:
        """
        Fetch RSS feed with ETag/Last-Modified caching.
        
        Returns:
            Tuple of (title, link, description, guid) or None if no new content
        """
        await self._ensure_session()
        
        # Prepare headers with cache validation
        headers = {}
        if use_cache:
            if url in self.feed_cache['etags']:
                headers['If-None-Match'] = self.feed_cache['etags'][url]
            if url in self.feed_cache['last_modified']:
                headers['If-Modified-Since'] = self.feed_cache['last_modified'][url]
        
        try:
            # Use semaphore to limit concurrent requests
            async with self._request_semaphore:
                async with self.session.get(url, headers=headers) as response:
                    # 304 Not Modified - no new content
                    if response.status == 304:
                        logger.debug(f"{source_name}: No new content (304)")
                        return None
                    
                    if response.status != 200:
                        logger.warning(f"{source_name}: HTTP {response.status}")
                        return None
                    
                    # Update cache headers
                    if use_cache:
                        if 'ETag' in response.headers:
                            self.feed_cache['etags'][url] = response.headers['ETag']
                        if 'Last-Modified' in response.headers:
                            self.feed_cache['last_modified'][url] = response.headers['Last-Modified']
                    
                    content = await response.text()
                    
                    # Parse feed
                    return self._parse_feed_content(content, url, source_name)
        
        except asyncio.TimeoutError:
            logger.warning(f"{source_name}: Request timeout")
            return None
        except Exception as e:
            logger.error(f"{source_name}: Error fetching feed: {e}")
            return None
    
    def _parse_feed_content(
        self,
        content: str,
        url: str,
        source_name: str
    ) -> Optional[Tuple[str, str, str, str]]:
        """Parse RSS/Atom feed content and return latest item."""
        try:
            # Detect feed type and parse accordingly
            item_pattern = r'<item>(.*?)</item>' if '<item>' in content else r'<entry>(.*?)</entry>'
            items = re.findall(item_pattern, content, re.DOTALL)
            
            if not items:
                logger.debug(f"{source_name}: No items found in feed")
                return None
            
            # Check multiple items to find first new one
            for item in items[:5]:  # Check up to 5 most recent items
                # Extract GUID/ID for deduplication
                guid_match = re.search(r'<guid(?:\s+[^>]*)?>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</guid>', item, re.DOTALL)
                if not guid_match:
                    guid_match = re.search(r'<id(?:\s+[^>]*)?>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</id>', item, re.DOTALL)
                
                guid = guid_match.group(1).strip() if guid_match else None
                
                # Check if we've already seen this GUID
                last_guids = self.feed_cache['last_guids'].get(url, [])
                if guid and guid in last_guids:
                    continue  # Skip already posted items
                
                # Extract title
                title = None
                title_match = re.search(r'<title(?:\s+[^>]*)?>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>', item, re.DOTALL)
                if title_match:
                    title = title_match.group(1).strip()
                    # IMPORTANT: Unescape HTML entities FIRST, then strip tags
                    title = unescape(title)
                    title = re.sub(r'<[^>]+>', '', title).strip()
                
                # If no title or empty, try content/summary for a title
                if not title:
                    # Try to extract from content as fallback
                    content_match = re.search(r'<content(?:\s+[^>]*)?>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</content>', item, re.DOTALL)
                    if not content_match:
                        content_match = re.search(r'<summary(?:\s+[^>]*)?>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</summary>', item, re.DOTALL)
                    
                    if content_match:
                        content = re.sub(r'<[^>]+>', '', content_match.group(1))
                        content = unescape(content.strip())
                        # Get first sentence or first 100 chars
                        first_sentence = re.split(r'[.!?]\s+', content)[0]
                        title = first_sentence[:100] + ("..." if len(first_sentence) > 100 else "")
                
                # Final fallback
                if not title:
                    title = "Latest Update"
                
                # Extract link
                link_match = re.search(r'<link(?:\s+[^>]*)?>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</link>', item, re.DOTALL)
                if not link_match:
                    link_match = re.search(r'<link\s+href="([^"]+)"', item)
                link = link_match.group(1).strip() if link_match else url
                
                # Extract description
                desc_match = re.search(r'<description>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</description>', item, re.DOTALL)
                if not desc_match:
                    desc_match = re.search(r'<summary>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</summary>', item, re.DOTALL)
                if not desc_match:
                    desc_match = re.search(r'<content(?:\s+[^>]*)?>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</content>', item, re.DOTALL)
                
                description = ""
                if desc_match:
                    desc = desc_match.group(1).strip()
                    
                    # Log raw description for debugging
                    logger.debug(f"{source_name}: Raw desc length: {len(desc)}, first 100 chars: {desc[:100]}")
                    
                    # IMPORTANT: Unescape HTML entities FIRST (converts &lt; to <, &amp; to &, etc.)
                    # This ensures the HTML parser can see actual tags, not entity-encoded text
                    desc = unescape(desc)
                    logger.debug(f"{source_name}: After unescape: {desc[:100]}")
                    
                    # Use HTML parser to properly strip all tags
                    stripper = HTMLStripper()
                    try:
                        stripper.feed(desc)
                        desc = stripper.get_text()
                        logger.debug(f"{source_name}: After HTMLStripper: {desc[:100]}")
                    except Exception as e:
                        # Fallback to regex if parser fails
                        logger.warning(f"HTML parser failed for {source_name}, using regex: {e}")
                        desc = re.sub(r'<script[^>]*>.*?</script\s*>', '', desc, flags=re.DOTALL | re.IGNORECASE)
                        desc = re.sub(r'<style[^>]*>.*?</style\s*>', '', desc, flags=re.DOTALL | re.IGNORECASE)
                        desc = re.sub(r'<[^>]+>', '', desc)
                        logger.debug(f"{source_name}: After regex: {desc[:100]}")
                    
                    # Clean up whitespace
                    desc = re.sub(r'\s+', ' ', desc)  # Normalize whitespace
                    desc = desc.strip()
                    
                    # Truncate if too long
                    description = desc[:300] + "..." if len(desc) > 300 else desc
                    logger.info(f"{source_name}: Final description: {description[:100]}")
                
                # Use link as fallback GUID
                if not guid:
                    guid = link
                
                # Update GUID cache (keep last 50 per feed)
                if url not in self.feed_cache['last_guids']:
                    self.feed_cache['last_guids'][url] = []
                
                self.feed_cache['last_guids'][url].append(guid)
                self.feed_cache['last_guids'][url] = self.feed_cache['last_guids'][url][-50:]
                
                return title, link, description, guid
            
            # All items already posted
            logger.debug(f"{source_name}: All items already posted")
            return None
        
        except Exception as e:
            logger.error(f"{source_name}: Error parsing feed: {e}")
            return None
    
    async def fetch_multiple_feeds(
        self,
        sources: Dict[str, Dict],
        enabled_sources: List[str],
        use_cache: bool = True
    ) -> List[Tuple[str, str, str, str, Dict]]:
        """
        Fetch multiple feeds concurrently with rate limiting.
        
        Returns:
            List of tuples: (title, link, description, guid, source_info)
        """
        await self._ensure_session()
        
        tasks = []
        source_map = {}
        
        for source_key in enabled_sources:
            if source_key not in sources:
                continue
            
            source = sources[source_key]
            task = self.fetch_feed_optimized(
                source['url'],
                source['name'],
                use_cache=use_cache
            )
            tasks.append(task)
            source_map[len(tasks) - 1] = (source_key, source)
        
        # Execute all tasks concurrently with semaphore limiting concurrency
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results
        new_items = []
        for idx, result in enumerate(results):
            if isinstance(result, Exception):
                source_key, source = source_map[idx]
                logger.error(f"Error fetching {source['name']}: {result}")
                continue
            
            if result:  # Has new content
                source_key, source = source_map[idx]
                title, link, description, guid = result
                new_items.append((title, link, description, guid, source))
        
        # Save cache after batch fetch
        if new_items:
            self._save_cache()
        
        return new_items
    
    async def close(self):
        """Close aiohttp session and save cache."""
        self._save_cache()
        if self.session:
            await self.session.close()
            self.session = None
