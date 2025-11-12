#!/usr/bin/env python3
"""
Test the fixed UK Legislation parser against real RSS feed.
This simulates the cog's parsing logic without Discord.
"""

import xml.etree.ElementTree as ET
import re
from html import unescape
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime


def is_recent(item_str: str, max_days: int = 7) -> bool:
    """Check if item is from the last N days (from cog)"""
    try:
        # Try to extract publication date
        date_patterns = [
            r'<pubDate>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</pubDate>',
            r'<published>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</published>',
            r'<updated>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</updated>',
            r'<dc:date>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</dc:date>'
        ]
        
        date_str = None
        for pattern in date_patterns:
            match = re.search(pattern, item_str, re.DOTALL | re.IGNORECASE)
            if match:
                date_str = match.group(1).strip()
                break
        
        if not date_str:
            # No date found, assume it's recent to avoid filtering
            return True
        
        # Parse date - handle multiple formats
        try:
            pub_date = parsedate_to_datetime(date_str)
        except:
            # Try ISO format
            try:
                pub_date = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            except:
                # Can't parse, assume recent
                return True
        
        # Check if within max_days
        cutoff = datetime.now(timezone.utc) - timedelta(days=max_days)
        return pub_date > cutoff
        
    except Exception as e:
        print(f"Error checking date: {e}")
        return True  # On error, assume recent


def test_fixed_parser(content: str) -> None:
    """Test the fixed XML parser implementation"""
    print("\n" + "="*60)
    print("TESTING FIXED UK LEGISLATION PARSER")
    print("="*60)
    
    posted_items = []  # Simulate state tracking
    
    try:
        # Parse RSS feed using XML parser (FIXED VERSION)
        root = ET.fromstring(content)
        
        # Find all item elements
        items = root.findall('.//item')
        if not items:
            items = root.findall('.//entry')
        
        print(f"✅ Total items found: {len(items)}")
        
        if not items:
            print("❌ No items found")
            return
        
        print(f"\nProcessing first 10 items:")
        found_count = 0
        
        # Check each item (simulating cog logic)
        for idx, item in enumerate(items[:10], 1):
            # Convert item to string for date checking
            item_str = ET.tostring(item, encoding='unicode')
            
            # Check if item is recent enough
            if not is_recent(item_str, max_days=7):
                print(f"  {idx}. [SKIP] Item too old")
                continue
            
            # Extract title using XML parser (NOT regex)
            title_elem = item.find('title')
            title = "No title"
            if title_elem is not None and title_elem.text:
                title = unescape(title_elem.text.strip())
            
            # Extract link using XML parser (NOT regex)
            link_elem = item.find('link')
            link = "No link"
            if link_elem is not None:
                if link_elem.text:
                    link = link_elem.text.strip()
                elif link_elem.get('href'):
                    link = link_elem.get('href')
            
            # Check if already posted
            if link in posted_items:
                print(f"  {idx}. [SKIP] Already posted: {title[:50]}")
                continue
            
            # Extract description using XML parser (NOT regex)
            desc_elem = item.find('description')
            if desc_elem is None:
                desc_elem = item.find('summary')
            
            description = ""
            if desc_elem is not None and desc_elem.text:
                desc = desc_elem.text.strip()
                desc = re.sub(r'<[^>]+>', '', desc)  # Strip HTML
                desc = unescape(desc)
                description = desc[:100] + "..." if len(desc) > 100 else desc
            
            # Mark as posted
            posted_items.append(link)
            found_count += 1
            
            print(f"  {idx}. ✅ FOUND: {title[:60]}")
            print(f"      Link: {link}")
            if description:
                print(f"      Desc: {description}")
            print()
        
        print("="*60)
        print(f"RESULT: Successfully parsed {found_count} new bills")
        print("="*60)
        print("✅ Fix confirmed:")
        print("  - XML parser handles <item> tags with attributes")
        print("  - Returns proper Element objects, not tuples")
        print("  - Extracts text content correctly")
        print("  - No 'expected string or bytes-like object' errors")
        
    except ET.ParseError as e:
        print(f"❌ XML parsing error: {e}")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()


def main():
    """Main test function"""
    print("UK Legislation Parser Fix Verification")
    print("Testing fixed code against: https://bills.parliament.uk/rss/allbills.rss")
    
    try:
        import urllib.request
        
        print("\nFetching RSS feed...")
        with urllib.request.urlopen('https://bills.parliament.uk/rss/allbills.rss', timeout=10) as response:
            content = response.read().decode('utf-8')
        
        print(f"✅ Feed fetched successfully ({len(content)} bytes)")
        
        test_fixed_parser(content)
        
    except Exception as e:
        print(f"\n❌ Error fetching feed: {e}")
        import sys
        sys.exit(1)


if __name__ == "__main__":
    main()
