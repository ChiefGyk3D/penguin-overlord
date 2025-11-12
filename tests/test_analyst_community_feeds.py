#!/usr/bin/env python3
"""
Test script for analyst and community cybersecurity feeds
"""

import asyncio
import aiohttp
import xml.etree.ElementTree as ET
import json

# Analyst and Community feeds to test
ANALYST_COMMUNITY_FEEDS = {
    '0xtoxin': {'name': '0xToxin', 'url': 'https://0xtoxin.github.io/feed.xml'},
    'alexplaskett': {'name': 'Alex Plaskett', 'url': 'https://alexplaskett.github.io/feed'},
    'apps3c': {'name': 'apps3c', 'url': 'https://www.apps3c.info/feed/'},
    'bellingcat_africa': {'name': 'bellingcat (Africa)', 'url': 'https://www.bellingcat.com/category/africa/feed/'},
    'bellingcat': {'name': 'bellingcat', 'url': 'https://www.bellingcat.com/feed/'},
    'bellingcat_americas': {'name': 'bellingcat (Americas)', 'url': 'https://www.bellingcat.com/category/americas/feed/'},
    'bellingcat_investigations': {'name': 'bellingcat (Investigations)', 'url': 'https://www.bellingcat.com/category/news/feed'},
    'bellingcat_mena': {'name': 'bellingcat (MENA)', 'url': 'https://www.bellingcat.com/category/mena/feed/'},
    'bellingcat_restofworld': {'name': 'bellingcat (Rest of World)', 'url': 'https://www.bellingcat.com/category/rest-of-world/feed/'},
    'bellingcat_ukeurope': {'name': 'bellingcat (UK & Europe)', 'url': 'https://www.bellingcat.com/category/uk-and-europe/feed/'},
    'bellingcat_uncategorized': {'name': 'bellingcat (Uncategorized)', 'url': 'https://www.bellingcat.com/category/uncategorized/feed'},
    'blazesec': {'name': "Blaze's Security Blog", 'url': 'https://bartblaze.blogspot.com/feeds/posts/default'},
    'bushidotoken': {'name': 'BushidoToken Threat Intel', 'url': 'https://blog.bushidotoken.net/feeds/posts/default'},
    'connormcgarr': {'name': 'Connor McGarr', 'url': 'https://connormcgarr.github.io/feed'},
    'curatedintel': {'name': 'Curated Intelligence', 'url': 'https://www.curatedintel.org/feeds/posts/default'},
    'cyberintelinsights': {'name': 'Cyber Intelligence Insights', 'url': 'https://intelinsights.substack.com/feed'},
    'cybercrimediaries': {'name': 'Cybercrime Diaries', 'url': 'https://www.cybercrimediaries.com/blog-feed.xml'},
    'darknet_advertorial': {'name': 'Darknet (Advertorial)', 'url': 'https://www.darknet.org.uk/category/advertorial/feed/'},
    'darknet': {'name': 'Darknet', 'url': 'http://www.darknet.org.uk/feed/'},
    'darknet_apple': {'name': 'Darknet (Apple)', 'url': 'https://www.darknet.org.uk/category/apple-hacking/feed/'},
    'darknet_countermeasures': {'name': 'Darknet (Countermeasures)', 'url': 'https://www.darknet.org.uk/category/countermeasures/feed/'},
    'darknet_cryptography': {'name': 'Darknet (Cryptography)', 'url': 'https://www.darknet.org.uk/category/cryptography/feed/'},
    'darknet_database': {'name': 'Darknet (Database Hacking)', 'url': 'https://www.darknet.org.uk/category/database-hacking/feed/'},
    'darknet_exploits': {'name': 'Darknet (Exploits/Vulnerabilities)', 'url': 'https://www.darknet.org.uk/category/exploitsvulnerabilities/feed/'},
    'darknet_forensics': {'name': 'Darknet (Forensics)', 'url': 'https://www.darknet.org.uk/category/forensics/feed/'},
    'darknet_culture': {'name': 'Darknet (Hacker Culture)', 'url': 'https://www.darknet.org.uk/category/hacker-culture/feed/'},
    'darknet_news': {'name': 'Darknet (Hacking News)', 'url': 'https://www.darknet.org.uk/category/hacking-news/feed/'},
    'darknet_tools': {'name': 'Darknet (Hacking Tools)', 'url': 'https://www.darknet.org.uk/category/hacking-tools/feed/'},
    'darknet_hardware': {'name': 'Darknet (Hardware Hacking)', 'url': 'https://www.darknet.org.uk/category/hardware-hacking/feed/'},
    'darknet_legal': {'name': 'Darknet (Legal Issues)', 'url': 'https://www.darknet.org.uk/category/legal-issues/feed/'},
    'darknet_linux': {'name': 'Darknet (Linux Hacking)', 'url': 'https://www.darknet.org.uk/category/linux-hacking/feed/'},
    'darknet_malware': {'name': 'Darknet (Malware)', 'url': 'https://www.darknet.org.uk/category/virustrojanswormsrootkits/feed/'},
    'darknet_networking': {'name': 'Darknet (Networking Hacking)', 'url': 'https://www.darknet.org.uk/category/networking-hacking/feed/'},
    'darknet_password': {'name': 'Darknet (Password Cracking)', 'url': 'https://www.darknet.org.uk/category/password-cracking/feed/'},
    'darknet_phishing': {'name': 'Darknet (Phishing)', 'url': 'https://www.darknet.org.uk/category/phishing/feed/'},
    'darknet_privacy': {'name': 'Darknet (Privacy)', 'url': 'https://www.darknet.org.uk/category/privacy/feed/'},
    'darknet_securecoding': {'name': 'Darknet (Secure Coding)', 'url': 'https://www.darknet.org.uk/category/secure-coding/feed/'},
    'darknet_securitysoftware': {'name': 'Darknet (Security Software)', 'url': 'https://www.darknet.org.uk/category/security-software/feed/'},
    'darknet_socialeng': {'name': 'Darknet (Social Engineering)', 'url': 'https://www.darknet.org.uk/category/social-engineering/feed/'},
    'darknet_spam': {'name': 'Darknet (Spammers & Scammers)', 'url': 'https://www.darknet.org.uk/category/spammers-scammers/feed/'},
    'darknet_stupidemails': {'name': 'Darknet (Stupid E-mails)', 'url': 'https://www.darknet.org.uk/category/stupid-emails/feed/'},
    'darknet_telecomms': {'name': 'Darknet (Telecomms Hacking)', 'url': 'https://www.darknet.org.uk/category/telecomms-hacking/feed/'},
    'darknet_unix': {'name': 'Darknet (UNIX Hacking)', 'url': 'https://www.darknet.org.uk/category/unix-hacking/feed/'},
    'darknet_virology': {'name': 'Darknet (Virology)', 'url': 'https://www.darknet.org.uk/category/virology/feed/'},
    'darknet_webhacking': {'name': 'Darknet (Web Hacking)', 'url': 'https://www.darknet.org.uk/category/web-hacking/feed/'},
    'darknet_windows': {'name': 'Darknet (Windows Hacking)', 'url': 'https://www.darknet.org.uk/category/windows-hacking/feed/'},
    'darknet_wireless': {'name': 'Darknet (Wireless Hacking)', 'url': 'https://www.darknet.org.uk/category/wireless-hacking/feed/'},
    'databreaches': {'name': 'DataBreaches', 'url': 'https://www.databreaches.net/feed/'},
    'doublepulsar': {'name': 'DoublePulsar (Kevin Beaumont)', 'url': 'https://doublepulsar.com/feed'},
    'jossefkadouri': {'name': 'Jossef Harush Kadouri', 'url': 'https://medium.com/@jossef/feed'},
    'krebs_sunshine': {'name': 'Krebs on Security (A Little Sunshine)', 'url': 'https://krebsonsecurity.com/category/sunshine/feed/'},
    'krebsonsecurity': {'name': 'Krebs on Security', 'url': 'http://krebsonsecurity.com/feed/'},
    'krebs_skimmers': {'name': 'Krebs on Security (All About Skimmers)', 'url': 'https://krebsonsecurity.com/category/all-about-skimmers/feed/'},
    'krebs_ashleymadison': {'name': 'Krebs on Security (Ashley Madison)', 'url': 'https://krebsonsecurity.com/category/ashley-madison-breach/feed/'},
    'krebs_breadcrumbs': {'name': 'Krebs on Security (Breadcrumbs)', 'url': 'https://krebsonsecurity.com/category/breadcrumbs/feed/'},
    'krebs_breaches': {'name': 'Krebs on Security (Data Breaches)', 'url': 'https://krebsonsecurity.com/category/data-breaches/feed/'},
    'krebs_ddos': {'name': 'Krebs on Security (DDoS-for-Hire)', 'url': 'https://krebsonsecurity.com/category/ddos-for-hire/feed/'},
    'krebs_employmentfraud': {'name': 'Krebs on Security (Employment Fraud)', 'url': 'https://krebsonsecurity.com/category/employment-fraud/feed/'},
    'krebs_iot': {'name': 'Krebs on Security (IoT)', 'url': 'https://krebsonsecurity.com/category/internet-of-things-iot/feed/'},
    'krebs_warnings': {'name': 'Krebs on Security (Latest Warnings)', 'url': 'https://krebsonsecurity.com/category/latest-warnings/feed/'},
    'krebs_neerdowell': {'name': "Krebs on Security (Ne'er-Do-Well News)", 'url': 'https://krebsonsecurity.com/category/neer-do-well-news/feed/'},
    'krebs_other': {'name': 'Krebs on Security (Other)', 'url': 'https://krebsonsecurity.com/category/other/feed/'},
    'krebs_pharma': {'name': 'Krebs on Security (Pharma Wars)', 'url': 'https://krebsonsecurity.com/category/pharma-wars/feed/'},
    'krebs_ransomware': {'name': 'Krebs on Security (Ransomware)', 'url': 'https://krebsonsecurity.com/category/ransomware/feed/'},
    'krebs_ukraine': {'name': "Krebs on Security (Russia's War on Ukraine)", 'url': 'https://krebsonsecurity.com/category/russias-war-on-ukraine/feed/'},
    'krebs_tools': {'name': 'Krebs on Security (Security Tools)', 'url': 'https://krebsonsecurity.com/category/security-tools/feed/'},
    'krebs_simswap': {'name': 'Krebs on Security (SIM Swapping)', 'url': 'https://krebsonsecurity.com/category/sim-swapping/feed/'},
    'krebs_spamnation': {'name': 'Krebs on Security (Spam Nation)', 'url': 'https://krebsonsecurity.com/category/spam-nation/feed/'},
    'krebs_smallbiz': {'name': 'Krebs on Security (Small Businesses)', 'url': 'https://krebsonsecurity.com/category/smallbizvictims/feed/'},
    'krebs_taxfraud': {'name': 'Krebs on Security (Tax Refund Fraud)', 'url': 'https://krebsonsecurity.com/category/tax-refund-fraud/feed/'},
    'krebs_comingstorm': {'name': 'Krebs on Security (The Coming Storm)', 'url': 'https://krebsonsecurity.com/category/comingstorm/feed/'},
    'krebs_patches': {'name': 'Krebs on Security (Time to Patch)', 'url': 'https://krebsonsecurity.com/category/patches/feed/'},
    'krebs_webfraud': {'name': 'Krebs on Security (Web Fraud 2.0)', 'url': 'https://krebsonsecurity.com/category/web-fraud-2-0/feed/'},
    'lohrmann': {'name': 'Lohrmann on Cybersecurity', 'url': 'http://feeds.feedburner.com/govtech/blogs/lohrmann_on_infrastructure'},
    'lowleveladventures': {'name': 'Low-level adventures', 'url': 'https://0x434b.dev/rss/'},
    'maxwelldulin': {'name': 'maxwelldulin', 'url': 'https://maxwelldulin.invades.space/resources-rss.xml'},
    'n1ghtwolf': {'name': 'n1ght-w0lf', 'url': 'https://n1ght-w0lf.github.io/feed'},
    'naosec': {'name': 'nao_sec', 'url': 'https://nao-sec.org/feed'},
    'outflux': {'name': 'Outflux', 'url': 'https://outflux.net/blog/feed/'},
    'breachescloud': {'name': 'Public Cloud Security Breaches', 'url': 'https://www.breaches.cloud/index.xml'},
    'schneier': {'name': 'Schneier on Security', 'url': 'https://www.schneier.com/blog/atom.xml'},
    'sebdraven': {'name': 'sebdraven', 'url': 'https://sebdraven.medium.com/feed'},
    'lordx64': {'name': 'taha aka "lordx64"', 'url': 'https://lordx64.medium.com/feed'},
    'dfirreport': {'name': 'The DFIR Report', 'url': 'https://thedfirreport.com/feed/'},
    'troyhunt': {'name': 'Troy Hunt', 'url': 'https://www.troyhunt.com/rss/'},
    'troyhunt_scam': {'name': 'Troy Hunt (Scam)', 'url': 'https://www.troyhunt.com/tag/scam/rss/'},
    'troyhunt_security': {'name': 'Troy Hunt (Security)', 'url': 'https://www.troyhunt.com/tag/security/rss/'},
    'willsroot': {'name': "Will's Root", 'url': 'https://www.willsroot.io/feeds/posts/default'},
    'citizenlab': {'name': 'Citizen Lab', 'url': 'https://citizenlab.ca/feed/'},
    'isc_sans': {'name': "ISC Handler's Diary", 'url': 'https://isc.sans.edu/rssfeed_full.xml'},
    'reddit_blueteam': {'name': 'Reddit (/r/blueteamsec)', 'url': 'https://www.reddit.com/r/blueteamsec/.rss'},
    'reddit_cybersecurity': {'name': 'Reddit (/r/cybersecurity)', 'url': 'https://www.reddit.com/r/cybersecurity/.rss'},
    'reddit_infosec': {'name': 'Reddit (/r/InfoSecNews)', 'url': 'https://www.reddit.com/r/InfoSecNews/.rss'},
    'reddit_netsec': {'name': 'Reddit (/r/netsec)', 'url': 'http://www.reddit.com/r/netsec/.rss'},
    'zdi_blog': {'name': 'Zero Day Initiative (Blog)', 'url': 'https://www.zerodayinitiative.com/blog/?format=rss'},
    'zdi_published': {'name': 'Zero Day Initiative (Published)', 'url': 'https://www.zerodayinitiative.com/rss/published/'},
    'zdi_upcoming': {'name': 'Zero Day Initiative (Upcoming)', 'url': 'https://www.zerodayinitiative.com/rss/upcoming/'}
}


async def test_feed(session, feed_key, feed_data):
    """Test a single feed"""
    try:
        async with session.get(feed_data['url'], timeout=aiohttp.ClientTimeout(total=15)) as response:
            if response.status == 200:
                content = await response.text()
                try:
                    root = ET.fromstring(content)
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
                            'items_count': len(items)
                        }
                    else:
                        return {
                            'status': 'error',
                            'feed_key': feed_key,
                            'name': feed_data['name'],
                            'url': feed_data['url'],
                            'error': 'No items found'
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
            'error': 'Timeout'
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
    """Test all feeds in batches"""
    print(f"Testing {len(ANALYST_COMMUNITY_FEEDS)} analyst/community feeds...\n")
    
    feed_items = list(ANALYST_COMMUNITY_FEEDS.items())
    batch_size = 25
    all_results = []
    
    async with aiohttp.ClientSession() as session:
        for i in range(0, len(feed_items), batch_size):
            batch = feed_items[i:i + batch_size]
            batch_num = i // batch_size + 1
            total_batches = (len(feed_items) + batch_size - 1) // batch_size
            
            print(f"Testing batch {batch_num}/{total_batches} ({len(batch)} feeds)...")
            
            tasks = [test_feed(session, key, data) for key, data in batch]
            results = await asyncio.gather(*tasks)
            all_results.extend(results)
            
            if i + batch_size < len(feed_items):
                await asyncio.sleep(2)
    
    # Check for already included feeds
    from pathlib import Path
    cybersec_file = Path(__file__).parent.parent / 'penguin-overlord' / 'cogs' / 'cybersecurity_news.py'
    if cybersec_file.exists():
        existing_content = cybersec_file.read_text()
        already_included = []
        for result in all_results:
            if result['status'] == 'working' and result['url'] in existing_content:
                already_included.append(result)
        
        if already_included:
            print(f"\n{'='*80}")
            print(f"ALREADY INCLUDED: {len(already_included)}")
            print('='*80)
            for feed in already_included:
                print(f"  - {feed['name']} ({feed['feed_key']})")
            
            # Remove already included from working list
            all_results = [r for r in all_results if r not in already_included]
    
    # Categorize results
    working = [r for r in all_results if r['status'] == 'working']
    broken = [r for r in all_results if r['status'] == 'error']
    
    # Save results
    results_data = {
        'working': working,
        'broken': broken
    }
    
    with open('analyst_community_feed_results.json', 'w') as f:
        json.dump(results_data, f, indent=2)
    
    # Display summary
    print(f"\n{'='*80}")
    print(f"WORKING FEEDS: {len(working)}")
    print('='*80)
    for feed in working[:10]:
        print(f"✓ {feed['name']} - {feed['items_count']} items")
    if len(working) > 10:
        print(f"  ... and {len(working) - 10} more")
    
    print(f"\n{'='*80}")
    print(f"BROKEN FEEDS: {len(broken)}")
    print('='*80)
    error_types = {}
    for feed in broken:
        error = feed['error'].split(':')[0] if ':' in feed['error'] else feed['error']
        error_types[error] = error_types.get(error, 0) + 1
    for error, count in sorted(error_types.items(), key=lambda x: x[1], reverse=True):
        print(f"  {error}: {count}")
    
    print(f"\n{'='*80}")
    print("SUMMARY")
    print('='*80)
    print(f"Total tested: {len(ANALYST_COMMUNITY_FEEDS)}")
    print(f"Working: {len(working)}")
    print(f"Broken: {len(broken)}")
    print(f"Success rate: {len(working)/len(ANALYST_COMMUNITY_FEEDS)*100:.1f}%")
    print(f"\nResults saved to: analyst_community_feed_results.json")
    
    return working, broken


if __name__ == '__main__':
    working, broken = asyncio.run(test_all_feeds())
