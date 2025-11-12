#!/usr/bin/env python3
"""
Quick verification test for the newly added feeds.
"""

import asyncio
import sys
import os
import aiohttp
import xml.etree.ElementTree as ET
from html import unescape


# Directly define the new feeds to test
NEWS_SOURCES = {
    'anton_on_security': {
        'name': 'Anton on Security',
        'url': 'https://medium.com/feed/anton-on-security',
    },
    'arstechnica_security': {
        'name': 'Ars Technica (Security)',
        'url': 'https://arstechnica.com/tag/security/feed/',
    },
    'bellingcat': {
        'name': 'bellingcat',
        'url': 'https://www.bellingcat.com/feed/',
    },
    'hackmageddon': {
        'name': 'HACKMAGEDDON',
        'url': 'https://www.hackmageddon.com/feed/',
    },
    'hackread': {
        'name': 'HackRead',
        'url': 'https://www.hackread.com/feed/',
    },
    'malware_traffic': {
        'name': 'Malware Traffic Analysis',
        'url': 'http://www.malware-traffic-analysis.net/blog-entries.rss',
    },
    'techrepublic_security': {
        'name': 'TechRepublic (security)',
        'url': 'http://www.techrepublic.com/rssfeeds/topic/security/?feedType=rssfeeds',
    },
    'zdnet_security': {
        'name': 'ZDNet (security)',
        'url': 'https://www.zdnet.com/topic/security/rss.xml',
    }
}

NEW_FEEDS = list(NEWS_SOURCES.keys())


async def test_feed(key: str) -> bool:
    """Test a single feed."""
    source = NEWS_SOURCES.get(key)
    if not source:
        print(f"❌ {key}: Not found in NEWS_SOURCES")
        return False
    
    try:
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(source['url']) as response:
                if response.status != 200:
                    print(f"❌ {source['name']}: HTTP {response.status}")
                    return False
                
                content = await response.text()
                root = ET.fromstring(content)
                
                # Find items
                items = root.findall('.//{http://www.w3.org/2005/Atom}entry')
                if not items:
                    items = root.findall('.//item')
                
                if not items:
                    print(f"❌ {source['name']}: No items found")
                    return False
                
                # Get first item title
                item = items[0]
                title_elem = item.find('.//{http://www.w3.org/2005/Atom}title')
                if title_elem is None:
                    title_elem = item.find('title')
                
                title = "N/A"
                if title_elem is not None and title_elem.text:
                    title = unescape(title_elem.text.strip())[:60]
                
                print(f"✅ {source['name']:<35} [{len(items)} items] - {title}...")
                return True
    
    except Exception as e:
        print(f"❌ {source['name']}: {type(e).__name__}: {str(e)[:50]}")
        return False


async def main():
    """Test all new feeds."""
    print("=" * 80)
    print("TESTING NEWLY ADDED FEEDS")
    print("=" * 80)
    print()
    
    tasks = [test_feed(key) for key in NEW_FEEDS]
    results = await asyncio.gather(*tasks)
    
    success = sum(results)
    total = len(results)
    
    print()
    print("=" * 80)
    print(f"RESULTS: {success}/{total} feeds working")
    print("=" * 80)
    
    return success == total


if __name__ == '__main__':
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
