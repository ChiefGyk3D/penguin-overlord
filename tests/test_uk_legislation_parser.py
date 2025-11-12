#!/usr/bin/env python3
"""
Test script to replicate UK Legislation RSS parsing bug without disrupting Discord.

This script:
1. Fetches the UK Parliament Bills RSS feed
2. Tests the current regex pattern (will fail)
3. Tests the XML parser approach (should work)
"""

import re
import xml.etree.ElementTree as ET
from html import unescape
import sys

def test_regex_parsing(content: str) -> None:
    """Test the current regex-based parsing approach"""
    print("\n" + "="*60)
    print("TEST 1: Current regex pattern (exact <item>)")
    print("="*60)
    
    # Current pattern - will fail with <item xml:version="2.0">
    item_pattern = r'<item>(.*?)</item>'
    items = re.findall(item_pattern, content, re.DOTALL)
    
    print(f"Items found: {len(items)}")
    if not items:
        print("❌ FAIL: No items found - regex expects exact '<item>' but feed has '<item xml:version=\"2.0\">'")
    
    print("\n" + "="*60)
    print("TEST 2: Modified regex pattern (with attributes)")
    print("="*60)
    
    # Modified pattern from bug report - creates tuple
    item_pattern_modified = r'<item(.*?)>(.*?)</item>'
    items_modified = re.findall(item_pattern_modified, content, re.DOTALL)
    
    print(f"Items found: {len(items_modified)}")
    if items_modified:
        print(f"Type of first item: {type(items_modified[0])}")
        if isinstance(items_modified[0], tuple):
            print("❌ FAIL: Returns tuple, not string - will cause 'expected string or bytes-like object' error")
            print(f"Tuple structure: {items_modified[0][:2] if len(items_modified[0]) > 2 else items_modified[0]}")


def test_xml_parsing(content: str) -> None:
    """Test proper XML parsing approach"""
    print("\n" + "="*60)
    print("TEST 3: XML parser (proper solution)")
    print("="*60)
    
    try:
        # Parse as XML
        root = ET.fromstring(content)
        
        # Find all item elements (handle namespaces if present)
        items = root.findall('.//item')
        
        print(f"Items found: {len(items)}")
        
        if items:
            print("✅ SUCCESS: XML parser handles attributes correctly")
            print(f"\nFirst 3 bills:")
            
            for i, item in enumerate(items[:3], 1):
                # Extract title
                title_elem = item.find('title')
                title = title_elem.text if title_elem is not None else "No title"
                title = unescape(title.strip()) if title else "No title"
                
                # Extract link
                link_elem = item.find('link')
                link = link_elem.text if link_elem is not None else "No link"
                link = link.strip() if link else "No link"
                
                # Extract description
                desc_elem = item.find('description')
                description = ""
                if desc_elem is not None and desc_elem.text:
                    desc = desc_elem.text.strip()
                    desc = re.sub(r'<[^>]+>', '', desc)  # Strip HTML
                    desc = unescape(desc)
                    description = desc[:100] + "..." if len(desc) > 100 else desc
                
                print(f"\n{i}. {title}")
                print(f"   Link: {link}")
                if description:
                    print(f"   Description: {description}")
                
        else:
            print("❌ No items found with XML parser")
            
    except ET.ParseError as e:
        print(f"❌ XML parsing error: {e}")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")


def main():
    """Main test function"""
    print("UK Legislation RSS Parser Test")
    print("Testing against: https://bills.parliament.uk/rss/allbills.rss")
    
    # Fetch the RSS feed
    try:
        import urllib.request
        
        print("\nFetching RSS feed...")
        with urllib.request.urlopen('https://bills.parliament.uk/rss/allbills.rss', timeout=10) as response:
            content = response.read().decode('utf-8')
        
        print(f"✅ Feed fetched successfully ({len(content)} bytes)")
        
        # Show a snippet of the feed to see the item tag format
        print("\n" + "="*60)
        print("Feed snippet (first <item> tag):")
        print("="*60)
        match = re.search(r'<item[^>]*>.*?</item>', content[:5000], re.DOTALL)
        if match:
            snippet = match.group(0)
            # Show just the opening tag and title
            lines = snippet.split('\n')[:5]
            print('\n'.join(lines))
            print("...")
        
        # Run tests
        test_regex_parsing(content)
        test_xml_parsing(content)
        
        print("\n" + "="*60)
        print("CONCLUSION")
        print("="*60)
        print("The current regex pattern fails because the UK Bills feed uses:")
        print('  <item xml:version="2.0"> (with attributes)')
        print("not:")
        print('  <item> (exact match)')
        print("\nThe XML parser approach is the correct solution as it:")
        print("  ✓ Handles attributes automatically")
        print("  ✓ Properly parses nested tags")
        print("  ✓ Returns string content, not tuples")
        print("  ✓ Is more maintainable")
        
    except Exception as e:
        print(f"\n❌ Error fetching feed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
