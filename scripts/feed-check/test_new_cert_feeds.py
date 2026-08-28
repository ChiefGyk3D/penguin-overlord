#!/usr/bin/env python3
"""
Verify the newly added CERT and government feeds
"""

import asyncio
import aiohttp
import xml.etree.ElementTree as ET

# New CVE/CERT feeds added to cve.py
NEW_CVE_FEEDS = {
    'cert_pl': {'name': 'CERT.PL', 'url': 'https://cert.pl/en/atom.xml'},
    'cert_fr': {'name': 'CERT-FR (ANSSI)', 'url': 'https://www.cert.ssi.gouv.fr/cti/feed/'},
    'cert_ca': {'name': 'Canadian Centre for Cyber Security', 'url': 'https://www.cyber.gc.ca/api/cccs/atom/v1/get?feed=alerts_advisories&lang=en'},
    'jpcert': {'name': 'JPCERT/CC', 'url': 'https://blogs.jpcert.or.jp/en/atom.xml'},
    'cisa_alerts': {'name': 'CISA Alerts', 'url': 'https://us-cert.cisa.gov/ncas/alerts.xml'},
    'cisa_current': {'name': 'CISA Current Activity', 'url': 'https://us-cert.cisa.gov/ncas/current-activity.xml'}
}

# New feed added to cybersecurity_news.py
NEW_NEWS_FEEDS = {
    'cisa_analysis': {'name': 'CISA Analysis Reports', 'url': 'https://us-cert.cisa.gov/ncas/analysis-reports.xml'}
}


async def test_feed(session, feed_key, feed_data, feed_type):
    """Test a single feed"""
    try:
        async with session.get(feed_data['url'], timeout=aiohttp.ClientTimeout(total=30)) as response:
            if response.status == 200:
                content = await response.text()
                try:
                    root = ET.fromstring(content)
                    # Check for RSS or Atom items
                    items = root.findall('.//item') or root.findall('.//{http://www.w3.org/2005/Atom}entry')
                    if items:
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
                            'type': feed_type,
                            'items_count': len(items),
                            'first_title': title[:80] + '...' if title and len(title) > 80 else title
                        }
                    else:
                        return {
                            'status': 'error',
                            'feed_key': feed_key,
                            'name': feed_data['name'],
                            'url': feed_data['url'],
                            'type': feed_type,
                            'error': 'No items found'
                        }
                except ET.ParseError as e:
                    return {
                        'status': 'error',
                        'feed_key': feed_key,
                        'name': feed_data['name'],
                        'url': feed_data['url'],
                        'type': feed_type,
                        'error': f'XML parse error: {str(e)}'
                    }
            else:
                return {
                    'status': 'error',
                    'feed_key': feed_key,
                    'name': feed_data['name'],
                    'url': feed_data['url'],
                    'type': feed_type,
                    'error': f'HTTP {response.status}'
                }
    except asyncio.TimeoutError:
        return {
            'status': 'error',
            'feed_key': feed_key,
            'name': feed_data['name'],
            'url': feed_data['url'],
            'type': feed_type,
            'error': 'Timeout (30s)'
        }
    except Exception as e:
        return {
            'status': 'error',
            'feed_key': feed_key,
            'name': feed_data['name'],
            'url': feed_data['url'],
            'type': feed_type,
            'error': str(e)
        }


async def test_all_feeds():
    """Test all newly added feeds"""
    print("Verifying newly added CERT and government feeds...\n")
    
    async with aiohttp.ClientSession() as session:
        tasks = []
        
        # Test CVE feeds
        for feed_key, feed_data in NEW_CVE_FEEDS.items():
            tasks.append(test_feed(session, feed_key, feed_data, 'cve'))
        
        # Test news feeds
        for feed_key, feed_data in NEW_NEWS_FEEDS.items():
            tasks.append(test_feed(session, feed_key, feed_data, 'news'))
        
        results = await asyncio.gather(*tasks)
    
    # Categorize results
    cve_working = [r for r in results if r['status'] == 'working' and r['type'] == 'cve']
    cve_broken = [r for r in results if r['status'] == 'error' and r['type'] == 'cve']
    news_working = [r for r in results if r['status'] == 'working' and r['type'] == 'news']
    news_broken = [r for r in results if r['status'] == 'error' and r['type'] == 'news']
    
    # Display CVE results
    print("=" * 80)
    print(f"CVE COG - NEW FEEDS: {len(cve_working)}/{len(NEW_CVE_FEEDS)}")
    print("=" * 80)
    for feed in cve_working:
        print(f"✓ {feed['name']}")
        print(f"  Key: {feed['feed_key']}")
        print(f"  Items: {feed['items_count']}")
        if feed.get('first_title'):
            print(f"  Latest: {feed['first_title']}")
        print()
    
    if cve_broken:
        print("\n" + "=" * 80)
        print(f"CVE COG - BROKEN FEEDS: {len(cve_broken)}")
        print("=" * 80)
        for feed in cve_broken:
            print(f"✗ {feed['name']}")
            print(f"  Key: {feed['feed_key']}")
            print(f"  Error: {feed['error']}")
            print(f"  URL: {feed['url']}")
            print()
    
    # Display news results
    print("=" * 80)
    print(f"CYBERSECURITY NEWS COG - NEW FEEDS: {len(news_working)}/{len(NEW_NEWS_FEEDS)}")
    print("=" * 80)
    for feed in news_working:
        print(f"✓ {feed['name']}")
        print(f"  Key: {feed['feed_key']}")
        print(f"  Items: {feed['items_count']}")
        if feed.get('first_title'):
            print(f"  Latest: {feed['first_title']}")
        print()
    
    if news_broken:
        print("\n" + "=" * 80)
        print(f"CYBERSECURITY NEWS COG - BROKEN FEEDS: {len(news_broken)}")
        print("=" * 80)
        for feed in news_broken:
            print(f"✗ {feed['name']}")
            print(f"  Key: {feed['feed_key']}")
            print(f"  Error: {feed['error']}")
            print(f"  URL: {feed['url']}")
            print()
    
    # Summary
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"CVE cog: {len(cve_working)}/{len(NEW_CVE_FEEDS)} working")
    print(f"Cybersecurity News cog: {len(news_working)}/{len(NEW_NEWS_FEEDS)} working")
    print(f"Total: {len(cve_working) + len(news_working)}/{len(NEW_CVE_FEEDS) + len(NEW_NEWS_FEEDS)} working")
    
    total_broken = len(cve_broken) + len(news_broken)
    if total_broken > 0:
        print(f"\n⚠️  Warning: {total_broken} feed(s) not working")
        return 1
    else:
        print("\n✓ All feeds working!")
        return 0


if __name__ == '__main__':
    exit_code = asyncio.run(test_all_feeds())
    exit(exit_code)
