#!/usr/bin/env python3
"""Test the OptimizedNewsFetcher directly"""
import sys
from pathlib import Path

# Add parent directory to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "penguin-overlord"))

import asyncio
from utils.news_fetcher import OptimizedNewsFetcher

async def test_fetcher():
    """Test fetching a single feed"""
    print("🧪 Testing OptimizedNewsFetcher...")
    
    # Create fetcher with test cache
    fetcher = OptimizedNewsFetcher(cache_file='penguin-overlord/data/test_cache.json')
    fetcher.set_concurrency_limit(3)
    
    # Test with a reliable RSS feed
    test_feeds = {
        'ars_test': {
            'name': 'Ars Technica',
            'url': 'https://feeds.arstechnica.com/arstechnica/index'
        },
        'thehackernews': {
            'name': 'The Hacker News',
            'url': 'https://feeds.feedburner.com/TheHackersNews'
        },
    }
    
    print(f"\n📡 Fetching {len(test_feeds)} test feeds...")
    print("=" * 60)
    
    try:
        # First run - should fetch fresh
        print("\n🔄 First run (fresh fetch)...")
        items = await fetcher.fetch_multiple_feeds(
            test_feeds,
            enabled_sources=['ars_test', 'thehackernews'],  # All enabled
            use_cache=True
        )
        
        print(f"\n✅ Found {len(items)} new items:")
        for title, link, desc, guid, source in items[:3]:  # Show first 3
            print(f"\n  📰 {source}")
            print(f"     Title: {title[:70]}...")
            print(f"     Link: {link[:80]}...")
            print(f"     GUID: {guid[:50]}...")
        
        # Second run - should use cache (304 responses)
        print("\n\n🔄 Second run (should use ETag cache)...")
        items2 = await fetcher.fetch_multiple_feeds(
            test_feeds,
            enabled_sources=['ars_test', 'thehackernews'],
            use_cache=True
        )
        
        print(f"✅ Found {len(items2)} new items (should be 0 or very few)")
        
        # Check cache statistics
        print("\n\n📊 Cache Statistics:")
        print(f"   ETags cached: {len(fetcher.feed_cache.get('etags', {}))}")
        print(f"   Last-Modified cached: {len(fetcher.feed_cache.get('last_modified', {}))}")
        print(f"   GUIDs tracked: {len(fetcher.feed_cache.get('last_guids', {}))}")
        
        # Close session properly
        if fetcher.session:
            await fetcher.session.close()
        
        print("\n✅ Test completed successfully!")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    asyncio.run(test_fetcher())
