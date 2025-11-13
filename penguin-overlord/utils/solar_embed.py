#!/usr/bin/env python3
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
Shared solar weather embed generation for both !solar command and solar_runner.
This ensures consistency between manual and automated solar reports.
"""

import logging
import discord
import aiohttp
import math
import io
import matplotlib
matplotlib.use('Agg')  # Non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


# Import physics functions from radiohead
# These are the core propagation calculation functions
def estimate_fof2_from_sfi(sfi_value):
    """Estimate critical frequency (foF2) from Solar Flux Index."""
    base_fof2 = 7.0
    scale = math.sqrt(max(sfi_value, 50) / 100.0)
    return base_fof2 * scale


def calculate_muf_for_distance(fof2, distance_km):
    """Calculate Maximum Usable Frequency for a given distance."""
    if distance_km < 500:
        return fof2 * 3.0  # NVIS
    elif distance_km < 2000:
        return fof2 * 3.5  # Single hop F2
    elif distance_km < 4000:
        return fof2 * 4.0  # Multi-hop
    else:
        return fof2 * 4.5  # Very long distance


def calculate_d_layer_absorption(utc_hour, r_scale, sfi_value):
    """Calculate D-layer absorption factor."""
    r_val = 0
    if r_scale not in ['R0', 'N/A']:
        try:
            r_val = int(r_scale.replace('R', ''))
        except:
            r_val = 0
    
    hour_angle = abs(utc_hour - 12)
    
    if hour_angle > 6:
        base_absorption = 0.05
    else:
        solar_zenith_angle = (hour_angle / 6.0) * 90
        base_absorption = 0.4 * (1.0 - math.cos(math.radians(solar_zenith_angle)))
    
    sfi_factor = min(sfi_value / 150.0, 1.5)
    r_factor = 1.0 + (r_val * 0.3)
    
    return min(base_absorption * sfi_factor * r_factor, 1.0)


def calculate_gray_line_enhancement(utc_hour):
    """Check for gray line propagation enhancement."""
    if (5 <= utc_hour <= 7) or (17 <= utc_hour <= 19):
        return True, "🌅 Gray line active! Enhanced propagation on all bands possible."
    return False, ""


def get_k_index_impact(k_index, band_mhz):
    """Calculate K-index impact on specific frequency."""
    try:
        k_val = float(k_index) if k_index != 'N/A' else 2.0
    except:
        k_val = 2.0
    
    if k_val < 2:
        return 0.0
    elif k_val < 4:
        return 0.1 * (k_val - 2)
    else:
        impact = 0.2 + (0.2 * (k_val - 4))
        if band_mhz > 14:
            impact *= 1.5
        return min(impact, 1.0)


def get_seasonal_factor(month):
    """Get seasonal propagation factor."""
    if 5 <= month <= 8:
        return 1.2
    elif month in [11, 12, 1, 2]:
        return 0.8
    else:
        return 1.0


def predict_band_conditions(freq_mhz, fof2, muf_dx, d_absorption, k_impact, is_gray_line, month):
    """Predict band conditions with quality score."""
    seasonal = get_seasonal_factor(month)
    
    # Calculate MUF for this specific frequency's typical distance
    if freq_mhz < 5:
        target_dist = 500
    elif freq_mhz < 10:
        target_dist = 1500
    elif freq_mhz < 20:
        target_dist = 3000
    else:
        target_dist = 4000
    
    muf_for_band = calculate_muf_for_distance(fof2, target_dist)
    
    muf_ratio = freq_mhz / max(muf_for_band, 0.1)
    
    if muf_ratio > 0.95:
        base_score = 0.0
    elif muf_ratio > 0.85:
        base_score = 0.3
    elif muf_ratio > 0.7:
        base_score = 0.6
    elif muf_ratio > 0.5:
        base_score = 0.8
    else:
        base_score = 1.0
    
    absorption_penalty = float(d_absorption) * 0.4
    k_penalty = float(k_impact) * 0.3
    
    score = base_score - absorption_penalty - k_penalty
    
    if is_gray_line:
        score += 0.2
    
    score *= seasonal
    score = max(0.0, min(1.0, score))
    
    if score >= 0.8:
        return score, "🟢", "Excellent"
    elif score >= 0.6:
        return score, "🟢", "Good"
    elif score >= 0.4:
        return score, "🟡", "Fair"
    elif score >= 0.2:
        return score, "🟠", "Poor"
    else:
        return score, "🔴", "Closed"


async def plot_xray_flux(period: str = '6h') -> io.BytesIO:
    """
    Fetch GOES X-ray flux data and generate a dark-themed chart.
    
    Args:
        period: Time period ('6h', '1d', '3d', '7d')
    
    Returns:
        BytesIO object containing PNG image
    """
    period_map = {
        '6h': '6-hour',
        '1d': '1-day',
        '3d': '3-day',
        '7d': '7-day'
    }
    
    period_file = period_map.get(period.lower(), '6-hour')
    json_url = f"https://services.swpc.noaa.gov/json/goes/primary/xrays-{period_file}.json"
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(json_url) as resp:
                if resp.status != 200:
                    logger.error(f"Failed to fetch GOES data: {resp.status}")
                    return None
                
                data = await resp.json()
        
        if not data:
            logger.error("No GOES X-ray data received")
            return None
        
        # Parse data
        timestamps = []
        flux_short = []  # 0.05-0.4 nm
        flux_long = []   # 0.1-0.8 nm
        
        for entry in data:
            try:
                # Parse timestamp
                time_tag = entry.get('time_tag', '')
                dt = datetime.fromisoformat(time_tag.replace('Z', '+00:00'))
                timestamps.append(dt)
                
                # Get flux values (watts per square meter)
                flux_short.append(float(entry.get('flux', 0)))
                flux_long.append(float(entry.get('energy', 0)))
            except (ValueError, KeyError) as e:
                logger.warning(f"Skipping invalid entry: {e}")
                continue
        
        if not timestamps:
            logger.error("No valid GOES data points")
            return None
        
        # Create dark-themed plot
        plt.style.use('dark_background')
        fig, ax = plt.subplots(figsize=(12, 6), facecolor='#2C2F33')
        ax.set_facecolor('#23272A')
        
        # Plot data
        ax.plot(timestamps, flux_long, color='#FF6B6B', linewidth=2, label='0.1-0.8 nm', alpha=0.9)
        ax.plot(timestamps, flux_short, color='#4ECDC4', linewidth=2, label='0.05-0.4 nm', alpha=0.9)
        
        # Set logarithmic scale
        ax.set_yscale('log')
        ax.set_ylim(1e-9, 1e-2)
        
        # Add flare classification lines
        ax.axhline(y=1e-3, color='#FF3838', linestyle='--', linewidth=1, alpha=0.5)
        ax.text(timestamps[len(timestamps)//20], 1e-3, 'X', color='#FF3838', fontsize=10, va='bottom')
        
        ax.axhline(y=1e-4, color='#FF8C42', linestyle='--', linewidth=1, alpha=0.5)
        ax.text(timestamps[len(timestamps)//20], 1e-4, 'M', color='#FF8C42', fontsize=10, va='bottom')
        
        ax.axhline(y=1e-5, color='#FFD93D', linestyle='--', linewidth=1, alpha=0.5)
        ax.text(timestamps[len(timestamps)//20], 1e-5, 'C', color='#FFD93D', fontsize=10, va='bottom')
        
        ax.axhline(y=1e-6, color='#6BCF7F', linestyle='--', linewidth=1, alpha=0.5)
        ax.text(timestamps[len(timestamps)//20], 1e-6, 'B', color='#6BCF7F', fontsize=10, va='bottom')
        
        # Format x-axis
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d %H:%M', tz=timezone.utc))
        ax.xaxis.set_major_locator(mdates.AutoDateLocator())
        plt.xticks(rotation=45, ha='right')
        
        # Labels and title
        ax.set_xlabel('Time (UTC)', fontsize=12, color='#FFFFFF')
        ax.set_ylabel('Watts per square meter', fontsize=12, color='#FFFFFF')
        ax.set_title(f'GOES Solar X-Ray Flux ({period_file})', fontsize=14, color='#FFFFFF', pad=20)
        
        # Legend
        ax.legend(loc='upper left', framealpha=0.8, facecolor='#23272A', edgecolor='#7289DA')
        
        # Grid
        ax.grid(True, alpha=0.2, linestyle=':', color='#7289DA')
        
        # Tight layout
        plt.tight_layout()
        
        # Save to BytesIO
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=150, facecolor='#2C2F33', edgecolor='none')
        buf.seek(0)
        plt.close(fig)
        
        return buf
        
    except Exception as e:
        logger.error(f"Error generating X-ray flux chart: {e}")
        return None


async def create_xray_flux_embed(period: str = '6h') -> tuple[discord.Embed, discord.File]:
    """
    Create GOES X-Ray Flux chart embed with plotted data.
    
    Args:
        period: Time period for chart ('6h', '1d', '3d', '7d')
    
    Returns:
        Tuple of (discord.Embed, discord.File) with X-ray flux chart
    """
    period_map = {
        '6h': {'name': '6-hour', 'file': '6-hour', 'desc': 'past 6 hours'},
        '1d': {'name': '1-day', 'file': '1-day', 'desc': 'past 24 hours'},
        '3d': {'name': '3-day', 'file': '3-day', 'desc': 'past 3 days'},
        '7d': {'name': '7-day', 'file': '7-day', 'desc': 'past 7 days'}
    }
    
    period_info = period_map.get(period.lower(), period_map['6h'])
    
    embed = discord.Embed(
        title=f"☀️ GOES Solar X-Ray Flux ({period_info['name']})",
        description=(
            f"**Real-time solar X-ray flux data - {period_info['desc']}**\n\n"
            "**Flare Classifications:**\n"
            "🔴 **X-class** (>10⁻³) - Major flares, HF blackouts worldwide\n"
            "🟠 **M-class** (10⁻⁴ to 10⁻³) - Medium flares, regional HF degradation\n"
            "🟡 **C-class** (10⁻⁵ to 10⁻⁴) - Minor flares, slight HF absorption\n"
            "🟢 **B-class** (10⁻⁶ to 10⁻⁵) - Weak flares, normal conditions\n\n"
            "📊 **Reading the Chart:**\n"
            "• Red line = 0.1-0.8 nm (long wavelength X-rays)\n"
            "• Cyan line = 0.05-0.4 nm (short wavelength X-rays)\n"
            "• Spikes indicate solar flares causing radio blackouts\n"
            "• Higher flux = More D-layer ionization = Worse HF propagation"
        ),
        color=0xFFA500,
        timestamp=datetime.now(timezone.utc)
    )
    
    # Generate chart
    chart_buf = await plot_xray_flux(period)
    
    if chart_buf:
        # Attach chart image
        file = discord.File(chart_buf, filename=f'xray_flux_{period}.png')
        embed.set_image(url=f'attachment://xray_flux_{period}.png')
    else:
        # Fallback to links if chart generation fails
        json_url = f"https://services.swpc.noaa.gov/json/goes/primary/xrays-{period_info['file']}.json"
        embed.add_field(
            name="⚠️ Chart Generation Failed",
            value=f"[View on NOAA SWPC](https://www.swpc.noaa.gov/products/goes-x-ray-flux)\n"
                  f"[Raw JSON Data]({json_url})",
            inline=False
        )
        file = None
    
    embed.set_footer(text=f"NOAA GOES Satellite • Updated every minute • Use !xray 6h|1d|3d|7d to change period")
    
    return embed, file


async def create_propagation_maps() -> list[discord.Embed]:
    """
    Create additional propagation map embeds for automated solar posts.
    Returns a list of embeds for D-RAP and Aurora forecast.
    
    Returns:
        List of discord.Embed objects for propagation maps
    """
    embeds = []
    
    # D-RAP Map
    drap_embed = discord.Embed(
        title="📡 D-Region Absorption Prediction",
        description=(
            "**Real-time HF absorption due to solar X-rays**\n\n"
            "🔴 Red = High absorption (HF challenging)\n"
            "🟡 Yellow = Moderate absorption\n"
            "🟢 Green/Blue = Low absorption (HF good)\n\n"
            "Higher D-layer absorption means lower frequencies work better.\n"
            "Try 40m/80m during high absorption periods."
        ),
        color=0xFF6B35,
        timestamp=datetime.now(timezone.utc)
    )
    drap_embed.set_image(url="https://services.swpc.noaa.gov/images/animations/d-rap/global/d-rap/latest.png")
    drap_embed.set_footer(text="NOAA SWPC • Updated every 15 min")
    embeds.append(drap_embed)
    
    # Aurora Forecast Map
    aurora_embed = discord.Embed(
        title="🌌 Aurora Forecast (30-min)",
        description=(
            "**Auroral oval position - VHF/UHF scatter opportunities**\n\n"
            "🟢 Green aurora = 2m/6m scatter possible\n"
            "🟡 Yellow = Enhanced activity\n"
            "🔴 Red = Intense aurora\n\n"
            "Point antennas north, use SSB/CW modes.\n"
            "Best during K≥4 geomagnetic activity."
        ),
        color=0x00FF7F,
        timestamp=datetime.now(timezone.utc)
    )
    aurora_embed.set_image(url="https://services.swpc.noaa.gov/images/animations/ovation/north/latest.jpg")
    aurora_embed.set_footer(text="NOAA SWPC • Updated every 5 min")
    embeds.append(aurora_embed)
    
    return embeds


async def create_solar_embed(session: aiohttp.ClientSession = None) -> discord.Embed:
    """
    Create comprehensive solar weather embed with band predictions.
    
    This is the SINGLE SOURCE OF TRUTH for solar reports - used by both
    the !solar command and the automated solar_runner.
    
    Args:
        session: aiohttp.ClientSession for API requests (will create if None)
    
    Returns:
        discord.Embed with complete solar weather report
    """
    close_session = False
    if session is None:
        session = aiohttp.ClientSession()
        close_session = True
    
    try:
        # Fetch NOAA scales (R, S, G scales)
        async with session.get('https://services.swpc.noaa.gov/products/noaa-scales.json', timeout=10) as resp:
            if resp.status != 200:
                return discord.Embed(
                    title="❌ Solar Data Unavailable",
                    description="Unable to fetch data from NOAA. Please try again later.",
                    color=0xF44336
                )
            
            data = await resp.json()
            
            # Extract current conditions
            r_scale = 'N/A'
            s_scale = 'N/A'
            g_scale = 'N/A'
            
            if isinstance(data, dict) and '0' in data:
                current = data['0']
                r_scale = current.get('R', {}).get('Scale', 'N/A')
                s_scale = current.get('S', {}).get('Scale', 'N/A')
                g_scale = current.get('G', {}).get('Scale', 'N/A')
            
            # Fetch solar flux
            sfi = 'N/A'
            async with session.get('https://services.swpc.noaa.gov/json/f107_cm_flux.json', timeout=10) as flux_resp:
                if flux_resp.status == 200:
                    flux_data = await flux_resp.json()
                    if flux_data:
                        for entry in reversed(flux_data):
                            if entry.get('reporting_schedule') == 'Noon':
                                sfi = str(int(entry.get('flux', 0)))
                                break
                        if sfi == 'N/A' and flux_data:
                            sfi = str(int(flux_data[-1].get('flux', 0)))
            
            # Fetch K-index
            k_index = 'N/A'
            async with session.get('https://services.swpc.noaa.gov/json/planetary_k_index_1m.json', timeout=10) as k_resp:
                if k_resp.status == 200:
                    k_data = await k_resp.json()
                    if k_data:
                        k_index = str(k_data[-1].get('kp_index', 'N/A'))
            
            # Calculate A-index from K-index
            a_index = 'N/A'
            if k_index != 'N/A':
                try:
                    k_val = int(k_index)
                    a_val = int((k_val ** 2) * 3.3)
                    a_index = str(a_val)
                except:
                    pass
            
            # Parse values for calculations
            try:
                sfi_value = int(sfi) if sfi != 'N/A' else 100
            except:
                sfi_value = 100
            
            try:
                k_value = float(k_index) if k_index != 'N/A' else 2.0
            except:
                k_value = 2.0
            
            # Get current UTC hour
            utc_hour = datetime.now(timezone.utc).hour
            
            # Calculate propagation parameters
            fof2 = estimate_fof2_from_sfi(sfi_value)
            muf_dx = calculate_muf_for_distance(fof2, 3000)
            muf_regional = calculate_muf_for_distance(fof2, 1000)
            d_absorption = calculate_d_layer_absorption(utc_hour, r_scale, sfi_value)
            is_gray_line, gray_line_msg = calculate_gray_line_enhancement(utc_hour)
            
            # Determine overall conditions
            conditions_good = (
                (r_scale in ['R0', 'N/A'] or r_scale == 'R0') and
                (g_scale in ['G0', 'N/A', 'G1'] or g_scale in ['G0', 'G1']) and
                d_absorption < 0.5 and
                k_value < 4
            )
            
            # Create main embed
            embed = discord.Embed(
                title="☀️ Solar Weather Report",
                description=f"Comprehensive propagation forecast • {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC",
                color=0xFF9800 if conditions_good else 0xF44336
            )
            
            # Solar Indices
            embed.add_field(
                name="📊 Solar Indices",
                value=(
                    f"**Solar Flux (SFI):** {sfi}\n"
                    f"**A-index:** {a_index}\n"
                    f"**K-index:** {k_index}\n"
                    f"**foF2 (Critical Freq):** {fof2:.1f} MHz\n"
                    f"**MUF (DX):** {muf_dx:.1f} MHz\n"
                    f"**D-Layer Absorption:** {d_absorption*100:.0f}%"
                ),
                inline=False
            )
            
            # NOAA Scales
            r_val = int(r_scale) if str(r_scale).isdigit() else -1
            s_val = int(s_scale) if str(s_scale).isdigit() else -1
            g_val = int(g_scale) if str(g_scale).isdigit() else -1
            
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
            current_month = datetime.now(timezone.utc).month
            
            bands = [
                (1.9, "160m", "Regional/DX at night"),
                (3.6, "80m", "Reliable day/night workhorse"),
                (7.1, "40m", "Most reliable all-around"),
                (10.125, "30m", "CW/digital DX"),
                (14.2, "20m", "Premier DX band"),
                (18.1, "17m", "Underutilized gem"),
                (21.2, "15m", "Solar-dependent DX"),
                (24.9, "12m", "Solar-dependent"),
                (28.5, "10m", "Magic band"),
                (50.1, "6m", "Magic band of VHF"),
            ]
            
            for freq_mhz, band_name, typical_use in bands:
                k_impact = get_k_index_impact(k_value, freq_mhz)
                score, emoji, quality = predict_band_conditions(
                    freq_mhz, fof2, muf_dx, d_absorption, k_impact, is_gray_line, current_month
                )
                
                # Add contextual information
                if band_name == "160m" and utc_hour >= 6 and utc_hour <= 18:
                    context = "(daytime - poor)"
                elif band_name == "80m" and utc_hour >= 0 and utc_hour <= 6:
                    context = "(nighttime peak)"
                elif band_name == "20m" and quality in ["Excellent", "Good"]:
                    context = "(worldwide DX)"
                elif band_name == "10m" and quality == "Closed":
                    context = "(try WSPR/FT8)"
                elif band_name == "6m":
                    if 5 <= current_month <= 8:
                        context = "(Sporadic-E season!)"
                    else:
                        context = "(check for Es/aurora)"
                else:
                    context = f"({typical_use})"
                
                hf_predictions.append(f"**{band_name}:** {emoji} {quality} {context}")
            
            embed.add_field(
                name="📻 Band Conditions (HF/VHF)",
                value="\n".join(hf_predictions),
                inline=False
            )
            
            # VHF/UHF predictions
            vhf_predictions = []
            g_val = int(g_scale.replace('G', '')) if g_scale not in ['N/A', 'G0'] and g_scale.replace('G', '').isdigit() else 0
            
            if g_val >= 3:
                vhf_predictions.append("**2m:** 🟢 Aurora possible! Try north, use SSB/CW")
            elif g_val >= 1:
                vhf_predictions.append("**2m:** 🟡 Minor aurora possible, watch for activity")
            else:
                vhf_predictions.append("**2m:** 🟡 Normal - Line of sight, tropospheric scatter")
            
            vhf_predictions.append("**70cm:** 🟡 Normal - Line of sight, repeaters, satellites")
            
            embed.add_field(
                name="📡 VHF/UHF Conditions",
                value="\n".join(vhf_predictions),
                inline=False
            )
            
            # ISM/WiFi effects during R2+ blackouts
            r_val = int(r_scale.replace('R', '')) if r_scale not in ['R0', 'N/A'] and r_scale.replace('R', '').isdigit() else 0
            if r_val >= 2:
                ism_effects = []
                
                if r_val >= 4:
                    ism_effects.append("**900MHz (33cm/ISM):** 🔴 Likely interference - LoRa, Zigbee, ISM devices affected")
                    ism_effects.append("**2.4GHz (WiFi/BT):** 🔴 Likely disruption - WiFi, Bluetooth, Zigbee may degrade")
                    ism_effects.append("**5GHz WiFi:** 🟠 Possible minor impact - Monitor for issues")
                    ism_effects.append("**6GHz WiFi 6E:** 🟡 Minimal impact expected")
                elif r_val >= 3:
                    ism_effects.append("**900MHz (33cm/ISM):** 🟠 Possible interference - LoRa, Zigbee, ISM devices")
                    ism_effects.append("**2.4GHz (WiFi/BT):** 🟠 Possible disruption - WiFi, Bluetooth may be affected")
                    ism_effects.append("**5GHz WiFi:** 🟡 Minor impact possible")
                    ism_effects.append("**6GHz WiFi 6E:** 🟡 Minimal impact expected")
                else:
                    ism_effects.append("**900MHz (33cm/ISM):** 🟡 Monitor for issues - LoRa, Zigbee, ISM devices")
                    ism_effects.append("**2.4GHz (WiFi/BT):** 🟡 Monitor for issues - WiFi, Bluetooth")
                    ism_effects.append("**5/6GHz WiFi:** 🟢 Minimal impact expected")
                
                if r_val >= 4:
                    ism_effects.append("\n*Note: Infrastructure issues (power grid) may also affect network equipment*")
                
                embed.add_field(
                    name=f"🌐 ISM/WiFi Band Effects ({r_scale} Radio Blackout Active)",
                    value="\n".join(ism_effects),
                    inline=False
                )
            
            # Gray line information
            if is_gray_line:
                embed.add_field(
                    name="🌅 Gray Line Enhancement",
                    value=gray_line_msg,
                    inline=False
                )
            
            # Operating recommendations
            recommendations = []
            
            if d_absorption > 0.7:
                recommendations.append("⚠️ **High D-Layer Absorption:** Lower frequencies heavily affected. Try 40m/80m.")
            elif d_absorption > 0.4:
                recommendations.append("⚠️ **Moderate Absorption:** Higher bands (20m+) may be challenging.")
            
            r_val = int(r_scale.replace('R', '')) if r_scale not in ['R0', 'N/A'] and r_scale.replace('R', '').isdigit() else 0
            if r_val >= 3:
                recommendations.append("🚨 **Major Radio Blackout (R3+):** HF severely degraded. Try lower bands.")
            elif r_val >= 1:
                recommendations.append("⚠️ **Radio Blackout Active:** Expect absorption on higher frequencies.")
            
            if g_val >= 4:
                recommendations.append("🌈 **Major Geomagnetic Storm!** Aurora likely on 6m/2m. HF disturbed.")
            elif g_val >= 3:
                recommendations.append("🌈 **Aurora Possible!** Check 6m/2m for aurora propagation.")
            elif g_val >= 1:
                recommendations.append("💡 **Tip:** Lower bands (80m/40m) handle geomagnetic activity better.")
            
            if muf_dx > 28:
                recommendations.append("🎉 **Excellent MUF!** 10m should be open - check for magic band DX!")
            elif muf_dx > 21:
                recommendations.append("✨ **Great Conditions!** 15m and 20m excellent for DX hunting.")
            elif muf_dx < 14:
                recommendations.append("💡 **Low MUF:** Focus on 40m and 80m for reliable contacts.")
            
            if k_value >= 5:
                recommendations.append("⚡ **High K-Index:** Expect flutter and fading on higher bands.")
            
            if conditions_good and muf_dx > 21:
                recommendations.append("✅ **Excellent Conditions Overall:** Prime time for DX on multiple bands!")
            elif conditions_good:
                recommendations.append("✅ **Good Conditions:** Normal propagation expected.")
            
            if not recommendations:
                recommendations.append("📡 **Normal Conditions:** Standard propagation behavior expected.")
            
            embed.add_field(
                name="💡 Operating Recommendations",
                value="\n".join(recommendations),
                inline=False
            )
            
            # Best bands right now
            best_bands = []
            if d_absorption < 0.3:
                if muf_dx > 28:
                    best_bands = ["10m", "15m", "20m", "17m"]
                elif muf_dx > 21:
                    best_bands = ["20m", "17m", "15m", "40m"]
                elif muf_dx > 14:
                    best_bands = ["20m", "30m", "40m"]
                else:
                    best_bands = ["40m", "30m", "80m"]
            else:
                if muf_dx > 21:
                    best_bands = ["40m", "80m", "30m", "20m"]
                else:
                    best_bands = ["80m", "40m", "160m"]
            
            time_period = "Day" if 6 <= utc_hour <= 18 else "Night"
            best_now = f"**Best Now ({time_period}, {utc_hour:02d}:00 UTC):** {', '.join(best_bands)}"
            
            embed.add_field(
                name="🕐 Recommended Bands Now",
                value=f"{best_now}\n*Predictions based on MUF={muf_dx:.1f}MHz, foF2={fof2:.1f}MHz*",
                inline=False
            )
            
            embed.set_footer(text="73 de Penguin Overlord! • Data from NOAA SWPC • Enhanced physics-based propagation • Posts every 30 min")
            
            return embed
            
    except Exception as e:
        logger.error(f"Error creating solar embed: {e}", exc_info=True)
        return discord.Embed(
            title="❌ Error Creating Solar Report",
            description=f"An error occurred: {str(e)}",
            color=0xF44336
        )
    finally:
        if close_session:
            await session.close()
