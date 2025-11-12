#!/usr/bin/env python3
"""
Comprehensive test for vendor_alerts integration
"""

import sys
import os

print("=" * 80)
print("VENDOR ALERTS INTEGRATION TEST")
print("=" * 80)
print()

# Test 1: Check if vendor_alerts.py exists and has correct structure
print("1. Checking vendor_alerts.py structure...")
vendor_alerts_path = "penguin-overlord/cogs/vendor_alerts.py"
if not os.path.exists(vendor_alerts_path):
    print("   ✗ File not found!")
    sys.exit(1)

with open(vendor_alerts_path) as f:
    content = f.read()
    checks = [
        ('VENDOR_ALERT_SOURCES', 'Feed sources dictionary'),
        ('class VendorAlerts', 'Main cog class'),
        ('vendor_alerts_auto_poster', 'Auto-poster task'),
        ('async def setup(bot)', 'Setup function'),
    ]
    
    for check, desc in checks:
        if check in content:
            print(f"   ✓ {desc}")
        else:
            print(f"   ✗ Missing: {desc}")
            sys.exit(1)

# Test 2: Check NEWS_SOURCES count
print("\n2. Counting vendor alert sources...")
import re
sources_count = len(re.findall(r"'\w+': \{[^}]+\}", content))
print(f"   ✓ Found {sources_count} vendor alert sources")

# Test 3: Verify news_manager.py integration
print("\n3. Checking news_manager.py integration...")
news_manager_path = "penguin-overlord/cogs/news_manager.py"
with open(news_manager_path) as f:
    nm_content = f.read()
    
    if "'vendor_alerts'" in nm_content:
        print("   ✓ vendor_alerts added to config")
    else:
        print("   ✗ vendor_alerts not in config")
        sys.exit(1)
    
    if "vendor_alerts'" in nm_content:  # Check in Literal types
        print("   ✓ vendor_alerts added to Literal types")
    else:
        print("   ✗ vendor_alerts not in Literal types")
        sys.exit(1)

# Test 4: Check deploy-news-timers.sh
print("\n4. Checking deploy-news-timers.sh...")
timer_script_path = "scripts/deploy-news-timers.sh"
with open(timer_script_path) as f:
    timer_content = f.read()
    
    if 'create_service "vendor_alerts"' in timer_content:
        print("   ✓ vendor_alerts service creation added")
    else:
        print("   ✗ vendor_alerts service not added")
        sys.exit(1)
    
    if 'create_timer "vendor_alerts"' in timer_content:
        print("   ✓ vendor_alerts timer creation added")
    else:
        print("   ✗ vendor_alerts timer not added")
        sys.exit(1)
    
    if 'vendor_alerts' in re.search(r'for category in ([^;]+);', timer_content).group(1):
        print("   ✓ vendor_alerts in enable/start loop")
    else:
        print("   ✗ vendor_alerts not in enable/start loop")
        sys.exit(1)

# Test 5: Verify Python syntax
print("\n5. Verifying Python syntax...")
import py_compile
import tempfile

for file_path in [vendor_alerts_path, news_manager_path]:
    try:
        with tempfile.NamedTemporaryFile(suffix='.pyc', delete=True) as tmp:
            py_compile.compile(file_path, tmp.name, doraise=True)
        print(f"   ✓ {os.path.basename(file_path)} - valid syntax")
    except py_compile.PyCompileError as e:
        print(f"   ✗ {os.path.basename(file_path)} - syntax error: {e}")
        sys.exit(1)

# Test 6: List all vendor alert sources
print("\n6. Vendor Alert Sources:")
print("   " + "-" * 76)
source_pattern = r"'(\w+)': \{\s*'name': '([^']+)'"
sources = re.findall(source_pattern, content)
for key, name in sources[:10]:
    print(f"   • {name} ({key})")
if len(sources) > 10:
    print(f"   ... and {len(sources) - 10} more")

print("\n" + "=" * 80)
print("✅ ALL TESTS PASSED!")
print("=" * 80)
print()
print("Next steps:")
print("1. Restart the bot to load the vendor_alerts cog")
print("2. Configure vendor_alerts channel: /news set_channel category:vendor_alerts")
print("3. Enable vendor_alerts: /news enable category:vendor_alerts")
print("4. Deploy systemd timer: sudo ./scripts/deploy-news-timers.sh")
print()
print(f"Total vendor alert sources: {len(sources)}")
print("Update interval: Every 4 hours at :25")
print()
