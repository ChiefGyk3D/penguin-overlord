#!/usr/bin/env python3
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
Test script to verify Doppler secrets integration.
Run this to check if your secrets are being loaded correctly.
"""

import os
import sys
from pathlib import Path

# Add parent directory to path so we can import from penguin-overlord
sys.path.insert(0, str(Path(__file__).parent / 'penguin-overlord'))

from dotenv import load_dotenv
from utils.secrets import get_secret

# Load .env as fallback
load_dotenv()

def test_secrets():
    """Test secret loading from various sources."""
    print("🐧 Penguin Overlord - Secrets Configuration Test\n")
    print("=" * 60)
    
    # Check for Doppler
    doppler_token = os.getenv('DOPPLER_TOKEN')
    if doppler_token:
        print("✅ DOPPLER_TOKEN found")
        print(f"   Token preview: {doppler_token[:15]}...")
        print(f"   Project: {os.getenv('DOPPLER_PROJECT', 'stream-daemon (default)')}")
        print(f"   Config: {os.getenv('DOPPLER_CONFIG', 'prd (default)')}")
    else:
        print("⚠️  DOPPLER_TOKEN not set (will use .env fallback)")
    
    print()
    
    # Check for other secrets managers
    secrets_manager = os.getenv('SECRETS_MANAGER', 'none')
    if secrets_manager != 'none':
        print(f"📦 Secrets Manager: {secrets_manager.upper()}")
    
    print("\n" + "=" * 60)
    print("\n🔍 Testing Discord Bot Token Retrieval...\n")
    
    # Try to get the Discord bot token
    token = get_secret('DISCORD', 'BOT_TOKEN')
    
    if token:
        print("✅ Successfully retrieved DISCORD_BOT_TOKEN!")
        print(f"   Token preview: {token[:20]}...{token[-5:]}")
        print(f"   Token length: {len(token)} characters")
        
        # Validate token format (basic check)
        if len(token) > 50 and '.' in token:
            print("   Token format looks valid ✓")
        else:
            print("   ⚠️  Token format might be incorrect")
    else:
        print("❌ Could not retrieve DISCORD_BOT_TOKEN")
        print("\n   Troubleshooting:")
        print("   1. If using Doppler:")
        print("      - Set DOPPLER_TOKEN environment variable")
        print("      - Add DISCORD_BOT_TOKEN secret to your Doppler project")
        print("   2. If using .env:")
        print("      - Create .env file with DISCORD_BOT_TOKEN=your_token")
        print("   3. Check that the token exists in your chosen secrets manager")
    
    print("\n" + "=" * 60)
    print("\n📋 Environment Variables:")
    print(f"   DOPPLER_TOKEN: {'✓ Set' if os.getenv('DOPPLER_TOKEN') else '✗ Not set'}")
    print(f"   DISCORD_BOT_TOKEN: {'✓ Set' if os.getenv('DISCORD_BOT_TOKEN') else '✗ Not set'}")
    print(f"   SECRETS_MANAGER: {os.getenv('SECRETS_MANAGER', 'none')}")
    
    print("\n" + "=" * 60)
    
    if token:
        print("\n✅ Configuration is ready! You can start the bot now.")
        print("\nTo start the bot:")
        print("  cd penguin-overlord && python bot.py")
        print("  OR")
        print("  python -m penguin-overlord.bot")
        if doppler_token:
            print("  OR (with Doppler CLI)")
            print("  doppler run -- python bot.py")
        return True
    else:
        print("\n❌ Configuration incomplete. Please set up your secrets.")
        return False

if __name__ == '__main__':
    success = test_secrets()
    sys.exit(0 if success else 1)
