#!/usr/bin/env python3
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
Solar/Propagation Runner - Standalone execution for systemd timers

Fetches NOAA space weather data and posts to configured Discord channel
with enhanced physics-based propagation calculations.

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


# ============================================================================
# IONOSPHERIC PROPAGATION PHYSICS FUNCTIONS
# ============================================================================

def calculate_muf_for_distance(fof2, distance_km):
    """
    Calculate Maximum Usable Frequency for a given distance.
    
    Uses simplified ionospheric model:
    MUF = foF2 * secant(elevation_angle) * correction_factor
    
    For typical F2-layer height of 300km:
    - Short paths (0-500km): MUF ≈ foF2 * 3.0 (NVIS/single hop)
    - Medium paths (500-2000km): MUF ≈ foF2 * 3.5
    - Long paths (2000-4000km): MUF ≈ foF2 * 4.0
    - Very long paths (4000km+): MUF ≈ foF2 * 4.5
    
    Args:
        fof2: Critical frequency in MHz
        distance_km: Path distance in kilometers
    
    Returns:
        MUF in MHz
    """
    if distance_km < 500:
        return fof2 * 3.0  # NVIS
    elif distance_km < 2000:
        return fof2 * 3.5  # Single hop F2
    elif distance_km < 4000:
        return fof2 * 4.0  # Multi-hop
    else:
        return fof2 * 4.5  # Very long distance


def calculate_d_layer_absorption(utc_hour, r_scale, sfi_value):
    """
    Calculate D-layer absorption factor based on solar zenith angle and solar activity.
    
    D-layer absorption is maximum at solar noon and minimal at night.
    Higher frequencies penetrate better than lower frequencies.
    Solar flares (R-scale events) dramatically increase absorption.
    
    Args:
        utc_hour: Current UTC hour (0-23)
        r_scale: NOAA R-scale (R0-R5 or 'N/A')
        sfi_value: Solar Flux Index
    
    Returns:
        Absorption factor (0.0 = no absorption, 1.0 = complete absorption)
    """
    # Convert R-scale to numeric
    r_val = 0
    if r_scale not in ['R0', 'N/A']:
        try:
            r_val = int(r_scale.replace('R', ''))
        except:
            r_val = 0
    
    # Calculate solar zenith angle approximation
    hour_angle = abs(utc_hour - 12)
    
    if hour_angle > 6:
        # Night time - minimal D-layer absorption
        base_absorption = 0.05
    else:
        # Day time - absorption increases toward solar noon
        base_absorption = 0.3 + (0.4 * (1.0 - hour_angle / 6.0))
    
    # Adjust for solar activity
    sfi_factor = min(sfi_value / 150.0, 2.0)
    base_absorption *= sfi_factor
    
    # Add radio blackout contribution
    if r_val > 0:
        base_absorption += (r_val * 0.2)
    
    return min(base_absorption, 1.0)


def calculate_gray_line_enhancement(utc_hour):
    """
    Determine if current time is during gray line (twilight) period.
    
    Gray line propagation occurs at sunrise/sunset when D-layer is minimal
    but F-layer remains ionized.
    
    Args:
        utc_hour: Current UTC hour (0-23)
    
    Returns:
        (is_gray_line, enhancement_description)
    """
    morning_gray = (5 <= utc_hour <= 7)
    evening_gray = (17 <= utc_hour <= 19)
    
    if morning_gray or evening_gray:
        time_desc = "Morning" if morning_gray else "Evening"
        return (True, f"🌅 {time_desc} Gray Line - Enhanced DX propagation!")
    
    return (False, None)


def get_k_index_impact(k_index, band_mhz):
    """
    Calculate K-index impact on propagation for specific band.
    
    Higher frequencies are more affected by geomagnetic disturbances.
    
    Args:
        k_index: Planetary K-index (0-9)
        band_mhz: Band frequency in MHz
    
    Returns:
        Impact factor (0.0 = no impact, 1.0 = severe impact)
    """
    try:
        k_val = float(k_index)
    except:
        k_val = 2.0
    
    # Higher frequencies more affected
    if band_mhz >= 21:  # 15m and higher
        sensitivity = 0.15
    elif band_mhz >= 14:  # 20m
        sensitivity = 0.12
    elif band_mhz >= 7:  # 40m and 30m
        sensitivity = 0.08
    else:  # 80m and 160m
        sensitivity = 0.05
    
    impact = min(k_val * sensitivity, 1.0)
    return impact


def get_seasonal_factor(month):
    """
    Calculate seasonal propagation factor.
    
    Args:
        month: Month number (1-12)
    
    Returns:
        (f2_factor, es_probability, season_name)
    """
    if month in [12, 1, 2]:  # Winter
        return (1.15, 0.1, "Winter")
    elif month in [3, 4, 9, 10]:  # Equinox
        return (1.1, 0.4, "Equinox")
    elif month in [5, 6, 7, 8]:  # Summer
        return (0.9, 0.8, "Summer")
    else:  # Fall
        return (1.0, 0.3, "Fall")


def predict_band_conditions(band_mhz, band_name, fof2, muf_nvis, muf_regional, muf_dx, 
                            absorption, k_impact, is_gray_line, month, utc_hour):
    """
    Predict propagation conditions for a specific band using all physics factors.
    
    Args:
        band_mhz: Band frequency in MHz
        band_name: Band name (e.g., "80m")
        fof2: Critical frequency in MHz
        muf_nvis: MUF for NVIS propagation
        muf_regional: MUF for regional (1000km)
        muf_dx: MUF for DX (3000km)
        absorption: D-layer absorption factor (0-1)
        k_impact: K-index impact factor (0-1)
        is_gray_line: Boolean indicating gray line enhancement
        month: Month number (1-12)
        utc_hour: Current UTC hour
    
    Returns:
        Formatted string with emoji and prediction
    """
    # Get seasonal factors
    f2_factor, es_probability, season_name = get_seasonal_factor(month)
    
    # Determine if band is usable based on MUF
    # Bands work best when frequency is between foF2 and 85% of MUF
    optimal_muf_dx = muf_dx * 0.85
    optimal_muf_regional = muf_regional * 0.85
    optimal_muf_nvis = muf_nvis * 0.85
    
    # Calculate quality score (0-100)
    quality = 50  # Base score
    
    # Check if band is below MUF (can propagate)
    if band_mhz > optimal_muf_dx:
        quality -= 40  # Way above MUF, poor propagation
    elif band_mhz > optimal_muf_regional:
        quality -= 20  # Above regional MUF, DX only
    
    # Check if band is above foF2 (skip zone avoidance)
    if band_mhz < fof2:
        quality -= 10  # Below foF2, but still usable via NVIS
    
    # Apply D-layer absorption (worse for lower frequencies during day)
    if band_mhz < 10:  # 160m, 80m, 40m affected more by D-layer at day
        quality -= (absorption * 30)
    else:
        quality -= (absorption * 15)
    
    # Apply K-index impact
    quality -= (k_impact * 40)
    
    # Gray line bonus
    if is_gray_line:
        quality += 20
    
    # Night time bonuses for low bands
    if utc_hour < 6 or utc_hour > 18:
        if band_mhz < 5:  # 160m, 80m
            quality += 15
    
    # Seasonal adjustments
    if month in [5, 6, 7, 8] and band_mhz >= 28:  # 10m/6m in summer
        quality += (es_probability * 20)
    
    # Clamp quality
    quality = max(0, min(100, quality))
    
    # Determine emoji and description
    if quality >= 70:
        emoji = "🟢"
        condition = "Excellent"
    elif quality >= 50:
        emoji = "🟡"
        condition = "Good"
    elif quality >= 30:
        emoji = "🟠"
        condition = "Fair"
    else:
        emoji = "🔴"
        condition = "Poor"
    
    # Build description
    description = f"{condition}"
    
    # Add propagation type
    if band_mhz < fof2 and band_mhz < optimal_muf_nvis:
        description += " - NVIS/regional"
    elif band_mhz < optimal_muf_regional:
        description += " - Regional DX"
    elif band_mhz < optimal_muf_dx:
        description += " - Worldwide DX"
    else:
        description += " - Limited/local only"
    
    return f"**{band_name}:** {emoji} {description}"

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
    """Fetch solar/propagation data from NOAA and calculate propagation parameters."""
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
                
                # Calculate foF2 from SFI (empirical relationship)
                # foF2 ≈ sqrt(SFI / 150) * 10 MHz (typical mid-latitude daytime)
                try:
                    sfi_value = float(sfi) if sfi != 'N/A' else 100.0
                except:
                    sfi_value = 100.0
                
                # Base foF2 calculation with time-of-day adjustment
                now = datetime.utcnow()
                utc_hour = now.hour
                
                # Day/night adjustment for foF2
                hour_angle = abs(utc_hour - 12)
                if hour_angle > 6:  # Night
                    time_factor = 0.6  # foF2 drops at night
                else:  # Day
                    time_factor = 1.0 - (hour_angle / 12.0) * 0.2
                
                fof2 = (sfi_value / 150.0) ** 0.5 * 10.0 * time_factor
                fof2 = max(3.0, min(fof2, 15.0))  # Clamp to realistic range
                
                return {
                    'r_scale': r_scale,
                    's_scale': s_scale,
                    'g_scale': g_scale,
                    'sfi': sfi,
                    'a_index': a_index,
                    'k_index': k_index,
                    'fof2': fof2,
                    'sfi_value': sfi_value,
                    'utc_hour': utc_hour,
                    'month': now.month
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
            
            # Calculate propagation parameters using physics
            fof2 = data['fof2']
            sfi_value = data['sfi_value']
            utc_hour = data['utc_hour']
            month = data['month']
            
            # Calculate MUFs for different path lengths
            muf_nvis = calculate_muf_for_distance(fof2, 300)      # NVIS/local
            muf_regional = calculate_muf_for_distance(fof2, 1000) # Regional
            muf_dx = calculate_muf_for_distance(fof2, 3000)       # DX
            
            # Calculate D-layer absorption
            absorption = calculate_d_layer_absorption(utc_hour, r_scale, sfi_value)
            
            # Check for gray line
            is_gray_line, gray_line_msg = calculate_gray_line_enhancement(utc_hour)
            
            # Add propagation physics info
            embed.add_field(
                name="🌐 Ionospheric Parameters",
                value=(
                    f"**foF2:** {fof2:.1f} MHz (Critical frequency)\n"
                    f"**MUF (DX):** {muf_dx:.1f} MHz (3000km path)\n"
                    f"**MUF (Regional):** {muf_regional:.1f} MHz (1000km)\n"
                    f"**D-layer Absorption:** {absorption*100:.0f}%"
                ),
                inline=False
            )
            
            # Band-by-band predictions using physics
            hf_predictions = []
            
            # Define HF bands with their frequencies
            bands = [
                (1.8, "160m"),
                (3.5, "80m"),
                (7.0, "40m"),
                (10.1, "30m"),
                (14.0, "20m"),
                (18.1, "17m"),
                (21.0, "15m"),
                (24.9, "12m"),
                (28.0, "10m"),
            ]
            
            for band_mhz, band_name in bands:
                k_impact = get_k_index_impact(data['k_index'], band_mhz)
                prediction = predict_band_conditions(
                    band_mhz, band_name, fof2, muf_nvis, muf_regional, muf_dx,
                    absorption, k_impact, is_gray_line, month, utc_hour
                )
                hf_predictions.append(prediction)
            
            # Add 6m with Sporadic-E consideration
            f2_factor, es_probability, season_name = get_seasonal_factor(month)
            if month in [5, 6, 7, 8]:  # Summer Sporadic-E season
                hf_predictions.append(f"**6m:** 🟢 Good - {season_name} Sporadic-E likely ({es_probability*100:.0f}% chance)")
            elif g_val >= 3:  # Aurora possible
                hf_predictions.append("**6m:** 🟡 Fair - Check for aurora propagation")
            else:
                hf_predictions.append("**6m:** 🟡 Fair - Tropospheric/short skip")
            
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
            
            # Gray line enhancement
            if is_gray_line:
                recommendations.append(gray_line_msg)
            
            # D-layer absorption warning
            if absorption > 0.5:
                recommendations.append(f"⚠️ **High D-layer Absorption ({absorption*100:.0f}%):** Lower bands affected, try higher frequencies")
            
            if r_scale != 'R0' and r_scale != 'N/A':
                recommendations.append("⚠️ **Radio Blackout Active:** Expect HF absorption, especially on higher frequencies")
            
            if g_scale and g_scale not in ['G0', 'N/A']:
                g_val_check = int(g_scale.replace('G', '')) if g_scale.replace('G', '').isdigit() else 0
                if g_val_check >= 3:
                    recommendations.append("🌈 **Aurora Possible!** Check 6m/2m for aurora propagation")
                recommendations.append("💡 **Tip:** Lower bands (80m/40m) handle storms better")
            
            # MUF-based recommendations
            if muf_dx > 21:
                recommendations.append(f"🎉 **MUF DX: {muf_dx:.1f} MHz** - Higher bands (20m/17m/15m) should support DX!")
            elif muf_dx < 14:
                recommendations.append(f"💡 **MUF DX: {muf_dx:.1f} MHz** - Stick to 40m/80m for best DX results")
            
            if sfi_value > 150:
                recommendations.append("🎉 **Excellent Solar Flux!** Higher bands (15m/10m) should be wide open")
            elif sfi_value < 80:
                recommendations.append("💡 **Low Solar Flux:** Conditions favor lower bands")
            
            if conditions_good and muf_dx > 18:
                recommendations.append("✅ **Great Conditions Overall:** Excellent for DX on multiple bands!")
            
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
            
            embed.set_footer(text="73 de Penguin Overlord! • Enhanced physics-based propagation • Posts every 3 hours")
            
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
