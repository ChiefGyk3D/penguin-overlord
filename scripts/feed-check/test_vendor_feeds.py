#!/usr/bin/env python3
"""
Test script to check vendor RSS feeds from the provided list.
Identifies which are already in cybersecurity_news.py and tests the missing ones.
"""

import asyncio
import aiohttp
import xml.etree.ElementTree as ET
from html import unescape

# Vendor feeds from user's list
VENDOR_FEEDS = {
    'zeropatch': {
        'name': '0patch Blog',
        'url': 'https://blog.0patch.com/feeds/posts/default',
        'description': 'Microscopic binary patches platform by ACROS Security'
    },
    'anomali': {
        'name': 'Anomali',
        'url': 'https://www.anomali.com/site/blog-rss',
        'description': 'Intelligence-driven cybersecurity solutions'
    },
    'att_cybersecurity': {
        'name': 'AT&T Cybersecurity',
        'url': 'https://cybersecurity.att.com/site/blog-all-rss',
        'description': 'Recent posts from AT&T Cybersecurity blogs'
    },
    'bitdefender_labs': {
        'name': 'Bitdefender Labs',
        'url': 'https://www.bitdefender.com/blog/api/rss/labs/',
        'description': 'Discovers 400 new threats each minute'
    },
    'broadcom_symantec': {
        'name': 'Broadcom Symantec blogs',
        'url': 'https://sed-cms.broadcom.com/rss/v1/blogs/rss.xml',
        'description': 'Symantec Enterprise Blog'
    },
    'checkpoint': {
        'name': 'Checkpoint',
        'url': 'https://research.checkpoint.com/feed/',
        'description': 'Checkpoint research blog'
    },
    'cisco_security': {
        'name': 'Cisco Security Blog',
        'url': 'https://blogs.cisco.com/security/feed',
        'description': 'Posts from the Cisco Security team'
    },
    'cisco_talos': {
        'name': 'Cisco Talos Intelligence Group',
        'url': 'http://feeds.feedburner.com/feedburner/Talos',
        'description': 'One of largest commercial threat intelligence teams'
    },
    'cloudflare_security': {
        'name': 'Cloudflare Security Blog',
        'url': 'https://blog.cloudflare.com/tag/security/rss',
        'description': 'Posts tagged with security on Cloudflare Blog'
    },
    'cofense': {
        'name': 'Cofense Intelligence',
        'url': 'https://cofense.com/feed/',
        'description': 'Phishing Prevention & Email Security Blog'
    },
    'crowdstrike_threat': {
        'name': 'Crowdstrike (Threat Research)',
        'url': 'https://www.crowdstrike.com/blog/category/threat-intel-research/',
        'description': 'Reports from threat research team at Crowdstrike'
    },
    'digital_shadows': {
        'name': 'Digital Shadows',
        'url': 'https://www.digitalshadows.com/blog-and-research/feed/',
        'description': 'Latest advice and research from intelligence analysts'
    },
    'eclecticiq': {
        'name': 'EclecticIQ',
        'url': 'https://blog.eclecticiq.com/rss.xml',
        'description': 'Fusion Center delivers thematic intelligence bundles'
    },
    'eset_newsroom': {
        'name': 'We Live Security (ESET)',
        'url': 'http://eset.com/int/rss.xml',
        'description': 'Security solutions for 200+ countries'
    },
    'fireeye': {
        'name': 'FireEye',
        'url': 'http://www.fireeye.com/blog/feed',
        'description': 'Leader in advanced threat prevention'
    },
    'foxit': {
        'name': 'Fox-IT International blog',
        'url': 'https://blog.fox-it.com/feed/',
        'description': 'We make the invisible visible'
    },
    'fortinet_threat': {
        'name': 'Fortinet (threat research)',
        'url': 'http://feeds.feedburner.com/fortinet/blog/threat-research',
        'description': 'FortiGuard Labs threat intelligence'
    },
    'google_security': {
        'name': 'Google Online Security',
        'url': 'https://googleonlinesecurity.blogspot.com/atom.xml',
        'description': 'Latest news from Google on security'
    },
    'google_project_zero': {
        'name': 'Google Project Zero',
        'url': 'https://googleprojectzero.blogspot.com/feeds/posts/default',
        'description': 'Zero-day vulnerability research team'
    },
    'ibm_security': {
        'name': 'IBM Security Intelligence',
        'url': 'https://securityintelligence.com/feed/',
        'description': 'Analysis from cybersecurity industry minds'
    },
    'malwarebytes': {
        'name': 'Malwarebytes Labs',
        'url': 'https://blog.malwarebytes.com/feed/',
        'description': 'Free from threats, free to thrive'
    },
    'mcafee': {
        'name': 'McAfee Labs',
        'url': 'https://www.mcafee.com/blogs/feed',
        'description': 'Leading independent cyber security company'
    },
    'microsoft_security': {
        'name': 'Microsoft Security Blog',
        'url': 'https://www.microsoft.com/security/blog/feed/',
        'description': 'Microsoft Security protection'
    },
    'msrc': {
        'name': 'Microsoft Security Response Center',
        'url': 'https://msrc-blog.microsoft.com/feed/',
        'description': 'MSRC on front line of security response'
    },
    'sophos': {
        'name': 'Naked Security (Sophos)',
        'url': 'https://nakedsecurity.sophos.com/feed/',
        'description': 'Computer security news from Sophos'
    },
    'proofpoint': {
        'name': 'Proofpoint',
        'url': 'https://www.proofpoint.com/us/rss.xml',
        'description': 'Protection for your greatest risk—your people'
    },
    'qualys': {
        'name': 'Qualys Blog',
        'url': 'https://blog.qualys.com/feed',
        'description': 'Qualys and industry best practices'
    },
    'quarkslab': {
        'name': 'Quarkslab blog',
        'url': 'https://blog.quarkslab.com/feeds/all.rss.xml',
        'description': 'Private infosec R&D laboratory'
    },
    'quickheal': {
        'name': 'Quick Heal Antivirus',
        'url': 'https://blogs.quickheal.com/feed/',
        'description': 'Protect millions from Internet threats'
    },
    'therecord': {
        'name': 'The Record',
        'url': 'https://therecord.media/feed/',
        'description': 'Exclusive access to cyber underground leaders'
    },
    'recorded_future_cyber': {
        'name': 'Recorded Future (Cyber Threat Intelligence)',
        'url': 'https://www.recordedfuture.com/category/cyber/feed/',
        'description': 'Organize and analyze threat data'
    },
    'recorded_future_threat': {
        'name': 'Recorded Future (Threat Intelligence)',
        'url': 'https://www.recordedfuture.com/category/threat-intelligence/feed/',
        'description': 'Threat intelligence analysis'
    },
    'recorded_future_vuln': {
        'name': 'Recorded Future (Vulnerability Management)',
        'url': 'https://www.recordedfuture.com/category/vulnerability-management/feed/',
        'description': 'Vulnerability management insights'
    },
    'recorded_future_research': {
        'name': 'Recorded Future (Research)',
        'url': 'https://www.recordedfuture.com/category/research/vulnerability-management/feed/',
        'description': 'Research on vulnerability management'
    },
    'recorded_future_geo': {
        'name': 'Recorded Future (Geopolitical Intelligence)',
        'url': 'https://www.recordedfuture.com/category/geopolitical/feed/',
        'description': 'Geopolitical threat intelligence'
    },
    'riskiq': {
        'name': 'RiskIQ',
        'url': 'https://www.riskiq.com/feed/',
        'description': 'Combat threats to your organization'
    },
    'securelist': {
        'name': 'SecureList (Kaspersky)',
        'url': 'https://securelist.com/feed/',
        'description': 'Kaspersky cyberthreat research'
    },
    'secureworks': {
        'name': 'Dell SecureWorks (Research & Intelligence)',
        'url': 'https://www.secureworks.com/rss?feed=blog&category=research-intelligence',
        'description': 'Managed Security Services'
    },
    'sensepost': {
        'name': 'SensePost (Orange)',
        'url': 'https://sensepost.com/rss.xml',
        'description': 'Ethical hacking team of Orange Cyberdefense'
    },
    'sentinelone': {
        'name': 'SentinelOne Labs',
        'url': 'https://www.sentinelone.com/labs/feed/',
        'description': 'Open venue for threat researchers'
    },
    'socprime': {
        'name': 'SOC Prime',
        'url': 'https://socprime.com/blog/feed/',
        'description': 'Platform to advance cyber security analytics'
    },
    'signalscorps': {
        'name': 'Signals Corps',
        'url': 'https://www.signalscorps.com/feed.xml',
        'description': 'Our blog!'
    },
    'specterops': {
        'name': 'SpecterOps',
        'url': 'https://posts.specterops.io/feed',
        'description': 'Posts on information security topics'
    },
    'trendmicro': {
        'name': 'Trend Micro',
        'url': 'http://feeds.trendmicro.com/TrendMicroSimplySecurity',
        'description': 'Global leader in enterprise data security'
    },
    'tripwire': {
        'name': 'Tripwire',
        'url': 'https://www.tripwire.com/state-of-security/feed/',
        'description': 'Security, compliance and IT operations'
    },
    'trustarc': {
        'name': 'TrustArc',
        'url': 'https://www.trustarc.com/blog/feed/',
        'description': 'Reduce complexities, eliminate redundancies'
    },
    'paloalto': {
        'name': 'PaloAlto Networks Blog',
        'url': 'https://www.paloaltonetworks.com/blog/rss',
        'description': 'Blog from the PaloAlto team'
    },
    'unit42': {
        'name': 'PaloAlto Networks Unit 42',
        'url': 'http://researchcenter.paloaltonetworks.com/unit42/feed/',
        'description': 'Global threat intelligence team'
    },
    'phishlabs': {
        'name': 'PhishLabs',
        'url': 'http://blog.phishlabs.com/rss.xml',
        'description': 'Digital Risk Protection'
    },
    'upguard_news': {
        'name': 'UpGuard Blog (news)',
        'url': 'https://www.upguard.com/news/rss.xml',
        'description': 'Cybersecurity & Risk Management Blog'
    },
    'upguard_breaches': {
        'name': 'UpGuard Blog (breaches)',
        'url': 'https://www.upguard.com/breaches/rss.xml',
        'description': 'Data breach news'
    },
    'veracode': {
        'name': 'Veracode Security Blog',
        'url': 'http://www.veracode.com/blog/feed/',
        'description': 'Build advanced application security program'
    },
    'virusbulletin': {
        'name': 'Virus Bulletin',
        'url': 'https://www.virusbulletin.com/rss',
        'description': 'Security information portal and testing'
    },
    'virustotal': {
        'name': 'VirusTotal Blog',
        'url': 'https://blog.virustotal.com/feeds/posts/default',
        'description': 'News and research from VirusTotal team'
    },
    'webroot': {
        'name': 'Webroot Threat Blog',
        'url': 'https://www.webroot.com/blog/feed/',
        'description': 'First to harness cloud and AI for zero-day threats'
    }
}

# Existing feeds in cybersecurity_news.py (based on URL patterns)
EXISTING_FEEDS = {
    'aws_security': 'https://aws.amazon.com/blogs/security/feed/',
    'crowdstrike': 'https://www.crowdstrike.com/en-us/blog/feed',
    'tenable': 'https://www.tenable.com/blog/rss',
    'google_security': 'https://feeds.feedburner.com/GoogleOnlineSecurityBlog',
    'sophos': 'https://nakedsecurity.sophos.com/feed/',
    'trendmicro': 'http://feeds.trendmicro.com/TrendMicroResearch',
    'malwarebytes': 'https://www.malwarebytes.com/blog/feed/index.xml',
    'cofense': 'https://cofense.com/feed/'
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
    print("VENDOR RSS FEED ANALYSIS FOR CYBERSECURITY NEWS")
    print("=" * 80)
    print()
    
    # Check which feeds are already included
    print("📋 ALREADY INCLUDED IN CYBERSECURITY_NEWS.PY:")
    print("-" * 80)
    already_included = []
    
    for key, feed in VENDOR_FEEDS.items():
        url_lower = feed['url'].lower().replace('https://', '').replace('http://', '')
        
        is_included = False
        for existing_key, existing_url in EXISTING_FEEDS.items():
            existing_lower = existing_url.lower().replace('https://', '').replace('http://', '')
            
            # Check for URL match (normalize slight variations)
            if url_lower in existing_lower or existing_lower in url_lower:
                is_included = True
                already_included.append(key)
                print(f"✓ {feed['name']:<45} (as '{existing_key}')")
                break
        
        if not is_included and key in EXISTING_FEEDS:
            already_included.append(key)
            print(f"✓ {feed['name']:<45} (key match)")
    
    print()
    print(f"Total already included: {len(already_included)}")
    print()
    
    # Test feeds that are not included
    missing_feeds = {k: v for k, v in VENDOR_FEEDS.items() if k not in already_included}
    
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
        print(f"✓ {r['name']:<45} [{r['items_found']} items]")
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
            print(f"✗ {r['name']:<45} [{r['status']}]")
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
    print(f"  Total feeds tested: {len(VENDOR_FEEDS)}")
    print("=" * 80)


if __name__ == '__main__':
    asyncio.run(main())
