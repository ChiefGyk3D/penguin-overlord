#!/usr/bin/env python3
"""
Test vendor service alert feeds and find missing URLs
"""

import asyncio
import aiohttp
import xml.etree.ElementTree as ET
import json

# Known vendor service alert feeds
VENDOR_ALERT_FEEDS = {
    # Zscaler
    'zscaler_maintenance': {'name': 'Zscaler Maintenance', 'url': 'https://trust.zscaler.com/rss-feed/maintenance?_format=json', 'type': 'json'},
    'zscaler_incidents': {'name': 'Zscaler Incidents', 'url': 'https://trust.zscaler.com/rss-feed/incidents?_format=json', 'type': 'json'},
    'zscaler_advisories': {'name': 'Zscaler Advisories', 'url': 'https://trust.zscaler.com/rss-feed/advisories?_format=json', 'type': 'json'},
    'zscaler_urlcat': {'name': 'Zscaler URL Category', 'url': 'https://trust.zscaler.com/rss-feed/url-category-notification?_format=json', 'type': 'json'},
    'zscaler_cloudapp': {'name': 'Zscaler Cloud App', 'url': 'https://trust.zscaler.com/rss-feed/cloud-app?_format=json', 'type': 'json'},
    
    # Avalor (Zscaler Risk 360)
    'avalor': {'name': 'Avalor/Zscaler Risk 360', 'url': 'https://avalorstatus.statuspage.io/history.atom', 'type': 'atom'},
    
    # Datadog regions
    'datadog_us1': {'name': 'Datadog US-1', 'url': 'https://status.datadoghq.com/history.atom', 'type': 'atom'},
    'datadog_us3': {'name': 'Datadog US-3', 'url': 'https://status.us3.datadoghq.com/history.atom', 'type': 'atom'},
    'datadog_us5': {'name': 'Datadog US-5', 'url': 'https://status.us5.datadoghq.com/history.atom', 'type': 'atom'},
    'datadog_eu': {'name': 'Datadog EU', 'url': 'https://status.datadoghq.eu/history.atom', 'type': 'atom'},
    'datadog_ap1': {'name': 'Datadog AP-1', 'url': 'https://status.ap1.datadoghq.com/history.atom', 'type': 'atom'},
    'datadog_gov': {'name': 'Datadog GovCloud', 'url': 'https://status.ddog-gov.com/history.atom', 'type': 'atom'},
    'datadog_ap2': {'name': 'Datadog AP-2', 'url': 'https://status.ap2.datadoghq.com/history.atom', 'type': 'atom'},
    
    # Microsoft Azure
    'azure': {'name': 'Microsoft Azure', 'url': 'https://rssfeed.azure.status.microsoft/en-us/status/feed/', 'type': 'rss'},
    
    # Okta
    'okta': {'name': 'Okta', 'url': 'https://feeds.feedburner.com/OktaTrustRSS', 'type': 'rss'},
    
    # JumpCloud
    'jumpcloud': {'name': 'JumpCloud', 'url': 'https://status.jumpcloud.com/history.atom', 'type': 'atom'},
    
    # Duo
    'duo': {'name': 'Duo', 'url': 'https://status.duo.com/history.atom', 'type': 'atom'},
    
    # Delinea
    'delinea': {'name': 'Delinea', 'url': 'https://status.delinea.com/history.atom', 'type': 'atom'},
    
    # Doppler
    'doppler': {'name': 'Doppler', 'url': 'https://www.dopplerstatus.com/history.atom', 'type': 'atom'},
    
    # Atlassian products
    'atlassian_jira': {'name': 'Atlassian Jira Software', 'url': 'https://jira-software.status.atlassian.com/history.atom', 'type': 'atom'},
    'atlassian_jsm': {'name': 'Atlassian Jira Service Management', 'url': 'https://jira-service-management.status.atlassian.com/history.atom', 'type': 'atom'},
    'atlassian_jwm': {'name': 'Atlassian Jira Work Management', 'url': 'https://jira-work-management.status.atlassian.com/history.atom', 'type': 'atom'},
    'atlassian_jpd': {'name': 'Atlassian Jira Product Discovery', 'url': 'https://jira-product-discovery.status.atlassian.com/history.atom', 'type': 'atom'},
    'atlassian_confluence': {'name': 'Atlassian Confluence', 'url': 'https://confluence.status.atlassian.com/history.atom', 'type': 'atom'},
    'atlassian_bitbucket': {'name': 'Atlassian Bitbucket', 'url': 'https://bitbucket.status.atlassian.com/history.atom', 'type': 'atom'},
    'atlassian_trello': {'name': 'Atlassian Trello', 'url': 'https://trello.status.atlassian.com/history.atom', 'type': 'atom'},
    'atlassian_opsgenie': {'name': 'Atlassian Opsgenie', 'url': 'https://opsgenie.status.atlassian.com/history.atom', 'type': 'atom'},
    
    # GitHub
    'github': {'name': 'GitHub', 'url': 'https://www.githubstatus.com/history.atom', 'type': 'atom'},
    
    # GitLab
    'gitlab': {'name': 'GitLab', 'url': 'https://status.gitlab.com/pages/5b36dc6502d06804c08349f7/rss', 'type': 'rss'},
    
    # Wiz
    'wiz_status': {'name': 'Wiz', 'url': 'https://status.wiz.io/history.atom', 'type': 'atom'},
}

# Vendors needing URL lookup
MISSING_URLS = [
    'CrowdStrike Status',
    'Microsoft Office 365',
    'Amazon Web Services (AWS)',
    'Proofpoint',
    'Mimecast',
    'Tenable'
]


async def test_json_feed(session, feed_key, feed_data):
    """Test a JSON feed"""
    try:
        async with session.get(feed_data['url'], timeout=aiohttp.ClientTimeout(total=15)) as response:
            if response.status == 200:
                try:
                    data = await response.json()
                    # Check if it has items/entries
                    items_count = 0
                    if isinstance(data, list):
                        items_count = len(data)
                    elif isinstance(data, dict):
                        items_count = len(data.get('items', data.get('entries', [])))
                    
                    return {
                        'status': 'working',
                        'feed_key': feed_key,
                        'name': feed_data['name'],
                        'url': feed_data['url'],
                        'items_count': items_count
                    }
                except json.JSONDecodeError as e:
                    return {
                        'status': 'error',
                        'feed_key': feed_key,
                        'name': feed_data['name'],
                        'url': feed_data['url'],
                        'error': f'JSON decode error: {str(e)}'
                    }
            else:
                return {
                    'status': 'error',
                    'feed_key': feed_key,
                    'name': feed_data['name'],
                    'url': feed_data['url'],
                    'error': f'HTTP {response.status}'
                }
    except Exception as e:
        return {
            'status': 'error',
            'feed_key': feed_key,
            'name': feed_data['name'],
            'url': feed_data['url'],
            'error': str(e)
        }


async def test_xml_feed(session, feed_key, feed_data):
    """Test an RSS/Atom feed"""
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
                            'items_count': len(items),
                            'first_title': title[:60] + '...' if title and len(title) > 60 else title
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
    except Exception as e:
        return {
            'status': 'error',
            'feed_key': feed_key,
            'name': feed_data['name'],
            'url': feed_data['url'],
            'error': str(e)
        }


async def lookup_missing_urls(session):
    """Try to find status page URLs for missing vendors"""
    common_patterns = [
        'status.{vendor}.com/history.atom',
        '{vendor}status.com/history.atom',
        'status.{vendor}.com/history.rss',
        'status.{vendor}.com/api/v2/incidents.rss',
    ]
    
    vendor_domains = {
        'CrowdStrike': 'crowdstrike',
        'AWS': 'aws.amazon',
        'Proofpoint': 'proofpoint',
        'Mimecast': 'mimecast',
        'Tenable': 'tenable',
        'Office 365': 'office365'
    }
    
    results = {}
    
    for vendor, domain in vendor_domains.items():
        print(f"Looking up {vendor}...")
        found = False
        
        for pattern in common_patterns:
            url = f"https://{pattern.format(vendor=domain)}"
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        results[vendor] = url
                        print(f"  ✓ Found: {url}")
                        found = True
                        break
            except:
                pass
        
        if not found:
            results[vendor] = None
            print(f"  ✗ Not found with common patterns")
    
    return results


async def test_all_feeds():
    """Test all vendor alert feeds"""
    print("Testing vendor service alert feeds...\n")
    
    async with aiohttp.ClientSession() as session:
        # Test known feeds
        tasks = []
        for feed_key, feed_data in VENDOR_ALERT_FEEDS.items():
            if feed_data['type'] == 'json':
                tasks.append(test_json_feed(session, feed_key, feed_data))
            else:
                tasks.append(test_xml_feed(session, feed_key, feed_data))
        
        results = await asyncio.gather(*tasks)
        
        # Lookup missing URLs
        print("\n" + "=" * 80)
        print("LOOKING UP MISSING VENDOR URLs")
        print("=" * 80)
        missing = await lookup_missing_urls(session)
    
    # Categorize results
    working = [r for r in results if r['status'] == 'working']
    broken = [r for r in results if r['status'] == 'error']
    
    # Display results
    print("\n" + "=" * 80)
    print(f"WORKING FEEDS: {len(working)}/{len(VENDOR_ALERT_FEEDS)}")
    print("=" * 80)
    for feed in working:
        print(f"✓ {feed['name']}")
        print(f"  Key: {feed['feed_key']}")
        print(f"  Items: {feed['items_count']}")
        if feed.get('first_title'):
            print(f"  Latest: {feed['first_title']}")
        print()
    
    if broken:
        print("=" * 80)
        print(f"BROKEN FEEDS: {len(broken)}")
        print("=" * 80)
        for feed in broken:
            print(f"✗ {feed['name']}")
            print(f"  Key: {feed['feed_key']}")
            print(f"  Error: {feed['error']}")
            print()
    
    # Display missing URLs
    print("=" * 80)
    print("MISSING VENDOR URLS")
    print("=" * 80)
    for vendor, url in missing.items():
        if url:
            print(f"✓ {vendor}: {url}")
        else:
            print(f"✗ {vendor}: Need manual lookup")
    
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Total feeds tested: {len(VENDOR_ALERT_FEEDS)}")
    print(f"Working: {len(working)}")
    print(f"Broken: {len(broken)}")
    print(f"Success rate: {len(working)/len(VENDOR_ALERT_FEEDS)*100:.1f}%")
    
    return working, broken


if __name__ == '__main__':
    working, broken = asyncio.run(test_all_feeds())
