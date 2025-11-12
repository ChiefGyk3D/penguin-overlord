#!/usr/bin/env python3
"""
Test script to verify the 30 new analyst/community feeds added to cybersecurity_news.py
"""

import asyncio
import aiohttp
import xml.etree.ElementTree as ET

# The 30 new analyst/community feeds to test
NEW_ANALYST_FEEDS = {
    'alexplaskett': {'name': 'Alex Plaskett', 'url': 'https://alexplaskett.github.io/feed'},
    'blazesec': {'name': "Blaze's Security Blog", 'url': 'https://bartblaze.blogspot.com/feeds/posts/default'},
    'bushidotoken': {'name': 'BushidoToken Threat Intel', 'url': 'https://blog.bushidotoken.net/feeds/posts/default'},
    'connormcgarr': {'name': 'Connor McGarr', 'url': 'https://connormcgarr.github.io/feed'},
    'curatedintel': {'name': 'Curated Intelligence', 'url': 'https://www.curatedintel.org/feeds/posts/default'},
    'cyberintelinsights': {'name': 'Cyber Intelligence Insights', 'url': 'https://intelinsights.substack.com/feed'},
    'cybercrimediaries': {'name': 'Cybercrime Diaries', 'url': 'https://www.cybercrimediaries.com/blog-feed.xml'},
    'darknet': {'name': 'Darknet', 'url': 'http://www.darknet.org.uk/feed/'},
    'databreaches': {'name': 'DataBreaches', 'url': 'https://www.databreaches.net/feed/'},
    'doublepulsar': {'name': 'DoublePulsar (Kevin Beaumont)', 'url': 'https://doublepulsar.com/feed'},
    'krebsonsecurity': {'name': 'Krebs on Security', 'url': 'http://krebsonsecurity.com/feed/'},
    'krebs_breaches': {'name': 'Krebs on Security (Data Breaches)', 'url': 'https://krebsonsecurity.com/category/data-breaches/feed/'},
    'krebs_warnings': {'name': 'Krebs on Security (Latest Warnings)', 'url': 'https://krebsonsecurity.com/category/latest-warnings/feed/'},
    'krebs_ransomware': {'name': 'Krebs on Security (Ransomware)', 'url': 'https://krebsonsecurity.com/category/ransomware/feed/'},
    'lohrmann': {'name': 'Lohrmann on Cybersecurity', 'url': 'http://feeds.feedburner.com/govtech/blogs/lohrmann_on_infrastructure'},
    'lowleveladventures': {'name': 'Low-level adventures', 'url': 'https://0x434b.dev/rss/'},
    'n1ghtwolf': {'name': 'n1ght-w0lf', 'url': 'https://n1ght-w0lf.github.io/feed'},
    'naosec': {'name': 'nao_sec', 'url': 'https://nao-sec.org/feed'},
    'outflux': {'name': 'Outflux', 'url': 'https://outflux.net/blog/feed/'},
    'breachescloud': {'name': 'Public Cloud Security Breaches', 'url': 'https://www.breaches.cloud/index.xml'},
    'schneier': {'name': 'Schneier on Security', 'url': 'https://www.schneier.com/blog/atom.xml'},
    'dfirreport': {'name': 'The DFIR Report', 'url': 'https://thedfirreport.com/feed/'},
    'troyhunt_scam': {'name': 'Troy Hunt (Scam)', 'url': 'https://www.troyhunt.com/tag/scam/rss/'},
    'troyhunt_security': {'name': 'Troy Hunt (Security)', 'url': 'https://www.troyhunt.com/tag/security/rss/'},
    'willsroot': {'name': "Will's Root", 'url': 'https://www.willsroot.io/feeds/posts/default'},
    'citizenlab': {'name': 'Citizen Lab', 'url': 'https://citizenlab.ca/feed/'},
    'isc_sans': {'name': "ISC Handler's Diary", 'url': 'https://isc.sans.edu/rssfeed_full.xml'},
    'reddit_cybersecurity': {'name': 'Reddit (/r/cybersecurity)', 'url': 'https://www.reddit.com/r/cybersecurity/.rss'},
    'reddit_netsec': {'name': 'Reddit (/r/netsec)', 'url': 'http://www.reddit.com/r/netsec/.rss'},
    'zdi_published': {'name': 'Zero Day Initiative (Published)', 'url': 'https://www.zerodayinitiative.com/rss/published/'}
}


async def test_feed(session, feed_key, feed_data):
    """Test a single feed"""
    try:
        async with session.get(feed_data['url'], timeout=aiohttp.ClientTimeout(total=15)) as response:
            if response.status == 200:
                content = await response.text()
                try:
                    root = ET.fromstring(content)
                    # Check for RSS or Atom items
                    items = root.findall('.//item') or root.findall('.//{http://www.w3.org/2005/Atom}entry')
                    if items:
                        # Try to get first item's title
                        first_item = items[0]
                        title = None
                        for title_tag in ['title', '{http://www.w3.org/2005/Atom}title']:
                            title_elem = first_item.find(title_tag)
                            if title_elem is not None:
                                title = title_elem.text
                                break
                        
                        return {
                            'status': 'working',
                            'feed_key': feed_key,
                            'name': feed_data['name'],
                            'url': feed_data['url'],
                            'items_count': len(items),
                            'first_title': title[:80] + '...' if title and len(title) > 80 else title
                        }
                    else:
                        return {
                            'status': 'error',
                            'feed_key': feed_key,
                            'name': feed_data['name'],
                            'url': feed_data['url'],
                            'error': 'No items found in feed'
                        }
                except ET.ParseError as e:
                    return {
                        'status': 'error',
                        'feed_key': feed_key,
                        'name': feed_data['name'],
                        'url': feed_data['url'],
                        'error': f'XML parse error: {str(e)}'
                    }
            else:
                return {
                    'status': 'error',
                    'feed_key': feed_key,
                    'name': feed_data['name'],
                    'url': feed_data['url'],
                    'error': f'HTTP {response.status}'
                }
    except asyncio.TimeoutError:
        return {
            'status': 'error',
            'feed_key': feed_key,
            'name': feed_data['name'],
            'url': feed_data['url'],
            'error': 'Timeout (15s)'
        }
    except Exception as e:
        return {
            'status': 'error',
            'feed_key': feed_key,
            'name': feed_data['name'],
            'url': feed_data['url'],
            'error': str(e)
        }


async def test_all_feeds():
    """Test all feeds"""
    print(f"Testing {len(NEW_ANALYST_FEEDS)} new analyst/community feeds...\n")
    
    async with aiohttp.ClientSession() as session:
        tasks = []
        for feed_key, feed_data in NEW_ANALYST_FEEDS.items():
            tasks.append(test_feed(session, feed_key, feed_data))
        
        results = await asyncio.gather(*tasks)
    
    # Categorize results
    working = [r for r in results if r['status'] == 'working']
    broken = [r for r in results if r['status'] == 'error']
    
    # Display results
    print("=" * 80)
    print(f"WORKING FEEDS: {len(working)}/{len(NEW_ANALYST_FEEDS)}")
    print("=" * 80)
    for feed in working:
        print(f"✓ {feed['name']}")
        print(f"  Key: {feed['feed_key']}")
        print(f"  Items: {feed['items_count']}")
        if feed['first_title']:
            print(f"  Latest: {feed['first_title']}")
        print()
    
    if broken:
        print("\n" + "=" * 80)
        print(f"BROKEN FEEDS: {len(broken)}/{len(NEW_ANALYST_FEEDS)}")
        print("=" * 80)
        for feed in broken:
            print(f"✗ {feed['name']}")
            print(f"  Key: {feed['feed_key']}")
            print(f"  Error: {feed['error']}")
            print(f"  URL: {feed['url']}")
            print()
    
    # Summary
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Total feeds tested: {len(NEW_ANALYST_FEEDS)}")
    print(f"Working: {len(working)}")
    print(f"Broken: {len(broken)}")
    print(f"Success rate: {len(working)/len(NEW_ANALYST_FEEDS)*100:.1f}%")
    
    return len(working), len(broken)


if __name__ == '__main__':
    working_count, broken_count = asyncio.run(test_all_feeds())
    
    # Exit with error if any feeds are broken
    if broken_count > 0:
        print(f"\n⚠️  Warning: {broken_count} feed(s) not working")
        exit(1)
    else:
        print("\n✓ All feeds working!")
        exit(0)
