#!/usr/bin/env python3
"""Test UK Legislation RSS parsing with item tags that have attributes"""
import sys
from pathlib import Path

# Add parent directory to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "penguin-overlord"))

import re
from html import unescape

def test_item_parsing_with_attributes():
    """Test that we can parse <item> tags with attributes like rdf:about"""
    print("🧪 Testing UK Legislation Item Parsing")
    print("=" * 60)
    
    # Simulated UK Parliament RSS feed with item tags that have attributes
    test_content = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
  <channel>
    <title>UK Parliament - All Bills</title>
    <item rdf:about="https://bills.parliament.uk/bills/123">
      <title>Test Bill 2024</title>
      <link>https://bills.parliament.uk/bills/123</link>
      <description>This is a test bill description</description>
      <pubDate>Mon, 11 Nov 2024 10:00:00 GMT</pubDate>
    </item>
    <item rdf:about="https://bills.parliament.uk/bills/124">
      <title>Another Test Bill 2024</title>
      <link>https://bills.parliament.uk/bills/124</link>
      <description>Another test bill description</description>
      <pubDate>Mon, 11 Nov 2024 12:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>"""
    
    # Test the pattern used in uk_legislation.py (after fix)
    item_pattern = r'<item(?:\s+[^>]*)?>.*?</item>' if '<item' in test_content else r'<entry(?:\s+[^>]*)?>.*?</entry>'
    items = re.findall(item_pattern, test_content, re.DOTALL)
    
    print(f"\n✓ Found {len(items)} items using pattern: {item_pattern}")
    
    if len(items) != 2:
        print(f"❌ FAILED: Expected 2 items, got {len(items)}")
        return False
    
    # Test extracting data from first item
    item = items[0]
    
    # Extract title
    title_match = re.search(r'<title(?:\s+[^>]*)?>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>', item, re.DOTALL)
    title = unescape(title_match.group(1).strip()) if title_match else "No title"
    
    print(f"\n✓ Title extracted: {title}")
    if title != "Test Bill 2024":
        print(f"❌ FAILED: Expected 'Test Bill 2024', got '{title}'")
        return False
    
    # Extract link
    link_match = re.search(r'<link(?:\s+[^>]*)?>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</link>', item, re.DOTALL)
    if not link_match:
        link_match = re.search(r'<link\s+href="([^"]+)"', item)
    link = link_match.group(1).strip() if link_match else ""
    
    print(f"✓ Link extracted: {link}")
    if link != "https://bills.parliament.uk/bills/123":
        print(f"❌ FAILED: Expected 'https://bills.parliament.uk/bills/123', got '{link}'")
        return False
    
    # Extract description
    desc_match = re.search(r'<description(?:\s+[^>]*)?>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</description>', item, re.DOTALL)
    if desc_match:
        desc = desc_match.group(1).strip()
        desc = re.sub(r'<[^>]+>', '', desc)
        desc = unescape(desc)
    else:
        desc = ""
    
    print(f"✓ Description extracted: {desc}")
    if desc != "This is a test bill description":
        print(f"❌ FAILED: Expected 'This is a test bill description', got '{desc}'")
        return False
    
    # Extract pubDate
    date_match = re.search(r'<pubDate(?:\s+[^>]*)?>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</pubDate>', item, re.DOTALL)
    date_str = date_match.group(1).strip() if date_match else ""
    
    print(f"✓ PubDate extracted: {date_str}")
    if date_str != "Mon, 11 Nov 2024 10:00:00 GMT":
        print(f"❌ FAILED: Expected 'Mon, 11 Nov 2024 10:00:00 GMT', got '{date_str}'")
        return False
    
    print("\n" + "=" * 60)
    print("✅ All tests passed!")
    return True

if __name__ == '__main__':
    success = test_item_parsing_with_attributes()
    sys.exit(0 if success else 1)
