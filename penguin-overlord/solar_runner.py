#!/usr/bin/env python3
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
Solar/Propagation Runner - Standalone execution for systemd timers

Fetches NOAA space weather data and posts to configured Discord channel.
Runs independently of the main bot process for reliability.

Usage:
    python solar_runner.py
    
Environment Variables:
    DISCORD_BOT_TOKEN - Required (supports Doppler via get_secret)
    SOLAR_POST_CHANNEL_ID - Required (channel ID for posting)
"""

import os
import sys
import json
import asyncio
import logging
from pathlib import Path
from datetime import datetime

import discord
import aiohttp
from dotenv import load_dotenv

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load environment
load_dotenv()

# Import secrets utility
from utils.secrets import get_secret

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('solar_runner')


STATE_FILE = Path('data/solar_state.json')


def load_state() -> dict:
    """Load solar state from file."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading solar state: {e}")
    return {}


def save_state(state: dict):
    """Save solar state to file."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(STATE_FILE, 'w') as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        logger.error(f"Error saving solar state: {e}")


async def fetch_solar_data(session: aiohttp.ClientSession) -> dict | None:
    """Fetch solar/propagation data from NOAA."""
    try:
        async with session.get('https://services.swpc.noaa.gov/products/noaa-scales.json', timeout=10) as resp:
            if resp.status == 200:
                data = await resp.json()
                
                # Extract current conditions
                r_scale = 'N/A'
                s_scale = 'N/A'
                g_scale = 'N/A'
                
                if isinstance(data, dict) and '0' in data:
                    current = data['0']
                    r_scale = current.get('R', {}).get('Scale', 'N/A') or 'N/A'
                    s_scale = current.get('S', {}).get('Scale', 'N/A') or 'N/A'
                    g_scale = current.get('G', {}).get('Scale', 'N/A') or 'N/A'
                
                # Fetch SFI and other indices
                async with session.get('https://services.swpc.noaa.gov/text/daily-geomagnetic-indices.txt', timeout=10) as resp2:
                    sfi = 'N/A'
                    a_index = 'N/A'
                    k_index = 'N/A'
                    
                    if resp2.status == 200:
                        text = await resp2.text()
                        lines = text.strip().split('\n')
                        if len(lines) > 1:
                            last_line = lines[-1].split()
                            if len(last_line) >= 8:
                                sfi = last_line[3]
                                a_index = last_line[6]
                                k_index = last_line[7]
                
                return {
                    'r_scale': r_scale,
                    's_scale': s_scale,
                    'g_scale': g_scale,
                    'sfi': sfi,
                    'a_index': a_index,
                    'k_index': k_index
                }
    
    except Exception as e:
        logger.error(f"Error fetching solar data: {e}")
    
    return None


async def post_solar_update():
    """Fetch and post solar/propagation update."""
    token = get_secret('DISCORD', 'BOT_TOKEN')
    channel_id = get_secret('SOLAR', 'POST_CHANNEL_ID')
    
    if not token:
        logger.error("DISCORD_BOT_TOKEN not set")
        return False
    
    if not channel_id:
        logger.error("SOLAR_POST_CHANNEL_ID not set")
        return False
    
    try:
        channel_id = int(channel_id)
    except ValueError:
        logger.error("Invalid SOLAR_POST_CHANNEL_ID (not numeric)")
        return False
    
    # Create Discord client
    intents = discord.Intents.default()
    client = discord.Client(intents=intents)
    
    @client.event
    async def on_ready():
        logger.info(f"Connected as {client.user}")
        
        try:
            channel = client.get_channel(channel_id)
            if not channel:
                channel = await client.fetch_channel(channel_id)
            
            if not channel:
                logger.error(f"Channel {channel_id} not found")
                await client.close()
                return
            
            # Fetch solar data
            async with aiohttp.ClientSession() as session:
                data = await fetch_solar_data(session)
            
            if not data:
                logger.error("Failed to fetch solar data")
                await client.close()
                return
            
            # Determine conditions
            r_scale = data['r_scale']
            s_scale = data['s_scale']
            g_scale = data['g_scale']
            sfi = data['sfi']
            
            # Parse numeric values for condition checking
            r_val = int(r_scale.replace('R', '')) if r_scale.replace('R', '').isdigit() else -1
            s_val = int(s_scale.replace('S', '')) if s_scale.replace('S', '').isdigit() else -1
            g_val = int(g_scale.replace('G', '')) if g_scale.replace('G', '').isdigit() else -1
            
            conditions_good = (
                (r_val == 0 or r_val == -1) and
                (g_val in [0, 1, -1])
            )
            
            try:
                sfi_value = int(sfi) if sfi != 'N/A' else 100
            except:
                sfi_value = 100
            
            # Create comprehensive embed
            embed = discord.Embed(
                title="☀️ Solar Weather & Propagation Report",
                description=f"Comprehensive band forecast • {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC",
                color=0xFF9800 if conditions_good else 0xF44336
            )
            
            # Current Indices
            embed.add_field(
                name="📊 Solar Indices",
                value=(
                    f"**Solar Flux (SFI):** {sfi}\n"
                    f"**A-index:** {data['a_index']}\n"
                    f"**K-index:** {data['k_index']}\n"
                    f"*SFI >150=Excellent, 70-150=Good, <70=Poor*"
                ),
                inline=False
            )
            
            # NOAA Scales
            embed.add_field(
                name="⚡ Radio Blackout",
                value=f"**{r_scale}** (R0-R5)\n{'✅ Clear' if r_val == 0 else '⚠️ Degraded' if r_val > 0 else 'N/A'}",
                inline=True
            )
            
            embed.add_field(
                name="☀️ Solar Radiation",
                value=f"**{s_scale}** (S0-S5)\n{'✅ Normal' if s_val == 0 else '⚠️ Elevated' if s_val > 0 else 'N/A'}",
                inline=True
            )
            
            embed.add_field(
                name="🧲 Geomagnetic Storm",
                value=f"**{g_scale}** (G0-G5)\n{'✅ Calm' if g_val == 0 else '⚠️ Disturbed' if g_val > 0 else 'N/A'}",
                inline=True
            )
            
            # Band-by-band predictions
            hf_predictions = []
            
            # 160m - Nighttime band
            hf_predictions.append("**160m:** 🟢 Good (Night) - Regional/DX after dark")
            
            # 80m - Day/Night band
            hf_predictions.append("**80m:** 🟢 Excellent (Night) - Reliable day/night")
            
            # 40m - Most reliable
            hf_predictions.append("**40m:** 🟢 Excellent - Works day and night")
            
            # 30m
            if conditions_good and sfi_value > 80:
                hf_predictions.append("**30m:** 🟢 Good - Digital modes DX possible")
            else:
                hf_predictions.append("**30m:** 🟡 Fair - Try CW/digital for best results")
            
            # 20m - Depends heavily on conditions
            if conditions_good and sfi_value > 100:
                hf_predictions.append("**20m:** 🟢 Excellent - Worldwide DX open!")
            elif sfi_value > 80:
                hf_predictions.append("**20m:** 🟡 Fair - DX possible with patience")
            else:
                hf_predictions.append("**20m:** 🟡 Fair - Limited to regional")
            
            # 17m
            if conditions_good and sfi_value > 100:
                hf_predictions.append("**17m:** 🟢 Good - Try for DX")
            else:
                hf_predictions.append("**17m:** 🟡 Fair - May be open briefly")
            
            # 15m - Solar dependent
            if conditions_good and sfi_value > 120:
                hf_predictions.append("**15m:** 🟢 Good - Long path DX possible")
            elif sfi_value > 90:
                hf_predictions.append("**15m:** 🟡 Fair - Check for openings")
            else:
                hf_predictions.append("**15m:** 🔴 Poor - Likely closed")
            
            # 12m
            if conditions_good and sfi_value > 120:
                hf_predictions.append("**12m:** 🟡 Fair - Worth checking")
            else:
                hf_predictions.append("**12m:** 🔴 Poor - Probably closed")
            
            # 10m - Highly solar dependent
            if conditions_good and sfi_value > 150:
                hf_predictions.append("**10m:** 🟢 Good - Magic band is open!")
            elif sfi_value > 120:
                hf_predictions.append("**10m:** 🟡 Fair - Possible short openings")
            else:
                hf_predictions.append("**10m:** 🔴 Poor - Closed, try WSPR")
            
            # 6m
            hf_predictions.append("**6m:** 🟡 Check for Sporadic-E (summer) or aurora")
            
            embed.add_field(
                name="📻 Band Conditions (HF)",
                value="\n".join(hf_predictions),
                inline=False
            )
            
            # VHF/UHF predictions
            vhf_predictions = []
            
            # 2m (144 MHz)
            if g_val and g_val >= 3:
                vhf_predictions.append("**2m:** 🟢 Good - Aurora possible! Try north")
            else:
                vhf_predictions.append("**2m:** 🟡 Normal - Line of sight, tropospheric")
            
            # 70cm (440 MHz)
            vhf_predictions.append("**70cm:** 🟡 Normal - Line of sight, repeaters")
            
            embed.add_field(
                name="📡 VHF/UHF Conditions",
                value="\n".join(vhf_predictions),
                inline=False
            )
            
            # Operating recommendations
            recommendations = []
            
            if r_scale != 'R0' and r_scale != 'N/A':
                recommendations.append("⚠️ **Radio Blackout Active:** Expect HF absorption, especially on higher frequencies")
            
            if g_scale and g_scale not in ['G0', 'N/A']:
                g_val_check = int(g_scale.replace('G', '')) if g_scale.replace('G', '').isdigit() else 0
                if g_val_check >= 3:
                    recommendations.append("🌈 **Aurora Possible!** Check 6m/2m for aurora propagation")
                recommendations.append("💡 **Tip:** Lower bands (80m/40m) handle storms better")
            
            if sfi_value > 150:
                recommendations.append("🎉 **Excellent Solar Flux!** Higher bands (15m/10m) should be wide open")
            elif sfi_value < 80:
                recommendations.append("💡 **Low Solar Flux:** Stick to 40m/80m for best results")
            
            if conditions_good:
                recommendations.append("✅ **Great Conditions Overall:** Good time for DX hunting on 20m!")
            
            if not recommendations:
                recommendations.append("📡 **Normal Conditions:** Standard band behavior expected")
            
            embed.add_field(
                name="💡 Operating Recommendations",
                value="\n".join(recommendations),
                inline=False
            )
            
            # Best bands right now
            now_hour = datetime.utcnow().hour
            if 12 <= now_hour <= 22:  # Daytime UTC
                best_now = "**Best Now (Day):** 20m, 17m, 15m, 40m"
            else:  # Nighttime UTC
                best_now = "**Best Now (Night):** 80m, 40m, 30m"
            
            embed.add_field(
                name="� Time-Based Suggestion",
                value=f"{best_now}\n*Gray line propagation may enhance any band!*",
                inline=False
            )
            
            embed.set_footer(text="73 de Penguin Overlord! • Data from NOAA SWPC • Posts every 6 hours")
            
            # Send message
            await channel.send(embed=embed)
            logger.info(f"Solar update posted to channel {channel_id}")
            
            # Update state
            state = load_state()
            state['last_posted'] = datetime.utcnow().isoformat()
            save_state(state)
            
        except Exception as e:
            logger.error(f"Error posting solar update: {e}", exc_info=True)
        
        finally:
            await client.close()
    
    try:
        await client.start(token)
        return True
    except Exception as e:
        logger.error(f"Error running client: {e}", exc_info=True)
        return False


if __name__ == '__main__':
    logger.info("Solar runner starting...")
    try:
        asyncio.run(post_solar_update())
        logger.info("Solar runner completed")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
