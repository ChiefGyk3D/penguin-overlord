#!/usr/bin/env python3
"""
Test script to verify the 30 new comprehensive cybersecurity feeds added to cybersecurity_news.py
"""

import asyncio
import aiohttp
import xml.etree.ElementTree as ET

# The 30 new comprehensive feeds to test
NEW_COMPREHENSIVE_FEEDS = {
    'cybersecuritynews': {
        'name': 'Cyber Security News',
        'url': 'https://cybersecuritynews.com/feed/'
    },
    'gbhackers': {
        'name': 'GBHackers',
        'url': 'https://gbhackers.com/feed/'
    },
    'securityboulevard': {
        'name': 'Security Boulevard',
        'url': 'https://securityboulevard.com/feed/'
    },
    'thecyberwire': {
        'name': 'The Cyber Wire',
        'url': 'https://thecyberwire.com/feeds/rss.xml'
    },
    'theregister_security': {
        'name': 'The Register (Security)',
        'url': 'https://www.theregister.com/security/headlines.atom'
    },
    'techcrunch_security': {
        'name': 'TechCrunch (Security)',
        'url': 'https://techcrunch.com/category/security/feed/'
    },
    'nextgov_cyber': {
        'name': 'NextGov (Cybersecurity)',
        'url': 'https://www.nextgov.com/rss/cybersecurity/'
    },
    'securityledger': {
        'name': 'The Security Ledger',
        'url': 'https://feeds.feedblitz.com/thesecurityledger&x=1'
    },
    'mandiant': {
        'name': 'Mandiant',
        'url': 'https://www.mandiant.com/resources/blog/rss.xml'
    },
    'datadog_security': {
        'name': 'Datadog Security Labs',
        'url': 'https://securitylabs.datadoghq.com/rss/feed.xml'
    },
    'github_security': {
        'name': 'GitHub Security Lab',
        'url': 'https://github.blog/tag/github-security-lab/feed/'
    },
    'google_tag': {
        'name': 'Google Threat Analysis Group',
        'url': 'https://blog.google/threat-analysis-group/rss/'
    },
    'greynoise': {
        'name': 'GreyNoise Labs',
        'url': 'https://www.labs.greynoise.io/grimoire/index.xml'
    },
    'groupib': {
        'name': 'Group IB',
        'url': 'https://blog.group-ib.com/rss.xml'
    },
    'haveibeenpwned': {
        'name': 'Have I Been Pwned',
        'url': 'https://feeds.feedburner.com/HaveIBeenPwnedLatestBreaches'
    },
    'huntress': {
        'name': 'Huntress',
        'url': 'https://www.huntress.com/blog/rss.xml'
    },
    'paloalto_unit42_feed': {
        'name': 'PaloAlto Unit 42',
        'url': 'http://feeds.feedburner.com/Unit42'
    },
    'recorded_future': {
        'name': 'Recorded Future',
        'url': 'https://www.recordedfuture.com/feed'
    },
    'wiz': {
        'name': 'WIZ Blog',
        'url': 'https://www.wiz.io/feed/rss.xml'
    },
    'wiz_threat': {
        'name': 'WIZ Cloud Threat Landscape',
        'url': 'https://www.wiz.io/api/feed/cloud-threat-landscape/rss.xml'
    },
    'cybereason': {
        'name': 'Cybereason',
        'url': 'https://www.cybereason.com/blog/rss.xml'
    },
    'sekoia': {
        'name': 'Sekoia',
        'url': 'https://blog.sekoia.io/feed/'
    },
    'trustwave': {
        'name': 'Trustwave SpiderLabs',
        'url': 'https://www.trustwave.com/en-us/resources/blogs/spiderlabs-blog/rss.xml'
    },
    'ahnlab': {
        'name': 'AhnLab Security Intelligence',
        'url': 'https://asec.ahnlab.com/en/feed/'
    },
    'checkmarx': {
        'name': 'Checkmarx',
        'url': 'https://medium.com/feed/checkmarx-security'
    },
    'anyrun_malware': {
        'name': 'ANY.RUN (Malware Analysis)',
        'url': 'https://any.run/cybersecurity-blog/category/malware-analysis/feed/'
    },
    'blackhills_blue': {
        'name': 'Black Hills (Blue Team)',
        'url': 'https://www.blackhillsinfosec.com/category/blue-team/feed/'
    },
    'fortinet_threat_feed': {
        'name': 'Fortinet (Threat Research)',
        'url': 'https://feeds.fortinet.com/fortinet/blog/threat-research&x=1'
    },
    'cis_advisory': {
        'name': 'CIS (Advisories)',
        'url': 'https://www.cisecurity.org/feed/advisories'
    },
    'pulsedive': {
        'name': 'Pulsedive',
        'url': 'https://blog.pulsedive.com/rss/'
    }
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
    print(f"Testing {len(NEW_COMPREHENSIVE_FEEDS)} new comprehensive feeds...\n")
    
    async with aiohttp.ClientSession() as session:
        tasks = []
        for feed_key, feed_data in NEW_COMPREHENSIVE_FEEDS.items():
            tasks.append(test_feed(session, feed_key, feed_data))
        
        results = await asyncio.gather(*tasks)
    
    # Categorize results
    working = [r for r in results if r['status'] == 'working']
    broken = [r for r in results if r['status'] == 'error']
    
    # Display results
    print("=" * 80)
    print(f"WORKING FEEDS: {len(working)}/{len(NEW_COMPREHENSIVE_FEEDS)}")
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
        print(f"BROKEN FEEDS: {len(broken)}/{len(NEW_COMPREHENSIVE_FEEDS)}")
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
    print(f"Total feeds tested: {len(NEW_COMPREHENSIVE_FEEDS)}")
    print(f"Working: {len(working)}")
    print(f"Broken: {len(broken)}")
    print(f"Success rate: {len(working)/len(NEW_COMPREHENSIVE_FEEDS)*100:.1f}%")
    
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
