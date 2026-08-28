#!/usr/bin/env python3
"""Test comics cog commands locally"""

import sys
import os
import asyncio
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'penguin-overlord'))

import discord
from discord.ext import commands

# Mock context for testing
class MockMessage:
    def __init__(self):
        self.author = MockUser()
        self.channel = MockChannel()
        self.guild = MockGuild()

class MockUser:
    def __init__(self):
        self.id = 123456789
        self.name = "TestUser"
        
class MockChannel:
    async def send(self, content=None, embed=None):
        if embed:
            print(f"\n📤 Bot would send embed:")
            print(f"   Title: {embed.title}")
            print(f"   URL: {embed.url}")
            if embed.image:
                print(f"   Image: {embed.image.url[:80]}...")
            if embed.footer:
                print(f"   Footer: {embed.footer.text[:80]}...")
        else:
            print(f"\n📤 Bot response: {content}")

class MockGuild:
    def __init__(self):
        self.id = 987654321

async def test_comic_command():
    """Test the comic command"""
    print("="*60)
    print("Testing Comics Cog Commands")
    print("="*60)
    
    # Create bot
    intents = discord.Intents.default()
    intents.message_content = True
    bot = commands.Bot(command_prefix='!', intents=intents)
    bot.owner_id = 123456789
    
    # Load comics cog
    try:
        await bot.load_extension('cogs.comics')
        print("✅ Comics cog loaded\n")
    except Exception as e:
        print(f"❌ Failed to load comics cog: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # Get the cog
    comics_cog = bot.get_cog('Comics')
    if not comics_cog:
        print("❌ Comics cog not found!")
        return False
    
    print(f"✅ Comics cog found: {comics_cog}\n")
    
    # List commands
    print("Commands registered:")
    for cmd in comics_cog.get_commands():
        print(f"  !{cmd.name}")
    print()
    
    # Test session initialization
    print("Testing session initialization...")
    try:
        await comics_cog._ensure_session()
        print(f"✅ Session created: {comics_cog.session}")
        print(f"✅ Session closed: {comics_cog.session.closed}\n")
    except Exception as e:
        print(f"❌ Session initialization failed: {e}\n")
        import traceback
        traceback.print_exc()
        return False
    
    # Test fetching comics
    print("Testing comic fetching...\n")
    
    # Test XKCD
    print("1. Testing XKCD fetch...")
    try:
        xkcd = await comics_cog._fetch_xkcd()
        if xkcd:
            print(f"   ✅ Success: {xkcd['title']}")
        else:
            print(f"   ❌ Failed to fetch")
    except Exception as e:
        print(f"   ❌ Error: {e}")
        import traceback
        traceback.print_exc()
    
    # Test Joy of Tech
    print("\n2. Testing Joy of Tech fetch...")
    try:
        jot = await comics_cog._fetch_joyoftech()
        if jot:
            print(f"   ✅ Success: {jot['title']}")
        else:
            print(f"   ❌ Failed to fetch")
    except Exception as e:
        print(f"   ❌ Error: {e}")
        import traceback
        traceback.print_exc()
    
    # Test TurnOff
    print("\n3. Testing TurnOff fetch...")
    try:
        turnoff = await comics_cog._fetch_turnoff()
        if turnoff:
            print(f"   ✅ Success: {turnoff['title']}")
        else:
            print(f"   ❌ Failed to fetch")
    except Exception as e:
        print(f"   ❌ Error: {e}")
        import traceback
        traceback.print_exc()
    
    # Test actual command invocation
    print("\n" + "="*60)
    print("Testing !comic command invocation")
    print("="*60)
    
    # Create mock context
    msg = MockMessage()
    ctx = await bot.get_context(msg)
    ctx.bot = bot
    ctx.author = msg.author
    ctx.channel = msg.channel
    ctx.guild = msg.guild
    
    # Mock defer
    async def mock_defer():
        print("⏳ Command is processing...")
    ctx.defer = mock_defer
    
    # Mock send
    ctx.send = msg.channel.send
    
    # Try to invoke comic command
    comic_cmd = bot.get_command('comic')
    if comic_cmd:
        print(f"\n✅ Found command: {comic_cmd.name}")
        print(f"Invoking: !comic xkcd\n")
        try:
            await comic_cmd.invoke(ctx, source='xkcd')
        except Exception as e:
            print(f"❌ Command invocation failed: {e}")
            import traceback
            traceback.print_exc()
    else:
        print("❌ comic command not found!")
    
    # Cleanup
    await comics_cog.cog_unload()
    await bot.close()
    
    return True

if __name__ == "__main__":
    try:
        result = asyncio.run(test_comic_command())
        sys.exit(0 if result else 1)
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
