#!/usr/bin/env python3
"""
Test script to check journalist RSS feeds from the provided list.
Identifies which are already in cybersecurity_news.py and tests the missing ones.
"""

import asyncio
import aiohttp
import xml.etree.ElementTree as ET
from html import unescape

# Feeds from user's list
JOURNALIST_FEEDS = {
    'anton_on_security': {
        'name': 'Anton on Security',
        'url': 'https://medium.com/feed/anton-on-security',
        'description': 'Information Security, Cyber Security and Fun!'
    },
    'arstechnica_security': {
        'name': 'Ars Technica (Security)',
        'url': 'https://arstechnica.com/tag/security/feed/',
        'description': 'Serving the Technologist for more than a decade'
    },
    'bellingcat': {
        'name': 'bellingcat',
        'url': 'https://www.bellingcat.com/feed/',
        'description': 'Independent international collective of researchers'
    },
    'bleepingcomputer': {
        'name': 'BleepingComputer',
        'url': 'https://www.bleepingcomputer.com/feed',
        'description': 'Leading source for security threats and tech news'
    },
    'cio_security': {
        'name': 'CIO Magazine (Security)',
        'url': 'https://www.cio.com/category/security/index.rss',
        'description': 'IT and security news for professionals'
    },
    'darkreading': {
        'name': 'Dark Reading (all)',
        'url': 'https://www.darkreading.com/rss/all.xml',
        'description': 'Most trusted online community for security professionals'
    },
    'grahamcluley': {
        'name': 'Graham Cluley',
        'url': 'https://www.grahamcluley.com/feed/',
        'description': 'Security news from veteran anti-virus expert'
    },
    'guardian_security': {
        'name': 'Guardian (Data and computer security)',
        'url': 'https://www.theguardian.com/technology/data-computer-security/rss',
        'description': 'Articles published by The Guardian team'
    },
    'hackerone': {
        'name': 'HackerOne',
        'url': 'https://www.hackerone.com/blog.rss',
        'description': 'Partner with global hacker community'
    },
    'hackmageddon': {
        'name': 'HACKMAGEDDON',
        'url': 'https://www.hackmageddon.com/feed/',
        'description': 'By Paolo Passeri'
    },
    'hackread': {
        'name': 'HackRead',
        'url': 'https://www.hackread.com/feed/',
        'description': 'InfoSec, Cyber Crime, Privacy, Surveillance news'
    },
    'infosecurity_mag': {
        'name': 'Infosecurity Magazine (news)',
        'url': 'http://www.infosecurity-magazine.com/rss/news/',
        'description': 'Award winning online magazine for InfoSec'
    },
    'intezer': {
        'name': 'Intezer',
        'url': 'https://www.intezer.com/blog/feed/',
        'description': 'Preventing attackers from reusing code'
    },
    'krebs': {
        'name': 'Krebs on Security',
        'url': 'http://krebsonsecurity.com/feed/',
        'description': 'Investigative stories on cybercrime and security'
    },
    'lohrmann': {
        'name': 'Lohrmann on Cybersecurity',
        'url': 'http://feeds.feedburner.com/govtech/blogs/lohrmann_on_infrastructure',
        'description': 'Cybersecurity for virtual government'
    },
    'malware_traffic': {
        'name': 'Malware Traffic Analysis',
        'url': 'http://www.malware-traffic-analysis.net/blog-entries.rss',
        'description': 'Malicious network traffic analysis'
    },
    'motherboard_tech': {
        'name': 'Motherboard (tech)',
        'url': 'https://www.vice.com/en_us/rss/section/tech',
        'description': 'Online magazine dedicated to technology and science'
    },
    'schneier': {
        'name': 'Schneier on Security',
        'url': 'https://www.schneier.com/blog/atom.xml',
        'description': 'Blog by Bruce Schneier on security technology'
    },
    'securityaffairs': {
        'name': 'Security Affairs',
        'url': 'http://securityaffairs.co/wordpress/feed',
        'description': 'By Pierluigi Paganini'
    },
    'techrepublic_security': {
        'name': 'TechRepublic (security)',
        'url': 'http://www.techrepublic.com/rssfeeds/topic/security/?feedType=rssfeeds',
        'description': 'Resources for online industry and security'
    },
    'threatpost': {
        'name': 'Threatpost',
        'url': 'https://threatpost.com/feed/',
        'description': 'Leading source of IT and business security info'
    },
    'troyhunt': {
        'name': 'Troy Hunt',
        'url': 'https://www.troyhunt.com/rss/',
        'description': 'Microsoft MVP and Pluralsight author'
    },
    'wired_security': {
        'name': 'WIRED Security',
        'url': 'https://www.wired.com/feed/category/security/latest/rss',
        'description': 'Where tomorrow is realized'
    },
    'zdnet_security': {
        'name': 'ZDNet (security)',
        'url': 'https://www.zdnet.com/topic/security/rss.xml',
        'description': 'Latest security vulnerabilities'
    }
}

# Existing feeds in cybersecurity_news.py (based on URL patterns)
EXISTING_FEEDS = {
    'bleepingcomputer': 'https://www.bleepingcomputer.com/feed/',
    'darkreading': 'https://www.darkreading.com/rss.xml',
    'schneier': 'https://www.schneier.com/feed/atom/',
    'securityaffairs': 'https://securityaffairs.com/feed',
    'krebs': 'https://krebsonsecurity.com/feed/',
    'troyhunt': 'https://www.troyhunt.com/rss/',
    'grahamcluley': 'https://grahamcluley.com/feed/',
    'threatpost': 'https://threatpost.com/feed/',
    'infosecurity_mag': 'https://www.infosecurity-magazine.com/rss/news/',
    'guardian_security': 'https://www.theguardian.com/technology/data-computer-security/rss',
    'cio_security': 'https://www.cio.com/feed/',
    'lohrmann': 'https://feeds.feedburner.com/govtech/blogs/lohrmann_on_infrastructure',
    'wired_security': 'https://www.wired.com/category/security/feed'
}


async def test_rss_feed(url: str, name: str) -> dict:
    """Test if an RSS feed is accessible and returns valid data."""
    result = {
        'name': name,
        'url': url,
        'status': 'unknown',
        'error': None,
        'title': None,
        'items_found': 0
    }
    
    try:
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as response:
                result['status'] = response.status
                
                if response.status != 200:
                    result['error'] = f"HTTP {response.status}"
                    return result
                
                content = await response.text()
                
                # Try to parse as XML
                try:
                    root = ET.fromstring(content)
                    
                    # Find items (RSS or Atom)
                    items = root.findall('.//{http://www.w3.org/2005/Atom}entry')
                    if not items:
                        items = root.findall('.//item')
                    
                    result['items_found'] = len(items)
                    
                    if items:
                        item = items[0]
                        
                        # Extract title
                        title_elem = item.find('.//{http://www.w3.org/2005/Atom}title')
                        if title_elem is None:
                            title_elem = item.find('title')
                        
                        if title_elem is not None and title_elem.text:
                            result['title'] = unescape(title_elem.text.strip())[:100]
                        
                        result['status'] = 'working'
                    else:
                        result['error'] = 'No items found in feed'
                        result['status'] = 'empty'
                
                except ET.ParseError as e:
                    result['error'] = f"XML parse error: {str(e)[:100]}"
                    result['status'] = 'invalid'
    
    except asyncio.TimeoutError:
        result['error'] = 'Request timeout'
        result['status'] = 'timeout'
    except Exception as e:
        result['error'] = f"{type(e).__name__}: {str(e)[:100]}"
        result['status'] = 'error'
    
    return result


async def main():
    """Main test function."""
    print("=" * 80)
    print("RSS FEED ANALYSIS FOR CYBERSECURITY NEWS")
    print("=" * 80)
    print()
    
    # Check which feeds are already included
    print("📋 ALREADY INCLUDED IN CYBERSECURITY_NEWS.PY:")
    print("-" * 80)
    already_included = []
    
    for key, feed in JOURNALIST_FEEDS.items():
        url_lower = feed['url'].lower().replace('https://', '').replace('http://', '')
        
        is_included = False
        for existing_key, existing_url in EXISTING_FEEDS.items():
            existing_lower = existing_url.lower().replace('https://', '').replace('http://', '')
            
            # Check for URL match (normalize slight variations)
            if url_lower in existing_lower or existing_lower in url_lower:
                is_included = True
                already_included.append(key)
                print(f"✓ {feed['name']:<40} (as '{existing_key}')")
                break
        
        if not is_included and key in EXISTING_FEEDS:
            already_included.append(key)
            print(f"✓ {feed['name']:<40} (key match)")
    
    print()
    print(f"Total already included: {len(already_included)}")
    print()
    
    # Test feeds that are not included
    missing_feeds = {k: v for k, v in JOURNALIST_FEEDS.items() if k not in already_included}
    
    if not missing_feeds:
        print("✅ All feeds are already included!")
        return
    
    print("🔍 TESTING MISSING FEEDS:")
    print("-" * 80)
    print(f"Testing {len(missing_feeds)} feeds...\n")
    
    # Test all feeds concurrently
    tasks = [test_rss_feed(feed['url'], feed['name']) for feed in missing_feeds.values()]
    results = await asyncio.gather(*tasks)
    
    # Categorize results
    working = []
    broken = []
    
    for result in results:
        if result['status'] == 'working':
            working.append(result)
        else:
            broken.append(result)
    
    # Display working feeds
    print("✅ WORKING FEEDS (ready to add):")
    print("-" * 80)
    for r in working:
        print(f"✓ {r['name']:<40} [{r['items_found']} items]")
        print(f"  URL: {r['url']}")
        if r['title']:
            print(f"  Latest: {r['title']}")
        print()
    
    print(f"Total working: {len(working)}")
    print()
    
    # Display broken feeds
    if broken:
        print("❌ NON-WORKING FEEDS:")
        print("-" * 80)
        for r in broken:
            print(f"✗ {r['name']:<40} [{r['status']}]")
            print(f"  URL: {r['url']}")
            if r['error']:
                print(f"  Error: {r['error']}")
            print()
        
        print(f"Total non-working: {len(broken)}")
        print()
    
    # Summary
    print("=" * 80)
    print("SUMMARY:")
    print(f"  Already included: {len(already_included)}")
    print(f"  Working (can add): {len(working)}")
    print(f"  Non-working: {len(broken)}")
    print(f"  Total feeds tested: {len(JOURNALIST_FEEDS)}")
    print("=" * 80)
    
    # Generate code snippet for working feeds
    if working:
        print("\n📝 CODE TO ADD TO NEWS_SOURCES:")
        print("-" * 80)
        
        for r in working:
            # Find the feed key
            feed_key = None
            for k, v in missing_feeds.items():
                if v['name'] == r['name']:
                    feed_key = k
                    break
            
            if feed_key:
                feed = missing_feeds[feed_key]
                icon = '📰'  # Default icon
                color = '0x1E88E5'  # Default color
                
                print(f"    '{feed_key}': {{")
                print(f"        'name': '{feed['name']}',")
                print(f"        'url': '{feed['url']}',")
                print(f"        'color': {color},")
                print(f"        'icon': '{icon}'")
                print(f"    }},")


if __name__ == '__main__':
    asyncio.run(main())
