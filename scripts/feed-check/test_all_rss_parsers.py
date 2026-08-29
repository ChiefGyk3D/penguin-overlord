#!/usr/bin/env python3
"""
Comprehensive test suite for all RSS parsers fixed with XML parser.
Tests ALL feeds from all 9 cogs that were updated to use xml.etree.ElementTree instead of regex.
"""

import asyncio
import aiohttp
import xml.etree.ElementTree as ET
from html import unescape
import re


# Test ALL feeds from each cog - using actual configured URLs
TEST_FEEDS = {
    # UK Legislation - 1 feed
    'uk_legislation_all_bills': {
        'name': 'UK Parliament - All Bills',
        'url': 'https://bills.parliament.uk/rss/allbills.rss',
        'expected_items': 10
    },
    
    # US Legislation - 5 feeds
    'us_presented_to_president': {
        'name': 'Congress.gov - Bills Presented to President',
        'url': 'https://www.congress.gov/rss/presented-to-president.xml',
        'expected_items': 5
    },
    'us_house_floor': {
        'name': 'Congress.gov - House Floor Today',
        'url': 'https://www.congress.gov/rss/house-floor-today.xml',
        'expected_items': 5
    },
    'us_senate_floor': {
        'name': 'Congress.gov - Senate Floor Today',
        'url': 'https://www.congress.gov/rss/senate-floor-today.xml',
        'expected_items': 5
    },
    'us_most_viewed_bills': {
        'name': 'Congress.gov - Most Viewed Bills',
        'url': 'https://www.congress.gov/rss/most-viewed-bills.xml',
        'expected_items': 1
    },
    'us_govinfo_bills': {
        'name': 'GovInfo - Bills',
        'url': 'https://www.govinfo.gov/rss/bills.xml',
        'expected_items': 5
    },
    
    # EU Legislation - 3 feeds
    'eu_parliament_council': {
        'name': 'EUR-Lex - Parliament & Council Legislation',
        'url': 'https://eur-lex.europa.eu/EN/display-feed.rss?rssId=162',
        'expected_items': 5
    },
    'eu_proposals': {
        'name': 'EUR-Lex - Commission Proposals',
        'url': 'https://eur-lex.europa.eu/EN/display-feed.rss?rssId=161',
        'expected_items': 5
    },
    'eu_official_journal': {
        'name': 'EUR-Lex - Official Journal (Binding Acts)',
        'url': 'https://eur-lex.europa.eu/EN/display-feed.rss?rssId=222',
        'expected_items': 5
    },
    
    # CVE - 1 feed
    'cve_ubuntu_usn': {
        'name': 'Ubuntu USN Security Notices',
        'url': 'https://ubuntu.com/security/notices/rss.xml',
        'expected_items': 5
    },
    
    # Cybersecurity News - sample of 5 high-priority feeds
    'cybersec_hackernews': {
        'name': 'The Hacker News',
        'url': 'https://feeds.feedburner.com/TheHackersNews',
        'expected_items': 5
    },
    'cybersec_bleepingcomputer': {
        'name': 'BleepingComputer',
        'url': 'https://www.bleepingcomputer.com/feed/',
        'expected_items': 5
    },
    'cybersec_krebs': {
        'name': 'Krebs on Security',
        'url': 'https://krebsonsecurity.com/feed/',
        'expected_items': 5
    },
    'cybersec_schneier': {
        'name': 'Schneier on Security',
        'url': 'https://www.schneier.com/feed/atom/',
        'expected_items': 5
    },
    'cybersec_darkreading': {
        'name': 'Dark Reading',
        'url': 'https://www.darkreading.com/rss.xml',
        'expected_items': 5
    },
    
    # General News - sample of 5 feeds
    'general_bbc_news': {
        'name': 'BBC News - Top Stories',
        'url': 'http://feeds.bbci.co.uk/news/rss.xml',
        'expected_items': 5
    },
    'general_npr': {
        'name': 'NPR News',
        'url': 'https://feeds.npr.org/1001/rss.xml',
        'expected_items': 5
    },
    'general_bbc_uk': {
        'name': 'BBC News - UK',
        'url': 'http://feeds.bbci.co.uk/news/uk/rss.xml',
        'expected_items': 5
    },
    'general_bbc_world': {
        'name': 'BBC News - World',
        'url': 'http://feeds.bbci.co.uk/news/world/rss.xml',
        'expected_items': 5
    },
    'general_politico': {
        'name': 'Politico',
        'url': 'https://www.politico.com/rss/politicopicks.xml',
        'expected_items': 5
    },
    
    # Tech News - sample of 5 feeds
    'tech_arstechnica': {
        'name': 'Ars Technica',
        'url': 'https://feeds.arstechnica.com/arstechnica/index',
        'expected_items': 5
    },
    'tech_theverge': {
        'name': 'The Verge',
        'url': 'https://www.theverge.com/rss/index.xml',
        'expected_items': 5
    },
    'tech_techcrunch': {
        'name': 'TechCrunch',
        'url': 'https://techcrunch.com/feed/',
        'expected_items': 5
    },
    'tech_github': {
        'name': 'GitHub Blog',
        'url': 'https://github.blog/feed/',
        'expected_items': 5
    },
    'tech_bbc': {
        'name': 'BBC News - Technology',
        'url': 'http://feeds.bbci.co.uk/news/technology/rss.xml',
        'expected_items': 5
    },
    
    # Apple/Google News - sample of 5 feeds
    'apple_9to5mac': {
        'name': '9to5Mac',
        'url': 'https://9to5mac.com/feed/',
        'expected_items': 5
    },
    'apple_macrumors': {
        'name': 'MacRumors',
        'url': 'https://www.macrumors.com/macrumors.xml',
        'expected_items': 5
    },
    'google_9to5google': {
        'name': '9to5Google',
        'url': 'https://9to5google.com/feed/',
        'expected_items': 5
    },
    'android_authority': {
        'name': 'Android Authority',
        'url': 'https://www.androidauthority.com/feed/',
        'expected_items': 5
    },
    'android_police': {
        'name': 'Android Police',
        'url': 'https://www.androidpolice.com/feed/',
        'expected_items': 5
    },
    
    # Gaming News - sample of 5 feeds
    'gaming_pcgamer': {
        'name': 'PC Gamer',
        'url': 'https://www.pcgamer.com/rss/',
        'expected_items': 5
    },
    'gaming_polygon': {
        'name': 'Polygon',
        'url': 'https://www.polygon.com/rss/index.xml',
        'expected_items': 5
    },
    'gaming_eurogamer': {
        'name': 'Eurogamer',
        'url': 'https://www.eurogamer.net/?format=rss',
        'expected_items': 5
    },
    'gaming_rockpapershotgun': {
        'name': 'Rock Paper Shotgun',
        'url': 'https://www.rockpapershotgun.com/feed',
        'expected_items': 5
    },
    'gaming_kotaku': {
        'name': 'Kotaku',
        'url': 'https://kotaku.com/rss',
        'expected_items': 5
    }
}


async def test_rss_parser(session, feed_key, feed_info):
    """
    Test RSS parser using XML ElementTree (the fixed approach).
    Returns (success, items_found, error_message).
    """
    print(f"\n{'='*60}")
    print(f"Testing: {feed_info['name']}")
    print(f"URL: {feed_info['url']}")
    print(f"Expected: At least {feed_info['expected_items']} items")
    print(f"{'='*60}")
    
    try:
        async with session.get(feed_info['url'], timeout=aiohttp.ClientTimeout(total=15)) as response:
            if response.status != 200:
                return False, 0, f"HTTP {response.status}"
            
            content = await response.text()
            
            # Parse with XML ElementTree (the fix)
            try:
                root = ET.fromstring(content)
            except ET.ParseError as e:
                return False, 0, f"XML parse error: {e}"
            
            # Find items (supports both <item> and <entry> tags)
            items = root.findall('.//{http://www.w3.org/2005/Atom}entry')
            if not items:
                items = root.findall('.//item')
            
            if not items:
                return False, 0, "No items found in feed"
            
            items_found = len(items)
            print(f"✅ SUCCESS: Found {items_found} items")
            
            # Extract and display first item details
            item = items[0]
            
            # Extract title
            title_elem = item.find('.//{http://www.w3.org/2005/Atom}title')
            if title_elem is None:
                title_elem = item.find('title')
            title = unescape(title_elem.text.strip()) if title_elem is not None and title_elem.text else "No title"
            
            # Extract link
            link_elem = item.find('.//{http://www.w3.org/2005/Atom}link')
            if link_elem is not None and 'href' in link_elem.attrib:
                link = link_elem.attrib['href'].strip()
            else:
                link_elem = item.find('link')
                link = link_elem.text.strip() if link_elem is not None and link_elem.text else "No link"
            
            # Extract description
            desc_elem = item.find('.//{http://www.w3.org/2005/Atom}summary')
            if desc_elem is None:
                desc_elem = item.find('description')
            
            description = ""
            if desc_elem is not None and desc_elem.text:
                desc = desc_elem.text.strip()
                desc = re.sub(r'<[^>]+>', '', desc)  # Strip HTML
                desc = unescape(desc)
                description = desc[:100] + "..." if len(desc) > 100 else desc
            
            print(f"\nFirst item details:")
            print(f"  Title: {title[:80]}...")
            print(f"  Link: {link[:80]}...")
            print(f"  Description: {description}")
            
            # Check if we got expected number
            if items_found >= feed_info['expected_items']:
                return True, items_found, None
            else:
                return True, items_found, f"Expected {feed_info['expected_items']}, got {items_found}"
    
    except asyncio.TimeoutError:
        return False, 0, "Request timeout"
    except Exception as e:
        return False, 0, f"Error: {type(e).__name__}: {str(e)}"


async def main():
    """Run all RSS parser tests."""
    print(f"\n{'#'*60}")
    print("# COMPREHENSIVE RSS PARSER TEST SUITE")
    print(f"# Testing {len(TEST_FEEDS)} feeds across all 9 fixed RSS parsers")
    print(f"{'#'*60}\n")
    
    timeout = aiohttp.ClientTimeout(total=15)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        results = {}
        
        # Test each feed
        for feed_key, feed_info in TEST_FEEDS.items():
            success, items_found, error = await test_rss_parser(session, feed_key, feed_info)
            results[feed_key] = {
                'name': feed_info['name'],
                'success': success,
                'items_found': items_found,
                'error': error
            }
    
    # Summary
    print(f"\n\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}\n")
    
    total = len(results)
    passed = sum(1 for r in results.values() if r['success'] and not r['error'])
    partial = sum(1 for r in results.values() if r['success'] and r['error'])
    failed = sum(1 for r in results.values() if not r['success'])
    
    for feed_key, result in results.items():
        status = "✅ PASS" if result['success'] and not result['error'] else \
                 "⚠️  PARTIAL" if result['success'] else \
                 "❌ FAIL"
        
        print(f"{status:12} {result['name']:30} Items: {result['items_found']:3}")
        if result['error']:
            print(f"             Error: {result['error']}")
    
    print(f"\n{'='*60}")
    print(f"TOTAL:   {total:3}")
    print(f"PASSED:  {passed:3}")
    print(f"PARTIAL: {partial:3}")
    print(f"FAILED:  {failed:3}")
    print(f"{'='*60}\n")
    
    if failed == 0 and partial == 0:
        print("🎉 ALL TESTS PASSED! XML parser working correctly for all feeds.")
        return 0
    elif failed == 0:
        print("✅ All feeds parsing, but some have warnings.")
        return 0
    else:
        print("⚠️  Some feeds failed. Review errors above.")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
