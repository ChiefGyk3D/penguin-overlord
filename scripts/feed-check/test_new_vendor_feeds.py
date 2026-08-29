#!/usr/bin/env python3
"""
Verification test for newly added vendor feeds.
"""

import asyncio
import sys
import aiohttp
import xml.etree.ElementTree as ET
from html import unescape


# Newly added vendor feeds
NEWS_SOURCES = {
    'zeropatch': {
        'name': '0patch Blog',
        'url': 'https://blog.0patch.com/feeds/posts/default',
    },
    'att_cybersecurity': {
        'name': 'AT&T Cybersecurity',
        'url': 'https://cybersecurity.att.com/site/blog-all-rss',
    },
    'bitdefender_labs': {
        'name': 'Bitdefender Labs',
        'url': 'https://www.bitdefender.com/blog/api/rss/labs/',
    },
    'broadcom_symantec': {
        'name': 'Broadcom Symantec',
        'url': 'https://sed-cms.broadcom.com/rss/v1/blogs/rss.xml',
    },
    'cisco_security': {
        'name': 'Cisco Security Blog',
        'url': 'https://blogs.cisco.com/security/feed',
    },
    'cisco_talos': {
        'name': 'Cisco Talos Intelligence',
        'url': 'http://feeds.feedburner.com/feedburner/Talos',
    },
    'cloudflare_security': {
        'name': 'Cloudflare Security',
        'url': 'https://blog.cloudflare.com/tag/security/rss',
    },
    'eclecticiq': {
        'name': 'EclecticIQ',
        'url': 'https://blog.eclecticiq.com/rss.xml',
    },
    'foxit': {
        'name': 'Fox-IT International',
        'url': 'https://blog.fox-it.com/feed/',
    },
    'google_project_zero': {
        'name': 'Google Project Zero',
        'url': 'https://googleprojectzero.blogspot.com/feeds/posts/default',
    },
    'microsoft_security': {
        'name': 'Microsoft Security Blog',
        'url': 'https://www.microsoft.com/security/blog/feed/',
    },
    'proofpoint': {
        'name': 'Proofpoint',
        'url': 'https://www.proofpoint.com/us/rss.xml',
    },
    'quarkslab': {
        'name': 'Quarkslab',
        'url': 'https://blog.quarkslab.com/feeds/all.rss.xml',
    },
    'quickheal': {
        'name': 'Quick Heal Antivirus',
        'url': 'https://blogs.quickheal.com/feed/',
    },
    'therecord': {
        'name': 'The Record',
        'url': 'https://therecord.media/feed/',
    },
    'sensepost': {
        'name': 'SensePost (Orange)',
        'url': 'https://sensepost.com/rss.xml',
    },
    'sentinelone': {
        'name': 'SentinelOne Labs',
        'url': 'https://www.sentinelone.com/labs/feed/',
    },
    'socprime': {
        'name': 'SOC Prime',
        'url': 'https://socprime.com/blog/feed/',
    },
    'tripwire': {
        'name': 'Tripwire',
        'url': 'https://www.tripwire.com/state-of-security/feed/',
    },
    'upguard_news': {
        'name': 'UpGuard News',
        'url': 'https://www.upguard.com/news/rss.xml',
    },
    'upguard_breaches': {
        'name': 'UpGuard Breaches',
        'url': 'https://www.upguard.com/breaches/rss.xml',
    },
    'virusbulletin': {
        'name': 'Virus Bulletin',
        'url': 'https://www.virusbulletin.com/rss',
    },
    'virustotal': {
        'name': 'VirusTotal',
        'url': 'https://blog.virustotal.com/feeds/posts/default',
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
                    print(f"❌ {source['name']:<40} HTTP {response.status}")
                    return False
                
                content = await response.text()
                root = ET.fromstring(content)
                
                # Find items
                items = root.findall('.//{http://www.w3.org/2005/Atom}entry')
                if not items:
                    items = root.findall('.//item')
                
                if not items:
                    print(f"❌ {source['name']:<40} No items found")
                    return False
                
                # Get first item title
                item = items[0]
                title_elem = item.find('.//{http://www.w3.org/2005/Atom}title')
                if title_elem is None:
                    title_elem = item.find('title')
                
                title = "N/A"
                if title_elem is not None and title_elem.text:
                    title = unescape(title_elem.text.strip())[:60]
                
                print(f"✅ {source['name']:<40} [{len(items):>2} items] - {title}...")
                return True
    
    except Exception as e:
        print(f"❌ {source['name']:<40} {type(e).__name__}: {str(e)[:50]}")
        return False


async def main():
    """Test all new feeds."""
    print("=" * 80)
    print("TESTING NEWLY ADDED VENDOR FEEDS")
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
