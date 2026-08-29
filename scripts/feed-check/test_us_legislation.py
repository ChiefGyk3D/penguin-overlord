#!/usr/bin/env python3
"""Test US Legislation feeds"""
import sys
from pathlib import Path

# Add parent directory to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "penguin-overlord"))

import asyncio
import aiohttp

# Import sources
from cogs.us_legislation import LEGISLATION_SOURCES

async def test_feeds():
    """Test that all US legislation feeds are accessible"""
    print("🧪 Testing US Legislation Feeds")
    print("=" * 60)
    
    async with aiohttp.ClientSession() as session:
        for key, source in LEGISLATION_SOURCES.items():
            print(f"\n{source['emoji']} Testing: {source['name']}")
            print(f"   URL: {source['url']}")
            
            try:
                async with session.get(source['url'], timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        content = await response.text()
                        # Check if it's valid RSS/XML
                        if '<rss' in content.lower() or '<feed' in content.lower():
                            # Count items
                            item_count = content.count('<item>') or content.count('<entry>')
                            print(f"   ✅ OK - {response.status} ({item_count} items)")
                        else:
                            print(f"   ⚠️  Response received but may not be RSS/XML")
                    else:
                        print(f"   ❌ HTTP {response.status}")
            except asyncio.TimeoutError:
                print(f"   ❌ Timeout")
            except Exception as e:
                print(f"   ❌ Error: {e}")
    
    print("\n" + "=" * 60)
    print("✅ Test complete!")

if __name__ == '__main__':
    asyncio.run(test_feeds())
