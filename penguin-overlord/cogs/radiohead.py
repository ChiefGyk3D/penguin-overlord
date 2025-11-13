# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
Radiohead Cog - HAM radio propagation, news, and frequency trivia.
Integrates with NOAA space weather API for real-time propagation data.
"""

import logging
import random
import discord
from discord.ext import commands, tasks
import aiohttp
from datetime import datetime, timezone
import json
import os
import math

logger = logging.getLogger(__name__)


# ============================================================================
# PROPAGATION HELPER FUNCTIONS - Physics-based MUF and absorption calculations
# ============================================================================

def estimate_fof2_from_sfi(sfi_value):
    """
    Estimate critical frequency (foF2) from Solar Flux Index.
    
    Based on empirical relationship: foF2 ≈ sqrt(SFI/150) * base_frequency
    During solar minimum (SFI~70): foF2 ≈ 4-5 MHz
    During solar maximum (SFI~200+): foF2 ≈ 10-12 MHz
    
    Args:
        sfi_value: Solar Flux Index (70-300 typical range)
    
    Returns:
        Estimated foF2 in MHz
    """
    # Base foF2 at SFI=100 (typical mid-cycle)
    base_fof2 = 7.0
    
    # Scale factor based on SFI
    scale = math.sqrt(max(sfi_value, 50) / 100.0)
    
    return base_fof2 * scale


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
        # NVIS - Near Vertical Incidence Skywave
        return fof2 * 3.0
    elif distance_km < 2000:
        # Single hop F2
        return fof2 * 3.5
    elif distance_km < 4000:
        # Multi-hop or long single hop
        return fof2 * 4.0
    else:
        # Very long distance
        return fof2 * 4.5


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
        Higher values mean worse conditions
    """
    # Convert R-scale to numeric
    r_val = 0
    if r_scale not in ['R0', 'N/A']:
        try:
            r_val = int(r_scale.replace('R', ''))
        except:
            r_val = 0
    
    # Calculate solar zenith angle approximation (simplified model)
    # Assumes observer near equator for global average
    # Peak absorption at solar noon (12 UTC approximate), minimum at night
    hour_angle = abs(utc_hour - 12)
    
    if hour_angle > 6:
        # Night time - minimal D-layer absorption
        base_absorption = 0.05
    else:
        # Day time - absorption increases toward solar noon
        base_absorption = 0.3 + (0.4 * (1.0 - hour_angle / 6.0))
    
    # Adjust for solar activity (higher SFI = more ionization = more absorption)
    sfi_factor = min(sfi_value / 150.0, 2.0)
    base_absorption *= sfi_factor
    
    # Add radio blackout contribution (R-scale events)
    if r_val > 0:
        # R1: +20% absorption, R2: +40%, R3: +60%, R4: +80%, R5: +100%
        base_absorption += (r_val * 0.2)
    
    return min(base_absorption, 1.0)


def calculate_gray_line_enhancement(utc_hour):
    """
    Determine if current time is during gray line (twilight) period.
    
    Gray line propagation occurs at sunrise/sunset when D-layer is minimal
    but F-layer remains ionized. Provides excellent long-distance propagation.
    
    Simplified model: Enhancement during 2 hours around sunrise/sunset
    (approximately 06:00 and 18:00 UTC for global average)
    
    Args:
        utc_hour: Current UTC hour (0-23)
    
    Returns:
        (is_gray_line, enhancement_description)
    """
    # Gray line occurs roughly 06:00 and 18:00 UTC (±1 hour)
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
    Lower bands (80m/40m) handle high K-index better than higher bands.
    
    Args:
        k_index: Planetary K-index (0-9)
        band_mhz: Band frequency in MHz
    
    Returns:
        Impact factor (0.0 = no impact, 1.0 = severe impact)
    """
    try:
        k_val = float(k_index)
    except:
        k_val = 2.0  # Assume typical quiet conditions
    
    # Higher frequencies more affected
    if band_mhz >= 21:  # 15m and higher
        sensitivity = 0.15
    elif band_mhz >= 14:  # 20m
        sensitivity = 0.12
    elif band_mhz >= 7:  # 40m and 30m
        sensitivity = 0.08
    else:  # 80m and 160m
        sensitivity = 0.05
    
    # Calculate impact: K=0 → 0%, K=5 → 75%, K=9 → 135% (capped at 100%)
    impact = min(k_val * sensitivity, 1.0)
    
    return impact


def get_seasonal_factor(month):
    """
    Calculate seasonal propagation factor.
    
    F-layer characteristics vary by season:
    - Winter: Higher foF2 in northern hemisphere (winter anomaly)
    - Summer: Lower foF2 but better Sporadic-E on 6m/10m
    - Equinox (Mar/Sep): Enhanced propagation, longer openings
    
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


def predict_band_conditions(band_mhz, fof2, muf, absorption, k_impact, is_gray_line, month=None):
    """
    Predict propagation conditions for a specific band using all factors.
    
    Args:
        band_mhz: Band frequency in MHz
        fof2: Critical frequency in MHz
        muf: Maximum Usable Frequency in MHz
        absorption: D-layer absorption factor (0-1)
        k_impact: K-index impact factor (0-1)
        is_gray_line: Boolean indicating gray line enhancement
        month: Month number (1-12) for seasonal adjustments
    
    Returns:
        (quality_score, status_emoji, description)
    """
    # Get seasonal factors
    if month:
        f2_factor, es_probability, season_name = get_seasonal_factor(month)
        # Apply seasonal F2-layer adjustment
        fof2_adjusted = fof2 * f2_factor
        muf_adjusted = muf * f2_factor
    else:
        fof2_adjusted = fof2
        muf_adjusted = muf
        es_probability = 0.3
    
    # Calculate usability: band should be between foF2 and MUF
    # Optimal frequency is typically 85% of MUF (MUF factor 0.85)
    optimal_muf = muf_adjusted * 0.85
    
    # Base score based on frequency vs MUF/foF2
    if band_mhz > muf_adjusted:
        base_score = 0.0  # Above MUF - closed
    elif band_mhz > optimal_muf:
        base_score = 0.5  # Between optimal and MUF - marginal
    elif band_mhz < fof2_adjusted:
        # Below foF2 - penetrates but has absorption
        base_score = 0.7 - absorption
    else:
        # Sweet spot: between foF2 and optimal MUF
        base_score = 1.0
    
    # Apply absorption (affects lower frequencies more)
    freq_absorption_factor = max(0.3, 1.0 - (band_mhz / 30.0))
    absorption_penalty = absorption * freq_absorption_factor
    base_score -= absorption_penalty
    
    # Apply K-index impact
    base_score -= k_impact
    
    # Gray line enhancement (+20% for HF bands)
    if is_gray_line and band_mhz >= 3.5 and band_mhz <= 30:
        base_score += 0.2
    
    # Sporadic-E enhancement for 6m and 10m during summer
    if (band_mhz >= 28 and band_mhz <= 54) and es_probability > 0.5:
        base_score += (es_probability * 0.3)
    
    # Clamp score
    final_score = max(0.0, min(1.0, base_score))
    
    # Convert to emoji and description
    if final_score >= 0.75:
        return (final_score, "🟢", "Excellent")
    elif final_score >= 0.55:
        return (final_score, "🟢", "Good")
    elif final_score >= 0.35:
        return (final_score, "🟡", "Fair")
    elif final_score >= 0.15:
        return (final_score, "🟠", "Poor")
    else:
        return (final_score, "🔴", "Closed")


# HAM Radio Trivia and Facts
HAM_TRIVIA = [
    {"fact": "The term 'HAM' radio may come from 'Ham and Hiram' - early amateur radio operators or the 'HAM' station at Harvard.", "category": "History"},
    {"fact": "The first transatlantic radio transmission was made by Guglielmo Marconi in 1901 from Cornwall to Newfoundland.", "category": "History"},
    {"fact": "HF propagation relies on the ionosphere - layers of charged particles 60-600km above Earth.", "category": "Propagation"},
    {"fact": "The 'gray line' is the best time for DX - when the terminator between day/night crosses your signal path.", "category": "Propagation"},
    {"fact": "Solar flares can cause radio blackouts by increasing D-layer absorption of HF signals.", "category": "Space Weather"},
    {"fact": "The 11-year solar cycle dramatically affects HF propagation conditions. We're currently in Solar Cycle 25.", "category": "Space Weather"},
    {"fact": "10 meters (28 MHz) opens up during solar maximum, providing worldwide communication on low power.", "category": "Bands"},
    {"fact": "80 meters (3.5 MHz) is great for nighttime regional communication, often called '75 meters' in the US.", "category": "Bands"},
    {"fact": "2 meters (144 MHz) and 70cm (440 MHz) are the most popular VHF/UHF bands for local communication.", "category": "Bands"},
    {"fact": "The K-index measures geomagnetic activity: 0-1 is calm, 5+ means poor HF conditions but possible aurora!", "category": "Space Weather"},
    {"fact": "A-index is the daily average of K-index. Lower is better for HF propagation (<20 is great!).", "category": "Space Weather"},
    {"fact": "Solar Flux Index (SFI) above 150 means excellent HF conditions. Below 70 means only low bands work well.", "category": "Space Weather"},
    {"fact": "RTTY, PSK31, and FT8 are digital modes that work even when voice is impossible due to poor conditions.", "category": "Modes"},
    {"fact": "FT8 revolutionized weak-signal communication - you can make contacts at -20dB signal-to-noise ratio!", "category": "Modes"},
    {"fact": "CW (Morse code) is still the most efficient mode, working when everything else fails.", "category": "Modes"},
    {"fact": "SSB uses about 2.4 kHz bandwidth, while FM uses about 16 kHz - that's why FM is VHF/UHF only.", "category": "Modes"},
    {"fact": "APRS (Automatic Packet Reporting System) tracks stations, weather, and objects in real-time.", "category": "Digital"},
    {"fact": "Winlink provides email over radio - crucial for emergency communications when internet is down.", "category": "Digital"},
    {"fact": "DMR (Digital Mobile Radio) and D-STAR are digital voice modes popular on VHF/UHF.", "category": "Digital"},
    {"fact": "Your antenna is MORE important than your radio. A dipole in the clear beats a beam in the trees.", "category": "Antennas"},
    {"fact": "A 1/4 wave ground plane antenna is one of the simplest and most effective vertical antennas.", "category": "Antennas"},
    {"fact": "Yagi antennas provide gain and directivity - essential for weak signal work and DXing.", "category": "Antennas"},
    {"fact": "SWR (Standing Wave Ratio) measures antenna efficiency. Under 1.5:1 is great, under 2:1 is acceptable.", "category": "Antennas"},
    {"fact": "Baluns convert between balanced (dipole) and unbalanced (coax) - prevents RF in the shack!", "category": "Antennas"},
    {"fact": "The International Space Station has a ham radio station. Astronauts regularly make contacts!", "category": "Satellites"},
    {"fact": "OSCAR satellites (Orbiting Satellite Carrying Amateur Radio) provide free worldwide communication.", "category": "Satellites"},
    {"fact": "You can bounce signals off the moon (EME - Earth-Moon-Earth) with enough power and a big antenna!", "category": "Satellites"},
    {"fact": "SSTV (Slow Scan TV) lets you send images over radio - the ISS regularly transmits SSTV images!", "category": "Modes"},
    {"fact": "QRP means low power operation - typically 5W or less. Some hams make worldwide contacts on 1W!", "category": "Operating"},
    {"fact": "The term '73' means 'best regards' in ham radio. '88' means 'love and kisses'.", "category": "Codes"},
    {"fact": "CQ DX means 'calling distant stations'. CQ means 'calling any station'.", "category": "Operating"},
    {"fact": "A 'pileup' is when many stations try to contact a rare DX station at once. Chaos ensues!", "category": "Operating"},
    {"fact": "DXCC (DX Century Club) awards require confirmed contacts with 100+ countries. Some have over 340!", "category": "Awards"},
    {"fact": "Field Day is ham radio's biggest event - 24 hours of emergency preparedness training disguised as fun.", "category": "Events"},
    {"fact": "ARRL is the American Radio Relay League - the main organization for US amateur radio since 1914.", "category": "Organizations"},
    {"fact": "Lightning can induce thousands of volts in your antenna. Always ground and disconnect during storms!", "category": "Safety"},
    {"fact": "RF burns are real! High power can cause deep tissue damage even without feeling heat on skin.", "category": "Safety"},
    {"fact": "Never look into a waveguide carrying power - RF energy can cause cataracts!", "category": "Safety"},
    {"fact": "Software Defined Radio (SDR) uses digital signal processing instead of analog circuits - the future of radio!", "category": "Technology"},
    {"fact": "HackRF, RTL-SDR, and LimeSDR are popular SDR platforms for receiving (and transmitting!).", "category": "Technology"},
]


# Frequency bands and their characteristics
FREQUENCY_TRIVIA = [
    {"freq": "160m (1.8 MHz)", "desc": "The 'top band' - nighttime only, great for ragchewing. Requires large antennas.", "propagation": "Ground wave and skywave at night"},
    {"freq": "80m (3.5 MHz)", "desc": "Workhorse band for regional nighttime contacts. Very popular for nets.", "propagation": "200-500 miles at night via skywave"},
    {"freq": "60m (5 MHz)", "desc": "Channelized band with 5 designated frequencies. Great for NVIS emergency comms.", "propagation": "Short to medium range, especially daytime"},
    {"freq": "40m (7 MHz)", "desc": "Works day and night, short to medium range. Most reliable all-around band.", "propagation": "Day: 500 miles, Night: 2000+ miles"},
    {"freq": "30m (10 MHz)", "desc": "CW and digital only, no voice. Excellent for long distance with low power.", "propagation": "Worldwide propagation often possible"},
    {"freq": "20m (14 MHz)", "desc": "The DX band! Worldwide contacts during the day. Most popular band.", "propagation": "Worldwide during daylight hours"},
    {"freq": "17m (18 MHz)", "desc": "Underutilized band with great propagation. Less crowded than 20m.", "propagation": "Similar to 20m but shorter duration"},
    {"freq": "15m (21 MHz)", "desc": "Opens during solar maximum, dead during minimum. Feast or famine!", "propagation": "Worldwide when open, depends on solar cycle"},
    {"freq": "12m (24 MHz)", "desc": "Like 15m but less crowded. CW and digital shine here.", "propagation": "Good DX when solar conditions support it"},
    {"freq": "10m (28 MHz)", "desc": "The 'magic band' - incredible DX when open, dead when closed. Solar dependent.", "propagation": "Can support worldwide FM simplex!"},
    {"freq": "6m (50 MHz)", "desc": "The 'magic band' of VHF. Sporadic E propagation in summer = surprise DX!", "propagation": "Usually line of sight, but can skip 1000+ miles"},
    {"freq": "2m (144 MHz)", "desc": "Most popular VHF band. Repeaters, FM simplex, SSB weak signal work.", "propagation": "Line of sight, occasional tropo and meteor scatter"},
    {"freq": "70cm (440 MHz)", "desc": "Popular UHF band. Great for small antennas and local communication.", "propagation": "Line of sight, good for urban areas"},
    {"freq": "33cm (902 MHz)", "desc": "Experimental band shared with ISM devices. Great for data links.", "propagation": "Short range, but excellent for point-to-point"},
    {"freq": "23cm (1.2 GHz)", "desc": "Microwave ham radio! ATV, data, and experimentation.", "propagation": "Very short range, requires line of sight"},
]

# ARRL Band Plan - US Amateur Radio Allocations
ARRL_BAND_PLAN = {
    "160m": {
        "name": "160 Meters",
        "range": "1.800 - 1.900 MHz",
        "segments": [
            {"freq": "1.800-1.810", "mode": "CW", "notes": "DX window"},
            {"freq": "1.810-1.840", "mode": "CW", "notes": "General CW"},
            {"freq": "1.840-1.900", "mode": "Phone/Digital", "notes": "SSB, AM, Digital"},
        ]
    },
    "80m": {
        "name": "80 Meters",
        "range": "3.500 - 4.000 MHz",
        "segments": [
            {"freq": "3.500-3.600", "mode": "CW", "notes": "DX window, Extra only to 3.525"},
            {"freq": "3.570-3.600", "mode": "Digital", "notes": "RTTY, PSK, FT8"},
            {"freq": "3.600-3.800", "mode": "Phone", "notes": "SSB (Extra), Phone/CW"},
            {"freq": "3.800-4.000", "mode": "Phone", "notes": "SSB ragchew, nets (General+)"},
        ]
    },
    "60m": {
        "name": "60 Meters (Channelized)",
        "range": "5.330 - 5.405 MHz",
        "segments": [
            {"freq": "5.332", "mode": "USB", "notes": "Channel 1 (15W PEP max)"},
            {"freq": "5.348", "mode": "USB", "notes": "Channel 2"},
            {"freq": "5.358.5", "mode": "USB", "notes": "Channel 3"},
            {"freq": "5.373", "mode": "USB", "notes": "Channel 4"},
            {"freq": "5.405", "mode": "USB", "notes": "Channel 5"},
        ]
    },
    "40m": {
        "name": "40 Meters",
        "range": "7.000 - 7.300 MHz",
        "segments": [
            {"freq": "7.000-7.125", "mode": "CW/Digital", "notes": "CW, RTTY, data"},
            {"freq": "7.125-7.175", "mode": "Phone", "notes": "SSB (Extra)"},
            {"freq": "7.175-7.300", "mode": "Phone", "notes": "SSB (General+)"},
        ]
    },
    "30m": {
        "name": "30 Meters",
        "range": "10.100 - 10.150 MHz",
        "segments": [
            {"freq": "10.100-10.150", "mode": "CW/Digital", "notes": "CW, RTTY, PSK only (200W max)"},
        ]
    },
    "20m": {
        "name": "20 Meters (Premier DX Band)",
        "range": "14.000 - 14.350 MHz",
        "segments": [
            {"freq": "14.000-14.070", "mode": "CW", "notes": "CW DX, QRP calling 14.060"},
            {"freq": "14.070-14.095", "mode": "Digital", "notes": "RTTY, PSK31"},
            {"freq": "14.095-14.112", "mode": "Digital", "notes": "Packet, PACTOR"},
            {"freq": "14.112-14.150", "mode": "Phone", "notes": "SSB (Extra)"},
            {"freq": "14.150-14.350", "mode": "Phone", "notes": "SSB DX, General+"},
            {"freq": "14.230", "mode": "SSB", "notes": "SSTV"},
        ]
    },
    "17m": {
        "name": "17 Meters",
        "range": "18.068 - 18.168 MHz",
        "segments": [
            {"freq": "18.068-18.110", "mode": "CW/Digital", "notes": "CW, RTTY, data"},
            {"freq": "18.110-18.168", "mode": "Phone", "notes": "SSB"},
        ]
    },
    "15m": {
        "name": "15 Meters",
        "range": "21.000 - 21.450 MHz",
        "segments": [
            {"freq": "21.000-21.070", "mode": "CW", "notes": "CW, QRP 21.060"},
            {"freq": "21.070-21.110", "mode": "Digital", "notes": "RTTY, PSK"},
            {"freq": "21.110-21.200", "mode": "Phone", "notes": "SSB (Extra)"},
            {"freq": "21.200-21.450", "mode": "Phone", "notes": "SSB (General+)"},
        ]
    },
    "12m": {
        "name": "12 Meters",
        "range": "24.890 - 24.990 MHz",
        "segments": [
            {"freq": "24.890-24.930", "mode": "CW/Digital", "notes": "CW, RTTY, data"},
            {"freq": "24.930-24.990", "mode": "Phone", "notes": "SSB"},
        ]
    },
    "10m": {
        "name": "10 Meters (Magic Band)",
        "range": "28.000 - 29.700 MHz",
        "segments": [
            {"freq": "28.000-28.070", "mode": "CW", "notes": "CW, QRP"},
            {"freq": "28.070-28.190", "mode": "Digital", "notes": "RTTY, PSK, FT8"},
            {"freq": "28.300-28.680", "mode": "Phone", "notes": "SSB (General+)"},
            {"freq": "28.680-29.200", "mode": "Phone", "notes": "SSB, SSTV"},
            {"freq": "29.000-29.200", "mode": "AM", "notes": "AM calling 29.000"},
            {"freq": "29.300-29.510", "mode": "Satellite", "notes": "Satellite downlinks"},
            {"freq": "29.520-29.580", "mode": "Repeater", "notes": "Repeater inputs"},
            {"freq": "29.600", "mode": "FM", "notes": "FM simplex calling"},
            {"freq": "29.620-29.700", "mode": "Repeater", "notes": "Repeater outputs"},
        ]
    },
    "6m": {
        "name": "6 Meters (Magic Band)",
        "range": "50.000 - 54.000 MHz",
        "segments": [
            {"freq": "50.000-50.100", "mode": "CW/Beacons", "notes": "CW, beacons"},
            {"freq": "50.100-50.300", "mode": "SSB/CW", "notes": "SSB DX calling 50.125"},
            {"freq": "50.300-50.600", "mode": "Digital", "notes": "RTTY, PSK, FT8"},
            {"freq": "50.600-50.800", "mode": "Digital", "notes": "Packet, experimental"},
            {"freq": "51.000-54.000", "mode": "FM/Repeaters", "notes": "FM simplex, repeaters"},
            {"freq": "52.525", "mode": "FM", "notes": "National FM simplex"},
        ]
    },
    "2m": {
        "name": "2 Meters (VHF)",
        "range": "144.000 - 148.000 MHz",
        "segments": [
            {"freq": "144.000-144.100", "mode": "CW", "notes": "EME, CW"},
            {"freq": "144.100-144.200", "mode": "SSB/CW", "notes": "SSB calling 144.200"},
            {"freq": "144.200-144.300", "mode": "Digital", "notes": "Weak-signal digital"},
            {"freq": "144.300-145.500", "mode": "Satellite/Digital", "notes": "Satellites, packet"},
            {"freq": "145.500-145.800", "mode": "Misc", "notes": "Experimental"},
            {"freq": "145.800-146.000", "mode": "SSTV", "notes": "SSTV, packet"},
            {"freq": "146.000-147.000", "mode": "Repeaters", "notes": "Repeater outputs +600 kHz"},
            {"freq": "147.000-147.400", "mode": "Simplex", "notes": "FM simplex (146.520 calling)"},
            {"freq": "147.400-148.000", "mode": "Repeaters", "notes": "Repeater inputs"},
        ]
    },
    "70cm": {
        "name": "70 Centimeters (UHF)",
        "range": "420.000 - 450.000 MHz",
        "segments": [
            {"freq": "420.000-426.000", "mode": "Mixed", "notes": "ATV, experimental, repeaters"},
            {"freq": "432.000-432.070", "mode": "CW", "notes": "EME, CW"},
            {"freq": "432.070-432.100", "mode": "SSB/CW", "notes": "SSB calling 432.100"},
            {"freq": "432.100-433.000", "mode": "Digital/Satellite", "notes": "Weak-signal, sat"},
            {"freq": "433.000-435.000", "mode": "Mixed", "notes": "ATV, satellite"},
            {"freq": "435.000-438.000", "mode": "Satellite", "notes": "Satellite only (ITU)"},
            {"freq": "438.000-444.000", "mode": "Repeaters", "notes": "Repeater inputs +5 MHz"},
            {"freq": "446.000", "mode": "FM", "notes": "National FM simplex"},
            {"freq": "446.000-450.000", "mode": "Repeaters", "notes": "Repeater outputs"},
        ]
    },
}

# HAM Radio License Classes and Privileges
HAM_LICENSE_CLASSES = {
    "technician": {
        "name": "Technician Class",
        "code": "FCC Technician",
        "description": "Entry-level license with full VHF/UHF privileges and limited HF access",
        "exam": "35 questions, Element 2",
        "privileges": {
            "HF_Bands": [
                {"band": "80m", "range": "3.525-3.600 MHz", "modes": "CW only", "power": "200W PEP"},
                {"band": "40m", "range": "7.025-7.125 MHz", "modes": "CW only", "power": "200W PEP"},
                {"band": "15m", "range": "21.025-21.200 MHz", "modes": "CW only", "power": "200W PEP"},
                {"band": "10m", "range": "28.000-28.300 MHz", "modes": "CW, RTTY, Data", "power": "200W PEP"},
                {"band": "10m", "range": "28.300-28.500 MHz", "modes": "CW, Phone", "power": "200W PEP"},
            ],
            "VHF_UHF": [
                {"band": "6m", "range": "50.0-54.0 MHz", "modes": "All modes", "power": "1500W PEP"},
                {"band": "2m", "range": "144-148 MHz", "modes": "All modes", "power": "1500W PEP"},
                {"band": "1.25m", "range": "222-225 MHz", "modes": "All modes", "power": "1500W PEP"},
                {"band": "70cm", "range": "420-450 MHz", "modes": "All modes", "power": "1500W PEP"},
                {"band": "33cm", "range": "902-928 MHz", "modes": "All modes", "power": "1500W PEP"},
                {"band": "23cm", "range": "1240-1300 MHz", "modes": "All modes", "power": "1500W PEP"},
            ]
        },
        "summary": "Full privileges on all VHF/UHF bands, limited CW-only access on HF"
    },
    "general": {
        "name": "General Class",
        "code": "FCC General",
        "description": "Mid-level license with most HF voice privileges plus all Technician privileges",
        "exam": "35 questions, Element 3 (must have Technician)",
        "privileges": {
            "HF_Bands": [
                {"band": "160m", "range": "1.800-2.000 MHz", "modes": "All modes", "power": "1500W PEP"},
                {"band": "80m", "range": "3.525-4.000 MHz", "modes": "All modes", "power": "1500W PEP", "notes": "Phone: 3.800-4.000 MHz"},
                {"band": "60m", "range": "5.332-5.405 MHz", "modes": "USB only, 5 channels", "power": "100W PEP (ERP)"},
                {"band": "40m", "range": "7.025-7.300 MHz", "modes": "All modes", "power": "1500W PEP", "notes": "Phone: 7.175-7.300 MHz"},
                {"band": "30m", "range": "10.100-10.150 MHz", "modes": "CW, RTTY, Data only", "power": "200W PEP"},
                {"band": "20m", "range": "14.025-14.350 MHz", "modes": "All modes", "power": "1500W PEP", "notes": "Phone: 14.150-14.350 MHz"},
                {"band": "17m", "range": "18.068-18.168 MHz", "modes": "All modes", "power": "1500W PEP", "notes": "Phone: 18.110-18.168 MHz"},
                {"band": "15m", "range": "21.025-21.450 MHz", "modes": "All modes", "power": "1500W PEP", "notes": "Phone: 21.200-21.450 MHz"},
                {"band": "12m", "range": "24.890-24.990 MHz", "modes": "All modes", "power": "1500W PEP", "notes": "Phone: 24.930-24.990 MHz"},
                {"band": "10m", "range": "28.000-29.700 MHz", "modes": "All modes", "power": "1500W PEP", "notes": "Phone: 28.300-29.700 MHz"},
            ],
            "VHF_UHF": "Same as Technician - full privileges on all VHF/UHF/Microwave bands"
        },
        "summary": "Most HF privileges including phone (SSB), all Technician privileges"
    },
    "extra": {
        "name": "Extra Class",
        "code": "FCC Amateur Extra",
        "description": "Highest license class with full privileges on all amateur bands",
        "exam": "50 questions, Element 4 (must have General)",
        "privileges": {
            "HF_Bands": [
                {"band": "160m", "range": "1.800-2.000 MHz", "modes": "All modes", "power": "1500W PEP"},
                {"band": "80m", "range": "3.500-4.000 MHz", "modes": "All modes", "power": "1500W PEP", "notes": "Full band access"},
                {"band": "60m", "range": "5.332-5.405 MHz", "modes": "USB only, 5 channels", "power": "100W PEP (ERP)"},
                {"band": "40m", "range": "7.000-7.300 MHz", "modes": "All modes", "power": "1500W PEP", "notes": "Full band access"},
                {"band": "30m", "range": "10.100-10.150 MHz", "modes": "CW, RTTY, Data only", "power": "200W PEP"},
                {"band": "20m", "range": "14.000-14.350 MHz", "modes": "All modes", "power": "1500W PEP", "notes": "Full band access"},
                {"band": "17m", "range": "18.068-18.168 MHz", "modes": "All modes", "power": "1500W PEP", "notes": "Full band access"},
                {"band": "15m", "range": "21.000-21.450 MHz", "modes": "All modes", "power": "1500W PEP", "notes": "Full band access"},
                {"band": "12m", "range": "24.890-24.990 MHz", "modes": "All modes", "power": "1500W PEP", "notes": "Full band access"},
                {"band": "10m", "range": "28.000-29.700 MHz", "modes": "All modes", "power": "1500W PEP", "notes": "Full band access"},
            ],
            "VHF_UHF": "Same as Technician/General - full privileges on all VHF/UHF/Microwave bands",
            "Special": [
                "Access to exclusive Extra-only segments on 80m, 40m, 20m, 15m",
                "Shorter vanity callsign options (1x2, 2x1)",
                "Required for VE (Volunteer Examiner) team leadership"
            ]
        },
        "summary": "Full privileges on ALL amateur radio frequencies and modes"
    }
}

# Power limits by band (FCC Part 97)
POWER_LIMITS = {
    "HF": {
        "160m-10m": "1500W PEP (except 60m: 100W ERP, 30m: 200W PEP)",
        "notes": "Reduced power for Technician on HF: 200W PEP"
    },
    "VHF_UHF": {
        "50MHz-1.3GHz": "1500W PEP",
        "notes": "All license classes have same power limits on VHF/UHF"
    },
    "Special": {
        "60m": "100W ERP (Effective Radiated Power) - channelized, not PEP",
        "30m": "200W PEP - CW and digital modes only",
        "Beacon": "100W PEP maximum for beacon stations",
        "Satellite": "Varies by frequency and coordination"
    }
}

# Common Non-Ham Radio Services and Their Frequencies
COMMON_SERVICES = {
    "lora": {
        "name": "LoRa / LoRaWAN",
        "frequencies": [
            {"region": "North America", "freq": "902-928 MHz", "notes": "ISM band, 64 channels"},
            {"region": "Europe", "freq": "863-870 MHz", "notes": "Short range"},
            {"region": "Europe", "freq": "433 MHz", "notes": "Long range"},
            {"region": "Asia", "freq": "920-925 MHz", "notes": "Japan, Korea"},
            {"region": "Asia", "freq": "470 MHz", "notes": "China"},
        ],
        "description": "Long-range, low-power wireless protocol for IoT devices",
        "power": "Typically 14-20 dBm (25-100 mW)",
        "range": "2-5 km urban, 15+ km rural"
    },
    "wifi": {
        "name": "Wi-Fi (802.11)",
        "frequencies": [
            {"band": "2.4 GHz", "freq": "2.400-2.483 GHz", "notes": "11-14 channels (depends on country)"},
            {"band": "5 GHz", "freq": "5.150-5.250 GHz", "notes": "UNII-1 (indoor only)"},
            {"band": "5 GHz", "freq": "5.250-5.350 GHz", "notes": "UNII-2 (DFS required)"},
            {"band": "5 GHz", "freq": "5.470-5.725 GHz", "notes": "UNII-2 Extended (DFS)"},
            {"band": "5 GHz", "freq": "5.725-5.850 GHz", "notes": "UNII-3 (ISM)"},
            {"band": "6 GHz", "freq": "5.925-7.125 GHz", "notes": "Wi-Fi 6E (1200 MHz bandwidth!)"},
        ],
        "description": "Wireless local area network (WLAN) technology",
        "power": "Up to 1W EIRP (varies by band/country)",
        "range": "50m indoor, 100m+ outdoor"
    },
    "bluetooth": {
        "name": "Bluetooth / BLE",
        "frequencies": [
            {"version": "Classic", "freq": "2.400-2.483 GHz", "notes": "79 channels, 1 MHz spacing"},
            {"version": "BLE", "freq": "2.400-2.483 GHz", "notes": "40 channels, 2 MHz spacing"},
        ],
        "description": "Short-range wireless technology for personal area networks",
        "power": "Class 1: 100mW (20 dBm), Class 2: 2.5mW (4 dBm), Class 3: 1mW (0 dBm)",
        "range": "Class 1: 100m, Class 2: 10m, BLE: 50-100m"
    },
    "zigbee": {
        "name": "Zigbee / Thread",
        "frequencies": [
            {"band": "Global", "freq": "2.400-2.483 GHz", "notes": "16 channels"},
            {"band": "Americas", "freq": "902-928 MHz", "notes": "10 channels (802.15.4)"},
            {"band": "Europe", "freq": "868-868.6 MHz", "notes": "1 channel"},
        ],
        "description": "Low-power mesh network protocol for home automation",
        "power": "0-20 dBm (1-100 mW)",
        "range": "10-100m depending on environment"
    },
    "ism": {
        "name": "ISM Bands (Industrial, Scientific, Medical)",
        "frequencies": [
            {"region": "Global", "freq": "6.765-6.795 MHz", "notes": "HF ISM"},
            {"region": "Global", "freq": "13.553-13.567 MHz", "notes": "RFID"},
            {"region": "Global", "freq": "26.957-27.283 MHz", "notes": "CB radio"},
            {"region": "Global", "freq": "40.660-40.700 MHz", "notes": "HF ISM"},
            {"region": "Global", "freq": "433.050-434.790 MHz", "notes": "Europe LPD"},
            {"region": "Global", "freq": "902-928 MHz", "notes": "Americas (915 MHz)"},
            {"region": "Global", "freq": "2.400-2.500 GHz", "notes": "Wi-Fi, Bluetooth, microwave"},
            {"region": "Global", "freq": "5.725-5.875 GHz", "notes": "Wi-Fi, FPV drones"},
            {"region": "Global", "freq": "24-24.25 GHz", "notes": "Motion sensors"},
        ],
        "description": "Unlicensed bands for industrial, scientific, and medical equipment",
        "power": "Varies by band and country",
        "range": "Varies widely by application"
    },
    "frs": {
        "name": "FRS (Family Radio Service)",
        "frequencies": [
            {"channel": "1-7, 15-22", "freq": "462.5625-467.7125 MHz", "notes": "2W max, no license"},
            {"channel": "8-14", "freq": "467.5625-467.7125 MHz", "notes": "0.5W max (shared with GMRS)"},
        ],
        "description": "License-free two-way radio service in US/Canada",
        "power": "0.5-2W depending on channel",
        "range": "0.5-2 miles (terrain dependent)"
    },
    "gmrs": {
        "name": "GMRS (General Mobile Radio Service)",
        "frequencies": [
            {"type": "Simplex", "freq": "462.5500-462.7250 MHz", "notes": "5W handheld, 50W mobile"},
            {"type": "Repeater", "freq": "462.5500-462.7250 MHz", "notes": "Repeater outputs (+5 MHz)"},
            {"type": "Repeater", "freq": "467.5500-467.7250 MHz", "notes": "Repeater inputs"},
        ],
        "description": "Licensed two-way radio service in US (family license)",
        "power": "5W handheld, 50W mobile/base, 50W repeater",
        "range": "1-25 miles depending on power/terrain/repeater"
    },
    "murs": {
        "name": "MURS (Multi-Use Radio Service)",
        "frequencies": [
            {"channel": "1", "freq": "151.820 MHz", "notes": "No license, 2W max"},
            {"channel": "2", "freq": "151.880 MHz", "notes": "No license, 2W max"},
            {"channel": "3", "freq": "151.940 MHz", "notes": "No license, 2W max"},
            {"channel": "4-5", "freq": "154.570-154.600 MHz", "notes": "No license, 2W max"},
        ],
        "description": "License-free VHF business/personal radio service in US",
        "power": "2W max, external antenna allowed",
        "range": "2-5 miles (better than FRS due to VHF propagation)"
    },
    "cb": {
        "name": "CB Radio (Citizens Band)",
        "frequencies": [
            {"band": "11m", "freq": "26.965-27.405 MHz", "notes": "40 channels (US)"},
            {"channel": "9", "freq": "27.065 MHz", "notes": "Emergency/traveler assistance"},
            {"channel": "19", "freq": "27.185 MHz", "notes": "Truckers"},
        ],
        "description": "License-free HF radio service for short-distance communication",
        "power": "4W AM, 12W SSB (US)",
        "range": "1-5 miles typical, 10+ miles with skip propagation"
    },
    "aprs": {
        "name": "APRS (Automatic Packet Reporting System)",
        "frequencies": [
            {"region": "North America", "freq": "144.390 MHz", "notes": "Primary APRS frequency"},
            {"region": "Europe", "freq": "144.800 MHz", "notes": "Primary APRS frequency"},
            {"region": "Asia", "freq": "144.640 MHz", "notes": "Japan APRS"},
            {"region": "Oceania", "freq": "145.175 MHz", "notes": "Australia/NZ APRS"},
        ],
        "description": "Amateur radio packet reporting system for position/telemetry",
        "power": "Varies (ham radio limits)",
        "range": "Typically 50-200 miles via digipeaters/iGates"
    },
    "rfid": {
        "name": "RFID (Radio Frequency Identification)",
        "frequencies": [
            {"type": "LF", "freq": "125-134 kHz", "notes": "Animal tracking, access control"},
            {"type": "HF", "freq": "13.56 MHz", "notes": "NFC, contactless payments, passports"},
            {"type": "UHF", "freq": "433 MHz", "notes": "Active RFID (Europe)"},
            {"type": "UHF", "freq": "860-960 MHz", "notes": "Passive RFID (global)"},
            {"type": "Microwave", "freq": "2.45 GHz", "notes": "Active RFID, toll systems"},
            {"type": "Microwave", "freq": "5.8 GHz", "notes": "Long-range RFID"},
        ],
        "description": "Wireless identification and tracking technology",
        "power": "Passive: powered by reader, Active: battery powered",
        "range": "LF: cm, HF: 1m, UHF: 10m, Microwave: 100m+"
    },
    "fm": {
        "name": "FM Radio (Frequency Modulation)",
        "frequencies": [
            {"region": "North America", "freq": "88-108 MHz", "notes": "87.5-108 MHz in some areas"},
            {"region": "Japan", "freq": "76-95 MHz", "notes": "Extended band"},
            {"region": "Europe", "freq": "87.5-108 MHz", "notes": "Standard FM broadcast"},
            {"region": "OIRT (Russia/Eastern Europe)", "freq": "65.8-74 MHz", "notes": "Legacy band"},
        ],
        "description": "Commercial FM broadcast radio for music and talk",
        "power": "100W-100kW depending on class and location",
        "range": "15-60 miles depending on power and terrain"
    },
    "am": {
        "name": "AM Radio (Amplitude Modulation)",
        "frequencies": [
            {"band": "Longwave", "freq": "148.5-283.5 kHz", "notes": "Europe, Asia, Africa"},
            {"band": "Mediumwave", "freq": "530-1710 kHz", "notes": "AM broadcast band (US/Americas)"},
            {"band": "Mediumwave", "freq": "531-1602 kHz", "notes": "MW broadcast (Europe, 9 kHz spacing)"},
            {"band": "Clear Channel", "freq": "640-1200 kHz", "notes": "50kW stations, wide coverage"},
        ],
        "description": "Commercial AM broadcast radio, long-distance at night",
        "power": "250W-50kW depending on class",
        "range": "5-20 miles day, 100-500+ miles at night (skywave)"
    },
    "shortwave": {
        "name": "Shortwave Radio (HF Broadcasting)",
        "frequencies": [
            {"band": "120m", "freq": "2.3-2.495 MHz", "notes": "Tropical band"},
            {"band": "90m", "freq": "3.2-3.4 MHz", "notes": "Tropical band"},
            {"band": "75m", "freq": "3.9-4.0 MHz", "notes": "Tropical/regional"},
            {"band": "60m", "freq": "4.75-5.06 MHz", "notes": "International broadcast"},
            {"band": "49m", "freq": "5.9-6.2 MHz", "notes": "International broadcast"},
            {"band": "41m", "freq": "7.2-7.45 MHz", "notes": "International broadcast"},
            {"band": "31m", "freq": "9.4-9.9 MHz", "notes": "International broadcast"},
            {"band": "25m", "freq": "11.6-12.1 MHz", "notes": "International broadcast"},
            {"band": "22m", "freq": "13.57-13.87 MHz", "notes": "International broadcast"},
            {"band": "19m", "freq": "15.1-15.8 MHz", "notes": "International broadcast"},
            {"band": "16m", "freq": "17.48-17.9 MHz", "notes": "International broadcast"},
            {"band": "15m", "freq": "18.9-19.02 MHz", "notes": "International broadcast"},
            {"band": "13m", "freq": "21.45-21.85 MHz", "notes": "International broadcast"},
            {"band": "11m", "freq": "25.67-26.1 MHz", "notes": "International broadcast"},
        ],
        "description": "Long-distance international broadcast radio",
        "power": "10kW-500kW for international broadcasters",
        "range": "Global coverage via ionospheric skip"
    },
    "tv": {
        "name": "Television Broadcast",
        "frequencies": [
            {"band": "VHF Low (Ch 2-6)", "freq": "54-88 MHz", "notes": "Channels 2-6 (mostly discontinued)"},
            {"band": "VHF High (Ch 7-13)", "freq": "174-216 MHz", "notes": "Channels 7-13"},
            {"band": "UHF (Ch 14-36)", "freq": "470-608 MHz", "notes": "Digital TV (ATSC 1.0/3.0)"},
            {"band": "UHF (Ch 38-51)", "freq": "614-698 MHz", "notes": "Repacked channels (post-2020)"},
        ],
        "description": "Over-the-air digital television (ATSC in North America)",
        "power": "1kW-1MW ERP depending on market size",
        "range": "30-60 miles line-of-sight"
    },
    "satellite": {
        "name": "Satellite Communications",
        "frequencies": [
            {"band": "L-band", "freq": "1-2 GHz", "notes": "GPS, Iridium, Inmarsat mobile"},
            {"band": "S-band", "freq": "2-4 GHz", "notes": "Weather sats, some comms"},
            {"band": "C-band", "freq": "4-8 GHz", "notes": "Fixed satellite service (FSS)"},
            {"band": "X-band", "freq": "8-12 GHz", "notes": "Military, radar, space comms"},
            {"band": "Ku-band", "freq": "12-18 GHz", "notes": "DBS TV, VSAT"},
            {"band": "K-band", "freq": "18-27 GHz", "notes": "Broadcast, limited use"},
            {"band": "Ka-band", "freq": "26.5-40 GHz", "notes": "High-throughput satellites, Starlink"},
        ],
        "description": "Satellite uplink/downlink for TV, internet, and mobile services",
        "power": "Varies widely (mW to kW)",
        "range": "Global coverage from GEO/MEO/LEO orbits"
    },
    "weather": {
        "name": "Weather Radio & Satellites",
        "frequencies": [
            {"type": "NOAA Weather Radio", "freq": "162.400-162.550 MHz", "notes": "7 channels, continuous broadcast"},
            {"type": "NOAA APT", "freq": "137.1 MHz, 137.9125 MHz", "notes": "Analog weather satellite images"},
            {"type": "Meteor-M2", "freq": "137.1 MHz, 137.9 MHz", "notes": "Russian weather sat (LRPT)"},
            {"type": "GOES HRIT", "freq": "1691 MHz", "notes": "Geostationary weather imagery"},
        ],
        "description": "Weather alerts and satellite imagery reception",
        "power": "NOAA: 300W-1kW, Satellites: varies",
        "range": "NOAA: 40 miles, Satellites: line-of-sight to horizon"
    },
    "marine": {
        "name": "Marine VHF Radio",
        "frequencies": [
            {"channel": "16", "freq": "156.800 MHz", "notes": "Distress, safety, calling (REQUIRED MONITORING)"},
            {"channel": "6", "freq": "156.300 MHz", "notes": "Inter-ship safety"},
            {"channel": "9", "freq": "156.450 MHz", "notes": "Calling (non-commercial)"},
            {"channel": "13", "freq": "156.650 MHz", "notes": "Bridge-to-bridge navigation"},
            {"channel": "70", "freq": "156.525 MHz", "notes": "Digital Selective Calling (DSC)"},
            {"type": "AIS", "freq": "161.975 MHz, 162.025 MHz", "notes": "Automatic Identification System"},
        ],
        "description": "Maritime mobile communication and safety",
        "power": "1W (handheld) to 25W (fixed/mobile)",
        "range": "5-10 miles handheld, 20-60 miles fixed (line-of-sight)"
    },
    "aviation": {
        "name": "Aviation VHF Radio",
        "frequencies": [
            {"type": "Emergency", "freq": "121.5 MHz", "notes": "International emergency frequency"},
            {"type": "VHF Air Band", "freq": "118-137 MHz", "notes": "AM voice, 8.33/25 kHz spacing"},
            {"type": "Tower/Ground", "freq": "118-122 MHz", "notes": "Airport tower and ground control"},
            {"type": "Enroute", "freq": "128-132 MHz", "notes": "Air traffic control"},
            {"type": "ATIS", "freq": "Various", "notes": "Automated Terminal Information"},
            {"type": "ACARS", "freq": "131.550 MHz", "notes": "Aircraft digital datalink"},
        ],
        "description": "Air-to-ground and air traffic control communications",
        "power": "10-25W aircraft radio",
        "range": "100-200 miles at altitude (line-of-sight)"
    },
    "pagers": {
        "name": "Pagers & Alerting",
        "frequencies": [
            {"type": "POCSAG", "freq": "137-138 MHz, 153-154 MHz", "notes": "Legacy paging"},
            {"type": "FLEX", "freq": "929-932 MHz", "notes": "Two-way paging (US)"},
            {"type": "POCSAG", "freq": "169 MHz", "notes": "Europe paging"},
        ],
        "description": "One-way and two-way paging systems",
        "power": "Varies (typically high-power transmitters)",
        "range": "Wide area coverage (city to regional)"
    },
    "cellular": {
        "name": "Cellular Mobile Networks",
        "frequencies": [
            {"band": "700 MHz (Band 12/13/14/17)", "freq": "698-806 MHz", "notes": "LTE low-band, wide coverage"},
            {"band": "850 MHz (Band 5)", "freq": "824-894 MHz", "notes": "2G/3G/4G, wide coverage"},
            {"band": "1900 MHz (PCS, Band 2)", "freq": "1850-1990 MHz", "notes": "2G/3G/4G/5G"},
            {"band": "AWS (Band 4/66)", "freq": "1695-2200 MHz", "notes": "LTE/5G"},
            {"band": "2.5 GHz (Band 41)", "freq": "2496-2690 MHz", "notes": "5G mid-band"},
            {"band": "3.5 GHz (CBRS, Band 48)", "freq": "3550-3700 MHz", "notes": "5G mid-band, shared"},
            {"band": "mmWave (Band 260/261)", "freq": "24-47 GHz", "notes": "5G high-band, short range"},
        ],
        "description": "Mobile phone networks (LTE, 5G, legacy 2G/3G)",
        "power": "23 dBm (200 mW) typical phone output",
        "range": "Low-band: 10+ miles, Mid: 1-3 miles, mmWave: 500-1000 ft"
    },
    "radar": {
        "name": "Radar Systems",
        "frequencies": [
            {"band": "HF (OTH)", "freq": "3-30 MHz", "notes": "Over-the-horizon radar"},
            {"band": "VHF", "freq": "50-330 MHz", "notes": "Long-range surveillance"},
            {"band": "UHF", "freq": "300-1000 MHz", "notes": "Surveillance, early warning"},
            {"band": "L-band", "freq": "1-2 GHz", "notes": "Air traffic control, long-range"},
            {"band": "S-band", "freq": "2-4 GHz", "notes": "Weather radar (WSR-88D), ATC"},
            {"band": "C-band", "freq": "4-8 GHz", "notes": "Weather, fire control"},
            {"band": "X-band", "freq": "8-12 GHz", "notes": "Marine, missile guidance, police"},
            {"band": "Ku/K/Ka", "freq": "12-40 GHz", "notes": "Police, speed cameras, military"},
        ],
        "description": "Radio detection and ranging (aviation, weather, maritime, police)",
        "power": "kW to MW peak power",
        "range": "Varies: miles to hundreds of miles"
    },
    "amateur_satellite": {
        "name": "Amateur Radio Satellites",
        "frequencies": [
            {"band": "2m Uplink", "freq": "145.800-146.000 MHz", "notes": "FM/SSB voice"},
            {"band": "70cm Downlink", "freq": "435-438 MHz", "notes": "FM/SSB/CW/digital"},
            {"band": "2m/70cm", "freq": "Various", "notes": "Linear transponders (SSB/CW)"},
            {"band": "S-band", "freq": "2.4 GHz", "notes": "Downlink (some satellites)"},
            {"band": "L-band", "freq": "1.2 GHz", "notes": "Uplink/downlink (some sats)"},
        ],
        "description": "Amateur radio satellites (FM, linear transponders, digital)",
        "power": "5-50W typical (higher gain antennas help)",
        "range": "Satellite passes (5-15 min windows)"
    },
    "microwave": {
        "name": "Microwave Links & Backhaul",
        "frequencies": [
            {"band": "6 GHz", "freq": "5.925-7.125 GHz", "notes": "Licensed point-to-point links"},
            {"band": "11 GHz", "freq": "10.7-11.7 GHz", "notes": "Common backhaul"},
            {"band": "18 GHz", "freq": "17.7-19.7 GHz", "notes": "Medium-capacity links"},
            {"band": "23 GHz", "freq": "21.2-23.6 GHz", "notes": "Short-haul links"},
            {"band": "26 GHz", "freq": "24.25-26.5 GHz", "notes": "5G backhaul, LMDS"},
            {"band": "38 GHz", "freq": "37-40 GHz", "notes": "High-capacity backhaul"},
            {"band": "60 GHz", "freq": "57-64 GHz", "notes": "Unlicensed, oxygen absorption (WiGig)"},
            {"band": "80 GHz", "freq": "71-86 GHz", "notes": "E-band, ultra-high capacity"},
        ],
        "description": "Point-to-point microwave links for telecom backhaul and data",
        "power": "100mW to 10W+ depending on frequency and distance",
        "range": "1-50 km depending on frequency, power, and path clearance"
    },
    "dmr": {
        "name": "DMR/P25/TETRA (Digital Mobile Radio)",
        "frequencies": [
            {"band": "VHF", "freq": "136-174 MHz", "notes": "DMR, P25 Phase 1/2"},
            {"band": "UHF", "freq": "403-527 MHz", "notes": "DMR, P25, TETRA (Europe 380-470)"},
            {"band": "700/800 MHz", "freq": "764-870 MHz", "notes": "P25 trunked systems (public safety)"},
        ],
        "description": "Digital trunked radio for public safety, commercial, amateur",
        "power": "1-50W depending on application",
        "range": "5-30 miles depending on band and infrastructure"
    },
    "iss": {
        "name": "International Space Station (ISS)",
        "frequencies": [
            {"type": "Voice Downlink", "freq": "145.800 MHz", "notes": "FM voice, SSTV, APRS digipeater"},
            {"type": "APRS", "freq": "145.825 MHz", "notes": "ISS APRS digipeater"},
            {"type": "Packet", "freq": "437.550 MHz", "notes": "Packet radio downlink"},
            {"type": "SSTV", "freq": "145.800 MHz", "notes": "Slow-scan TV images"},
        ],
        "description": "Contact ISS astronauts and use ISS as digipeater/repeater",
        "power": "5-50W with directional antenna (Yagi, Arrow, eggbeater)",
        "range": "Visible passes (5-10 min, several per day)"
    },
    "time_signals": {
        "name": "Time & Frequency Standards",
        "frequencies": [
            {"station": "WWV (Colorado)", "freq": "2.5, 5, 10, 15, 20 MHz", "notes": "NIST time signal, voice/tones"},
            {"station": "WWVH (Hawaii)", "freq": "2.5, 5, 10, 15 MHz", "notes": "NIST time signal, female voice"},
            {"station": "CHU (Canada)", "freq": "3.330, 7.850, 14.670 MHz", "notes": "Canadian time signal"},
            {"station": "DCF77 (Germany)", "freq": "77.5 kHz", "notes": "LF time signal (Europe)"},
            {"station": "MSF (UK)", "freq": "60 kHz", "notes": "UK time signal"},
            {"station": "WWVB (Colorado)", "freq": "60 kHz", "notes": "US atomic clock reference"},
        ],
        "description": "Official time and frequency standard broadcasts",
        "power": "2.5kW-10kW (WWVB: 70kW)",
        "range": "WWV/WWVH: global HF, WWVB/DCF77: 1000+ miles"
    },
    "vlf": {
        "name": "VLF/ELF (Very Low / Extremely Low Frequency)",
        "frequencies": [
            {"band": "ELF", "freq": "3-30 Hz", "notes": "Submarine communications (mostly discontinued)"},
            {"band": "SLF", "freq": "30-300 Hz", "notes": "Submarine communications"},
            {"band": "ULF", "freq": "300-3000 Hz", "notes": "Through-earth communications, geophysics"},
            {"band": "VLF", "freq": "3-30 kHz", "notes": "Navigation (LORAN-C), submarine comms"},
            {"type": "NAA Cutler", "freq": "24 kHz", "notes": "US Navy VLF transmitter (1MW)"},
            {"type": "NWC Australia", "freq": "19.8 kHz", "notes": "Naval comms (1MW)"},
        ],
        "description": "Ultra-long-range, ground/water-penetrating communications",
        "power": "100kW-1MW+ (massive antenna systems)",
        "range": "Global, penetrates seawater (submarine depth comms)"
    },
    "radio_astronomy": {
        "name": "Radio Astronomy (Protected Bands)",
        "frequencies": [
            {"band": "HI Line", "freq": "1420.405 MHz", "notes": "Neutral hydrogen (21 cm line)"},
            {"band": "OH Lines", "freq": "1612-1720 MHz", "notes": "Hydroxyl radical emissions"},
            {"band": "CMB", "freq": "22 GHz", "notes": "Cosmic microwave background"},
            {"band": "Water Line", "freq": "22.235 GHz", "notes": "Water vapor emission"},
            {"band": "Ammonia", "freq": "23.694 GHz", "notes": "Ammonia emission"},
            {"band": "Continuum", "freq": "Various", "notes": "1-100+ GHz, pulsars, quasars, galaxies"},
        ],
        "description": "Protected radio spectrum for astronomical observations",
        "power": "N/A (receive-only, extremely sensitive)",
        "range": "Cosmic (billions of light-years)"
    },
    "sstv": {
        "name": "SSTV (Slow-Scan Television)",
        "frequencies": [
            {"band": "HF", "freq": "14.230 MHz", "notes": "20m band (primary SSTV frequency)"},
            {"band": "HF", "freq": "7.171 MHz", "notes": "40m band SSTV"},
            {"band": "HF", "freq": "3.845 MHz", "notes": "80m band SSTV"},
            {"band": "VHF", "freq": "145.500 MHz", "notes": "2m FM SSTV"},
            {"band": "ISS", "freq": "145.800 MHz", "notes": "SSTV from space station"},
        ],
        "description": "Analog image transmission over ham radio (picture in 1-2 minutes)",
        "power": "5-100W typical amateur radio",
        "range": "HF: global via skip, VHF: line-of-sight"
    },
    "atv": {
        "name": "ATV (Amateur Television)",
        "frequencies": [
            {"band": "70cm", "freq": "420-450 MHz", "notes": "Analog/digital ATV"},
            {"band": "33cm", "freq": "902-928 MHz", "notes": "ATV, fast-scan"},
            {"band": "23cm", "freq": "1240-1300 MHz", "notes": "Primary ATV band"},
            {"band": "13cm", "freq": "2390-2450 MHz", "notes": "Digital ATV, DVB-S/T"},
            {"band": "Higher", "freq": "3.3, 5.6, 10 GHz", "notes": "Experimental, narrow bandwidth"},
        ],
        "description": "Full-motion video transmission by amateur radio operators",
        "power": "1-50W with high-gain antennas",
        "range": "10-50 miles line-of-sight (more via repeaters)"
    },
    "trunked": {
        "name": "Trunked Radio (Public Safety)",
        "frequencies": [
            {"band": "VHF", "freq": "150-174 MHz", "notes": "Older analog/digital trunked"},
            {"band": "UHF (T-Band)", "freq": "470-512 MHz", "notes": "Public safety (some areas)"},
            {"band": "700 MHz", "freq": "764-776, 794-806 MHz", "notes": "FirstNet, P25 Phase 2"},
            {"band": "800 MHz", "freq": "851-870 MHz", "notes": "Legacy Motorola, EDACS, P25"},
        ],
        "description": "Digital trunked systems for police, fire, EMS, government",
        "power": "1-50W mobile/portable, repeaters up to 100W+",
        "range": "5-30 miles per site, wide-area via multiple sites"
    },
    "wireless_mic": {
        "name": "Wireless Microphones & IEM",
        "frequencies": [
            {"band": "VHF", "freq": "174-216 MHz", "notes": "Legacy wireless mics (limited)"},
            {"band": "UHF (TV)", "freq": "470-608 MHz", "notes": "White space devices (varies by location)"},
            {"band": "UHF (TV)", "freq": "614-698 MHz", "notes": "Limited after 2020 repack"},
            {"band": "900 MHz", "freq": "902-928 MHz", "notes": "License-free, some interference"},
            {"band": "1.9 GHz", "freq": "1920-1930 MHz", "notes": "DECT wireless mics"},
            {"band": "2.4 GHz", "freq": "2.4-2.4835 GHz", "notes": "Digital wireless (crowded)"},
        ],
        "description": "Professional and consumer wireless audio (mics, IEM, intercom)",
        "power": "10-50 mW typical",
        "range": "100-300 feet depending on frequency and environment"
    },
    "rc": {
        "name": "Radio Control (RC)",
        "frequencies": [
            {"band": "27 MHz", "freq": "26.995-27.255 MHz", "notes": "Citizens band RC (legacy)"},
            {"band": "49 MHz", "freq": "49.830-49.890 MHz", "notes": "Surface RC (cars, boats)"},
            {"band": "72 MHz", "freq": "72.010-72.990 MHz", "notes": "Aircraft RC (legacy, US)"},
            {"band": "75 MHz", "freq": "75.410-75.990 MHz", "notes": "Surface RC (legacy, US)"},
            {"band": "433 MHz", "freq": "433.050-434.790 MHz", "notes": "ISM RC (Europe)"},
            {"band": "900 MHz", "freq": "902-928 MHz", "notes": "Long-range RC (FPV, control)"},
            {"band": "2.4 GHz", "freq": "2.400-2.483 GHz", "notes": "Modern RC (Spektrum, Futaba, FrSky)"},
            {"band": "5.8 GHz", "freq": "5.645-5.945 GHz", "notes": "FPV video (racing drones)"},
        ],
        "description": "Remote control for aircraft, cars, boats, drones",
        "power": "10-1000 mW depending on application",
        "range": "100m-10+ km depending on frequency, power, and line-of-sight"
    },
    "garage": {
        "name": "Garage Doors & Keyless Entry",
        "frequencies": [
            {"region": "North America", "freq": "315 MHz", "notes": "Garage doors, car fobs, tire pressure"},
            {"region": "Europe/Asia", "freq": "433.92 MHz", "notes": "Garage doors, car fobs"},
            {"region": "Japan", "freq": "390 MHz", "notes": "Car keyless entry"},
            {"type": "Rolling Code", "freq": "315/433 MHz", "notes": "Secure garage door openers (KeeLoq, etc.)"},
        ],
        "description": "Wireless garage door openers and automotive keyless entry",
        "power": "1-10 mW typical",
        "range": "30-100 feet typical"
    },
}


class Radiohead(commands.Cog):
    """HAM Radio bot - propagation, news, and frequency trivia."""
    
    def __init__(self, bot):
        self.bot = bot
        self.session = None
        self.state_file = 'data/solar_state.json'
        self.state = self._load_state()
    
    def _load_state(self):
        """Load solar poster state from file."""
        try:
            if os.path.exists(self.state_file):
                with open(self.state_file, 'r') as f:
                    state = json.load(f)
            else:
                state = {
                    'last_posted': None,
                    'channel_id': None,
                    'enabled': False
                }
        except Exception as e:
            logger.error(f"Error loading solar state: {e}")
            state = {
                'last_posted': None,
                'channel_id': None,
                'enabled': False
            }
        
        # Check for environment variable override
        env_chan = os.getenv('SOLAR_POST_CHANNEL_ID')
        if env_chan and env_chan.isdigit():
            state['channel_id'] = int(env_chan)
            logger.info(f"Using solar channel from environment: {env_chan}")
        
        return state
    
    def _save_state(self):
        """Save solar poster state to file."""
        try:
            os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
            with open(self.state_file, 'w') as f:
                json.dump(self.state, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving solar state: {e}")
    
    async def cog_load(self):
        """Create aiohttp session and start auto-poster when cog loads."""
        self.session = aiohttp.ClientSession()
        if self.state.get('enabled', False):
            self.solar_auto_poster.start()
    
    async def cog_unload(self):
        """Close aiohttp session and stop auto-poster when cog unloads."""
        self.solar_auto_poster.cancel()
        if self.session:
            await self.session.close()
    
    @commands.hybrid_command(name='ham_class', description='View HAM radio license class privileges and power limits')
    async def ham_class(self, ctx: commands.Context, license_class: str = None):
        """
        Display information about HAM radio license classes and their privileges.
        
        Usage:
            !ham_class                  - Overview of all license classes
            !ham_class technician       - Technician class details
            !ham_class general          - General class details
            !ham_class extra            - Extra class details
        """
        # If no class specified, show overview
        if not license_class:
            embed = discord.Embed(
                title="📻 US Amateur Radio License Classes",
                description="Three license classes with progressively more privileges. Click for details!",
                color=0x1E88E5
            )
            
            # Technician
            tech = HAM_LICENSE_CLASSES["technician"]
            embed.add_field(
                name=f"🟢 {tech['name']}",
                value=(
                    f"{tech['description']}\n"
                    f"**Exam:** {tech['exam']}\n"
                    f"**Privileges:** {tech['summary']}"
                ),
                inline=False
            )
            
            # General
            gen = HAM_LICENSE_CLASSES["general"]
            embed.add_field(
                name=f"🟡 {gen['name']}",
                value=(
                    f"{gen['description']}\n"
                    f"**Exam:** {gen['exam']}\n"
                    f"**Privileges:** {gen['summary']}"
                ),
                inline=False
            )
            
            # Extra
            extra = HAM_LICENSE_CLASSES["extra"]
            embed.add_field(
                name=f"🔴 {extra['name']}",
                value=(
                    f"{extra['description']}\n"
                    f"**Exam:** {extra['exam']}\n"
                    f"**Privileges:** {extra['summary']}"
                ),
                inline=False
            )
            
            # Power limits summary
            embed.add_field(
                name="⚡ Power Limits",
                value=(
                    f"**HF (1.8-30 MHz):** {POWER_LIMITS['HF']['160m-10m']}\n"
                    f"**VHF/UHF (50 MHz+):** {POWER_LIMITS['VHF_UHF']['50MHz-1.3GHz']}\n"
                    f"_Special limits apply to 60m (100W ERP) and 30m (200W PEP)_"
                ),
                inline=False
            )
            
            embed.set_footer(text="Use /ham_class <class> for detailed band privileges • Example: /ham_class general")
            
            await ctx.send(embed=embed)
            return
        
        # Look up specific license class
        license_class = license_class.lower().strip()
        
        if license_class not in HAM_LICENSE_CLASSES:
            await ctx.send(f"❌ License class `{license_class}` not found. Available: technician, general, extra")
            return
        
        lic = HAM_LICENSE_CLASSES[license_class]
        
        # Color coding by class
        colors = {
            "technician": 0x43A047,
            "general": 0xFF9800,
            "extra": 0xE53935
        }
        
        embed = discord.Embed(
            title=f"📻 {lic['name']}",
            description=f"{lic['description']}\n\n**{lic['exam']}**",
            color=colors.get(license_class, 0x607D8B)
        )
        
        # HF Band privileges
        if "HF_Bands" in lic['privileges']:
            hf_list = []
            for band_priv in lic['privileges']['HF_Bands']:
                entry = f"**{band_priv['band']}:** {band_priv['range']}"
                if 'modes' in band_priv:
                    entry += f"\n  Modes: {band_priv['modes']}"
                if 'power' in band_priv:
                    entry += f"\n  Power: {band_priv['power']}"
                if 'notes' in band_priv:
                    entry += f"\n  _{band_priv['notes']}_"
                hf_list.append(entry)
            
            # Split into multiple fields if too long
            hf_text = "\n\n".join(hf_list)
            if len(hf_text) > 1024:
                # Split into two fields
                mid = len(hf_list) // 2
                embed.add_field(
                    name="📡 HF Band Privileges (Part 1)",
                    value="\n\n".join(hf_list[:mid]),
                    inline=False
                )
                embed.add_field(
                    name="📡 HF Band Privileges (Part 2)",
                    value="\n\n".join(hf_list[mid:]),
                    inline=False
                )
            else:
                embed.add_field(
                    name="📡 HF Band Privileges",
                    value=hf_text,
                    inline=False
                )
        
        # VHF/UHF privileges
        if "VHF_UHF" in lic['privileges']:
            if isinstance(lic['privileges']['VHF_UHF'], str):
                # Simple string description
                embed.add_field(
                    name="📻 VHF/UHF Privileges",
                    value=lic['privileges']['VHF_UHF'],
                    inline=False
                )
            else:
                # Detailed list
                vhf_list = []
                for band_priv in lic['privileges']['VHF_UHF']:
                    entry = f"**{band_priv['band']}:** {band_priv['range']}\n  {band_priv['modes']} - {band_priv['power']}"
                    vhf_list.append(entry)
                
                embed.add_field(
                    name="📻 VHF/UHF/Microwave Privileges",
                    value="\n\n".join(vhf_list),
                    inline=False
                )
        
        # Special privileges (Extra class)
        if "Special" in lic['privileges']:
            embed.add_field(
                name="⭐ Extra Class Special Privileges",
                value="\n".join([f"• {item}" for item in lic['privileges']['Special']]),
                inline=False
            )
        
        # Key highlights
        highlights = {
            "technician": [
                "✅ Full VHF/UHF privileges (repeaters, FM, satellites)",
                "✅ 10m phone privileges (28.3-28.5 MHz)",
                "⚠️ Limited HF (CW only on 80m, 40m, 15m)",
                "💡 Great for local communication and satellites"
            ],
            "general": [
                "✅ Most HF phone (SSB) privileges",
                "✅ All Technician privileges",
                "✅ Access to premier DX frequencies",
                "💡 Recommended for HF enthusiasts"
            ],
            "extra": [
                "✅ Full privileges on ALL bands",
                "✅ Access to exclusive Extra-only segments",
                "✅ Shorter vanity callsigns (1x2, 2x1)",
                "💡 Maximum operating flexibility"
            ]
        }
        
        if license_class in highlights:
            embed.add_field(
                name="🎯 Key Highlights",
                value="\n".join(highlights[license_class]),
                inline=False
            )
        
        embed.set_footer(text="73! • Use /bandplan <band> for detailed frequency plans • /solar for conditions")
        
        await ctx.send(embed=embed)
    
    @commands.hybrid_command(name='hamradio', description='Get HAM radio trivia and facts')
    async def hamradio(self, ctx: commands.Context):
        """
        Get random HAM radio trivia, facts, and tips.
        
        Usage:
            !hamradio
            /hamradio
        """
        trivia = random.choice(HAM_TRIVIA)
        
        # Color based on category
        colors = {
            "History": 0x8B4513,
            "Propagation": 0x1E88E5,
            "Space Weather": 0xFF6F00,
            "Bands": 0x43A047,
            "Modes": 0x5E35B1,
            "Digital": 0x00ACC1,
            "Antennas": 0xFDD835,
            "Satellites": 0x3949AB,
            "Operating": 0x00897B,
            "Codes": 0x6D4C41,
            "Awards": 0xFFB300,
            "Events": 0xE53935,
            "Organizations": 0x1976D2,
            "Safety": 0xD32F2F,
            "Technology": 0x7B1FA2,
        }
        
        color = colors.get(trivia['category'], 0x607D8B)
        
        embed = discord.Embed(
            title=f"📻 HAM Radio Trivia - {trivia['category']}",
            description=trivia['fact'],
            color=color
        )
        
        embed.set_footer(text="73! • Use !hamradio for more • !solar for current conditions")
        
        await ctx.send(embed=embed)
    
    @commands.hybrid_command(name='frequency', description='Look up frequency information for ham bands or services')
    async def frequency(self, ctx: commands.Context, service: str = None):
        """
        Get information about HAM radio frequency bands or common radio services.
        
        Usage:
            !frequency                 - Random HAM band info
            !frequency tv              - TV broadcast bands
            !frequency fm              - FM radio
            !frequency am              - AM radio
            !frequency shortwave       - Shortwave broadcast bands
            !frequency satellite       - Satellite communication bands
            !frequency microwave       - Microwave links and backhaul
            !frequency iss             - International Space Station
            !frequency time_signals    - WWV, WWVH, CHU time standards
            
        Broadcasting: tv, fm, am, shortwave, satellite, weather, wireless_mic
        Amateur: aprs, amateur_satellite, iss, sstv, atv
        Commercial: cellular, pagers, radar, microwave, dmr, trunked
        Unlicensed: wifi, bluetooth, zigbee, lora, ism, frs, gmrs, murs, cb, rfid, rc, garage
        Safety/Science: marine, aviation, weather, time_signals, vlf, radio_astronomy
        
        Use /bandplan for full ARRL amateur radio band plan
        """
        # If no service specified, show random ham band
        if not service:
            freq_info = random.choice(FREQUENCY_TRIVIA)
            
            embed = discord.Embed(
                title=f"📡 Frequency Band: {freq_info['freq']}",
                description=freq_info['desc'],
                color=0x43A047
            )
            
            embed.add_field(name="Propagation", value=freq_info['propagation'], inline=False)
            embed.set_footer(text="73! • Use /frequency <service> for service lookups • /bandplan for ARRL plan")
            
            await ctx.send(embed=embed)
            return
        
        # Look up service
        service = service.lower().strip()
        
        if service not in COMMON_SERVICES:
            available = ", ".join(sorted(COMMON_SERVICES.keys()))
            await ctx.send(f"❌ Service `{service}` not found. Available: {available}")
            return
        
        svc = COMMON_SERVICES[service]
        
        embed = discord.Embed(
            title=f"📡 {svc['name']}",
            description=svc['description'],
            color=0x00ACC1
        )
        
        # Build frequency list
        freq_list = []
        for freq_entry in svc['frequencies']:
            # Handle different dict key structures
            if 'region' in freq_entry:
                freq_list.append(f"**{freq_entry['region']}:** {freq_entry['freq']}")
                if 'notes' in freq_entry:
                    freq_list.append(f"  _{freq_entry['notes']}_")
            elif 'band' in freq_entry:
                freq_list.append(f"**{freq_entry['band']}:** {freq_entry['freq']}")
                if 'notes' in freq_entry:
                    freq_list.append(f"  _{freq_entry['notes']}_")
            elif 'version' in freq_entry:
                freq_list.append(f"**{freq_entry['version']}:** {freq_entry['freq']}")
                if 'notes' in freq_entry:
                    freq_list.append(f"  _{freq_entry['notes']}_")
            elif 'type' in freq_entry:
                freq_list.append(f"**{freq_entry['type']}:** {freq_entry['freq']}")
                if 'notes' in freq_entry:
                    freq_list.append(f"  _{freq_entry['notes']}_")
            elif 'channel' in freq_entry:
                freq_list.append(f"**Ch {freq_entry['channel']}:** {freq_entry['freq']}")
                if 'notes' in freq_entry:
                    freq_list.append(f"  _{freq_entry['notes']}_")
            else:
                freq_list.append(f"{freq_entry.get('freq', 'N/A')}")
        
        embed.add_field(
            name="Frequencies",
            value="\n".join(freq_list),
            inline=False
        )
        
        if 'power' in svc:
            embed.add_field(name="Power", value=svc['power'], inline=True)
        
        if 'range' in svc:
            embed.add_field(name="Range", value=svc['range'], inline=True)
        
        embed.set_footer(text=f"Use /frequency <service> to look up other services • /bandplan for ARRL")
        
        await ctx.send(embed=embed)
    
    @commands.hybrid_command(name='bandplan', description='Display ARRL band plan for amateur radio')
    async def bandplan(self, ctx: commands.Context, band: str = None):
        """
        Display the ARRL band plan for US amateur radio frequencies.
        
        Usage:
            !bandplan           - List all ham bands
            !bandplan 20m       - Detailed 20m band plan
            !bandplan 2m        - Detailed 2m band plan
            
        Available bands: 160m, 80m, 60m, 40m, 30m, 20m, 17m, 15m, 12m, 10m, 6m, 2m, 70cm
        """
        # If no band specified, show overview
        if not band:
            embed = discord.Embed(
                title="📻 ARRL Amateur Radio Band Plan",
                description="US amateur radio frequency allocations. Use `/bandplan <band>` for details.",
                color=0x1E88E5
            )
            
            # HF Bands
            hf_bands = []
            for band_key in ["160m", "80m", "60m", "40m", "30m", "20m", "17m", "15m", "12m", "10m"]:
                if band_key in ARRL_BAND_PLAN:
                    plan = ARRL_BAND_PLAN[band_key]
                    hf_bands.append(f"**{plan['name']}:** {plan['range']}")
            
            embed.add_field(
                name="HF Bands (1.8-30 MHz)",
                value="\n".join(hf_bands),
                inline=False
            )
            
            # VHF/UHF Bands
            vhf_bands = []
            for band_key in ["6m", "2m", "70cm"]:
                if band_key in ARRL_BAND_PLAN:
                    plan = ARRL_BAND_PLAN[band_key]
                    vhf_bands.append(f"**{plan['name']}:** {plan['range']}")
            
            embed.add_field(
                name="VHF/UHF Bands",
                value="\n".join(vhf_bands),
                inline=False
            )
            
            embed.set_footer(text="Use /bandplan <band> for detailed allocations • Example: /bandplan 20m")
            
            await ctx.send(embed=embed)
            return
        
        # Look up specific band
        band = band.lower().strip()
        
        if band not in ARRL_BAND_PLAN:
            available = ", ".join(sorted(ARRL_BAND_PLAN.keys()))
            await ctx.send(f"❌ Band `{band}` not found. Available: {available}")
            return
        
        plan = ARRL_BAND_PLAN[band]
        
        embed = discord.Embed(
            title=f"📻 {plan['name']} Band Plan",
            description=f"**Frequency Range:** {plan['range']}",
            color=0x43A047
        )
        
        # Add segments
        for i, segment in enumerate(plan['segments'], 1):
            mode = segment.get('mode', 'Mixed')
            notes = segment.get('notes', '')
            
            field_value = f"**Mode:** {mode}"
            if notes:
                field_value += f"\n{notes}"
            
            embed.add_field(
                name=f"{segment['freq']} MHz",
                value=field_value,
                inline=False
            )
        
        # Add usage notes for specific bands
        usage_notes = {
            "20m": "🌍 **Premier DX Band** - Worldwide propagation during daylight",
            "10m": "✨ **Magic Band** - Opens during solar maximum for incredible DX",
            "6m": "✨ **Magic Band of VHF** - Sporadic-E propagation in summer",
            "2m": "📡 **Most Popular VHF** - FM simplex calling: 146.520 MHz",
            "70cm": "📡 **Popular UHF Band** - FM simplex calling: 446.000 MHz",
            "40m": "⚡ **Reliable All-Around** - Works day and night",
            "80m": "🌙 **Nighttime Workhorse** - Excellent for regional contacts",
        }
        
        if band in usage_notes:
            embed.add_field(
                name="ℹ️ Usage Notes",
                value=usage_notes[band],
                inline=False
            )
        
        embed.set_footer(text="73 de ARRL • Use /solar for current propagation conditions")
        
        await ctx.send(embed=embed)
    
    @commands.hybrid_command(name='propagation', description='Get current HF propagation conditions (alias for !solar)')
    async def propagation(self, ctx: commands.Context):
        """
        Get current HF propagation conditions from NOAA Space Weather.
        This is an alias for the !solar command.
        
        Usage:
            !propagation
            /propagation
        """
        # Redirect to solar command
        await self.solar(ctx)
    
    @commands.hybrid_command(name='solar', description='Get detailed solar weather report and band predictions')
    async def solar(self, ctx: commands.Context):
        """
        Get comprehensive solar weather report with band-by-band propagation predictions.
        Fetches live data from NOAA Space Weather Prediction Center.
        
        Usage:
            !solar
            /solar
        """
        await ctx.defer()
        
        try:
            # Import the shared solar embed generator
            from utils.solar_embed import create_solar_embed
            
            if not self.session:
                self.session = aiohttp.ClientSession()
            
            # Use the shared embed generator (same as automated reports)
            embed = await create_solar_embed(self.session)
            await ctx.send(embed=embed)
                
        except Exception as e:
            logger.error(f"Error fetching solar weather data: {e}")
            await ctx.send("❌ Error fetching solar weather data. Please try again later!")
    
    @tasks.loop(hours=12)
    async def solar_auto_poster(self):
        """Automatically post solar/propagation data every 12 hours."""
        try:
            # Skip if disabled
            if not self.state.get('enabled', False):
                return
            
            channel_id = self.state.get('channel_id')
            if not channel_id:
                return
            
            channel = self.bot.get_channel(channel_id)
            if not channel:
                logger.warning(f"Solar auto-poster: Channel not found")
                return
            
            # Fetch and post solar data
            try:
                async with self.session.get("https://services.swpc.noaa.gov/json/f10_7cm_flux.json", timeout=10) as resp:
                    if resp.status == 200:
                        flux_data = await resp.json()
                        flux = flux_data[0]['flux'] if flux_data else 'N/A'
                        
                        async with self.session.get("https://services.swpc.noaa.gov/json/planetary_k_index_1m.json", timeout=10) as resp2:
                            if resp2.status == 200:
                                k_data = await resp2.json()
                                k_index = k_data[-1]['kp_index'] if k_data else 'N/A'
                                
                                # Create embed
                                embed = discord.Embed(
                                    title="📡 Solar & Propagation Update",
                                    description="*Automatic 12-hour update for radio operators*",
                                    color=0x1E88E5,
                                    timestamp=datetime.utcnow()
                                )
                                
                                embed.add_field(
                                    name="☀️ Solar Flux Index (SFI)",
                                    value=f"**{flux}** sfu",
                                    inline=True
                                )
                                
                                embed.add_field(
                                    name="🧲 K-Index",
                                    value=f"**{k_index}**",
                                    inline=True
                                )
                                
                                # Interpret conditions
                                try:
                                    flux_val = float(flux)
                                    k_val = float(k_index)
                                    
                                    if flux_val > 150:
                                        conditions = "🟢 **Excellent HF Conditions**"
                                    elif flux_val > 100:
                                        conditions = "🟡 **Good HF Conditions**"
                                    else:
                                        conditions = "🟠 **Fair HF Conditions**"
                                    
                                    if k_val >= 5:
                                        conditions += "\n⚠️ High K-index may degrade propagation"
                                    
                                    embed.add_field(
                                        name="📊 Overall Assessment",
                                        value=conditions,
                                        inline=False
                                    )
                                except:
                                    pass
                                
                                # Best bands right now
                                now_hour = datetime.utcnow().hour
                                if 12 <= now_hour <= 22:
                                    best_now = "**Best Bands:** 20m, 17m, 15m, 40m"
                                else:
                                    best_now = "**Best Bands:** 80m, 40m, 30m"
                                
                                embed.add_field(
                                    name="📻 Recommended Bands",
                                    value=best_now,
                                    inline=False
                                )
                                
                                embed.set_footer(text="73 de Penguin Overlord! • Use /solar for detailed info • Posts every 12 hours")
                                
                                await channel.send(embed=embed)
                                self.state['last_posted'] = datetime.utcnow().isoformat()
                                self._save_state()
                                logger.info(f"Solar auto-poster: Posted successfully")
            
            except Exception as e:
                logger.error(f"Solar auto-poster: Error fetching data: {e}")
        
        except Exception as e:
            logger.error(f"Solar auto-poster error: {e}")
    
    @solar_auto_poster.before_loop
    async def before_solar_auto_poster(self):
        """Wait for the bot to be ready before starting the auto-poster."""
        await self.bot.wait_until_ready()
    
    @commands.hybrid_command(name='solar_set_channel', description='Set the channel for automatic solar/propagation updates')
    @commands.has_permissions(manage_guild=True)
    async def solar_set_channel(self, ctx: commands.Context, channel: discord.TextChannel = None):
        """
        Set the channel where solar/propagation data will be posted every 12 hours.
        
        Usage:
            !solar_set_channel #radioheads
            /solar_set_channel channel:#radioheads
        
        Requires: Manage Server permission
        """
        channel = channel or ctx.channel
        self.state['channel_id'] = channel.id
        self._save_state()
        await ctx.send(f"✅ Solar/propagation updates will be posted to {channel.mention} every 12 hours.\n"
                      f"Use `/solar_enable` to start automatic posting.")
    
    @commands.hybrid_command(name='solar_enable', description='Enable automatic solar/propagation updates')
    @commands.is_owner()
    async def solar_enable(self, ctx: commands.Context):
        """
        Enable automatic solar/propagation updates every 12 hours.
        
        Usage:
            !solar_enable
            /solar_enable
        
        Requires: Bot owner only
        """
        if not self.state.get('channel_id'):
            await ctx.send("❌ Please set a channel first with `/solar_set_channel`")
            return
        
        self.state['enabled'] = True
        self._save_state()
        
        if not self.solar_auto_poster.is_running():
            self.solar_auto_poster.start()
        
        channel = self.bot.get_channel(self.state['channel_id'])
        await ctx.send(f"✅ Solar/propagation auto-posting **enabled** in {channel.mention if channel else 'the configured channel'}!\n"
                      f"Updates will be posted every 12 hours.")
    
    @commands.hybrid_command(name='solar_disable', description='Disable automatic solar/propagation updates')
    @commands.is_owner()
    async def solar_disable(self, ctx: commands.Context):
        """
        Disable automatic solar/propagation updates.
        
        Usage:
            !solar_disable
            /solar_disable
        
        Requires: Bot owner only
        """
        self.state['enabled'] = False
        self._save_state()
        
        if self.solar_auto_poster.is_running():
            self.solar_auto_poster.cancel()
        
        await ctx.send("✅ Solar/propagation auto-posting **disabled**.")
    
    @commands.hybrid_command(name='solar_status', description='Check solar auto-poster status')
    async def solar_status(self, ctx: commands.Context):
        """
        Check the status of the solar/propagation auto-poster.
        
        Usage:
            !solar_status
            /solar_status
        """
        channel_id = self.state.get('channel_id')
        channel = self.bot.get_channel(channel_id) if channel_id else None
        enabled = self.state.get('enabled', False)
        last_posted = self.state.get('last_posted')
        
        embed = discord.Embed(
            title="📡 Solar Auto-Poster Status",
            color=0x1E88E5 if enabled else 0x757575
        )
        
        embed.add_field(
            name="Status",
            value="🟢 Enabled" if enabled else "🔴 Disabled",
            inline=True
        )
        
        embed.add_field(
            name="Channel",
            value=channel.mention if channel else "Not set",
            inline=True
        )
        
        embed.add_field(
            name="Frequency",
            value="Every 12 hours",
            inline=True
        )
        
        if last_posted:
            embed.add_field(
                name="Last Posted",
                value=f"<t:{int(datetime.fromisoformat(last_posted).timestamp())}:R>",
                inline=False
            )
        
        embed.set_footer(text="Use /solar_set_channel and /solar_enable to configure")
        
        await ctx.send(embed=embed)
    
    @commands.hybrid_command(name='xray', description='Show GOES Solar X-Ray Flux chart')
    async def xray(self, ctx: commands.Context, period: str = '6h'):
        """
        Display GOES Solar X-Ray Flux chart with various time periods.
        Shows solar flare activity and X-ray flux levels.
        
        Usage:
            !xray           - Shows 6-hour chart (default)
            !xray 6h        - 6-hour history
            !xray 1d        - 1-day history
            !xray 3d        - 3-day history
            !xray 7d        - 7-day history
            /xray period:6h
        """
        await ctx.defer()
        
        # Validate period
        valid_periods = ['6h', '1d', '3d', '7d']
        period_lower = period.lower()
        if period_lower not in valid_periods:
            await ctx.send(f"❌ Invalid period. Use: `6h`, `1d`, `3d`, or `7d`\nExample: `!xray 1d`")
            return
        
        # Use shared X-ray flux embed function
        from utils.solar_embed import create_xray_flux_embed
        
        embed, file = await create_xray_flux_embed(period_lower)
        if file:
            await ctx.send(embed=embed, file=file)
        else:
            await ctx.send(embed=embed)
    
    @commands.hybrid_command(name='drap', description='Show D-Region Absorption Prediction map for HF propagation')
    async def drap(self, ctx: commands.Context):
        """
        Display the D-Region Absorption Prediction (D-RAP) map.
        Shows real-time HF radio wave absorption due to solar X-ray flux.
        
        Updated every 15 minutes by NOAA Space Weather Prediction Center.
        
        Usage:
            !drap
            /drap
        """
        await ctx.defer()
        
        embed = discord.Embed(
            title="📡 D-Region Absorption Prediction (D-RAP)",
            description=(
                "Real-time HF absorption map showing ionospheric D-layer effects.\n\n"
                "**How to Read:**\n"
                "🔴 **Red/Orange**: High absorption (5+ dB) - HF signals significantly weakened\n"
                "🟡 **Yellow**: Moderate absorption (2-5 dB) - Some signal degradation\n"
                "🟢 **Green/Blue**: Low absorption (<2 dB) - Good propagation\n\n"
                "**What This Means:**\n"
                "• High absorption = HF bands (especially higher frequencies) won't work well\n"
                "• Caused by solar X-ray flares energizing D-layer\n"
                "• Most absorption on dayside of Earth\n"
                "• Lower bands (40m/80m) affected more than higher bands"
            ),
            color=0xFF6B35,
            timestamp=datetime.utcnow()
        )
        
        # Main D-RAP global map
        embed.set_image(url="https://services.swpc.noaa.gov/images/animations/d-rap/global/d-rap/latest.png")
        
        embed.add_field(
            name="📊 Update Frequency",
            value="Every 15 minutes",
            inline=True
        )
        
        embed.add_field(
            name="🌍 Coverage",
            value="Global HF absorption",
            inline=True
        )
        
        embed.add_field(
            name="💡 Tip",
            value="Red areas = try lower bands (40m/80m). Use !solar for detailed band predictions.",
            inline=False
        )
        
        embed.set_footer(text="Data: NOAA SWPC • Use !aurora for VHF conditions • !radio_maps for more")
        
        await ctx.send(embed=embed)
    
    @commands.hybrid_command(name='aurora', description='Show current auroral oval and forecast')
    async def aurora(self, ctx: commands.Context):
        """
        Display current auroral oval position and 30-minute forecast.
        Useful for VHF/UHF aurora scatter propagation.
        
        Usage:
            !aurora
            /aurora
        """
        await ctx.defer()
        
        embed = discord.Embed(
            title="🌌 Aurora Oval - Current Conditions",
            description=(
                "Real-time auroral oval position and 30-minute forecast.\n\n"
                "**For Radio Operators:**\n"
                "🟢 **Green Aurora**: VHF/UHF aurora scatter possible (2m/70cm)\n"
                "📡 **Point north** for best aurora contacts\n"
                "📻 **Use SSB or CW** - aurora distorts FM signals\n"
                "⚡ **Check !solar** for geomagnetic K-index (K≥4 = good aurora)\n\n"
                "**How to Read:**\n"
                "• Bright green/red = Strong aurora activity\n"
                "• Oval extends south during storms (G3+ events)\n"
                "• Aurora moves with geomagnetic field lines"
            ),
            color=0x00FF7F,
            timestamp=datetime.utcnow()
        )
        
        # Current auroral oval (Northern hemisphere)
        embed.set_image(url="https://services.swpc.noaa.gov/images/animations/ovation/north/latest.jpg")
        
        # Thumbnail: current aurora position
        embed.set_thumbnail(url="https://services.swpc.noaa.gov/images/aurora_n_pole_current.jpg")
        
        embed.add_field(
            name="🕐 Forecast",
            value="30-minute prediction",
            inline=True
        )
        
        embed.add_field(
            name="📊 Update Frequency",
            value="Every 5 minutes",
            inline=True
        )
        
        embed.add_field(
            name="💡 Radio Tip",
            value="Strong aurora = try 2m/6m SSB pointed north. Listen for distorted signals!",
            inline=False
        )
        
        embed.set_footer(text="Data: NOAA SWPC • Use !solar for full space weather report")
        
        await ctx.send(embed=embed)
    
    @commands.hybrid_command(name='radio_maps', description='Show comprehensive radio propagation maps')
    async def radio_maps(self, ctx: commands.Context):
        """
        Display multiple radio propagation maps in sequence:
        - D-RAP absorption map
        - Aurora forecast
        - Solar X-ray flux
        
        Usage:
            !radio_maps
            /radio_maps
        """
        await ctx.defer()
        
        # Use shared propagation map functions
        from utils.solar_embed import create_propagation_maps, create_xray_flux_embed
        
        # Get D-RAP and Aurora maps
        map_embeds = await create_propagation_maps()
        
        # Update titles and footers for radio_maps context
        if len(map_embeds) >= 1:
            map_embeds[0].title = "📡 Radio Propagation Maps - D-Region Absorption"
            map_embeds[0].set_footer(text="1/3 • NOAA SWPC • Updated every 15 min")
        
        if len(map_embeds) >= 2:
            map_embeds[1].title = "📡 Radio Propagation Maps - Aurora Forecast"
            map_embeds[1].set_footer(text="2/3 • NOAA SWPC • Updated every 5 min")
        
        # Get X-ray flux embed with chart
        xray_embed, xray_file = await create_xray_flux_embed('6h')
        xray_embed.title = "📡 Radio Propagation Maps - Solar X-Ray Flux"
        xray_embed.set_footer(text="3/3 • NOAA GOES Satellite • Real-time data")
        
        # Send all three embeds
        for embed in map_embeds:
            await ctx.send(embed=embed)
        if xray_file:
            await ctx.send(embed=xray_embed, file=xray_file)
        else:
            await ctx.send(embed=xray_embed)
        
        # Summary message
        summary = discord.Embed(
            title="📊 How to Use These Maps",
            description=(
                "**D-RAP Map**: Plan HF operations\n"
                "• Red areas = HF difficult, try 40m/80m\n"
                "• Green areas = HF excellent\n\n"
                "**Aurora Map**: Plan VHF scatter\n"
                "• Green oval = Point 2m/6m north\n"
                "• Use during K≥4 geomagnetic activity\n\n"
                "**X-Ray Flux**: Understand sudden changes\n"
                "• M/X flares = Expect HF blackouts\n"
                "• Rising flux = Conditions degrading\n\n"
                "💡 **Combine with !solar for complete picture**"
            ),
            color=0x1E88E5
        )
        summary.set_footer(text="Use !drap, !aurora, or !xray for individual charts • !solar for text report")
        
        await ctx.send(embed=summary)
    
    @commands.hybrid_command(name='contests', description='Show upcoming amateur radio contests')
    async def contests(self, ctx: commands.Context, days: int = 7):
        """
        Display upcoming amateur radio contests from various sources.
        
        Usage:
            !contests       - Show contests for next 7 days
            !contests 14    - Show contests for next 14 days
            !contests 30    - Show contests for next 30 days
        """
        await ctx.defer()
        
        try:
            # Fetch from WA7BNM Contest Calendar (JSON API)
            url = "https://www.contestcalendar.com/weeklycont.php"
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=10) as resp:
                    if resp.status != 200:
                        await ctx.send("❌ Unable to fetch contest calendar. Please try again later.")
                        return
                    
                    html = await resp.text()
            
            # Parse the HTML to extract contests (simple parsing)
            # Note: This is a basic implementation. For production, consider using BeautifulSoup
            import re
            from datetime import datetime, timedelta, timezone
            
            contests = []
            current_date = datetime.now(timezone.utc)
            end_date = current_date + timedelta(days=min(days, 30))
            
            # Extract contest information from HTML
            # Looking for patterns like: date, contest name, mode
            contest_pattern = re.compile(
                r'(\d{1,2}\s+\w+)\s+\d{4}\s+\d{4}Z\s+([^<]+?)\s+(CW|SSB|RTTY|Digital|Mixed|VHF|FM)',
                re.IGNORECASE
            )
            
            matches = contest_pattern.findall(html)
            
            for match in matches[:15]:  # Limit to 15 contests
                date_str, name, mode = match
                contests.append({
                    'date': date_str.strip(),
                    'name': name.strip(),
                    'mode': mode.upper()
                })
            
            if not contests:
                # Fallback: provide static list of common contests
                contests = [
                    {'date': 'Every Weekend', 'name': 'CQ WW DX Contest', 'mode': 'CW/SSB'},
                    {'date': 'Monthly', 'name': 'ARRL DX Contest', 'mode': 'Mixed'},
                    {'date': 'Check Calendar', 'name': 'Various Regional Contests', 'mode': 'All'},
                ]
            
            embed = discord.Embed(
                title="🏆 Upcoming Amateur Radio Contests",
                description=f"Contests in the next {days} days",
                color=0xF39C12,
                timestamp=datetime.now(timezone.utc)
            )
            
            # Group by mode
            cw_contests = [c for c in contests if 'CW' in c['mode']]
            ssb_contests = [c for c in contests if 'SSB' in c['mode'] or 'Phone' in c['mode']]
            digital_contests = [c for c in contests if 'RTTY' in c['mode'] or 'Digital' in c['mode'] or 'FT' in c['mode']]
            vhf_contests = [c for c in contests if 'VHF' in c['mode'] or 'FM' in c['mode']]
            mixed_contests = [c for c in contests if 'Mixed' in c['mode'] or ('CW' not in c['mode'] and 'SSB' not in c['mode'] and 'RTTY' not in c['mode'] and 'VHF' not in c['mode'])]
            
            if cw_contests:
                cw_list = '\n'.join([f"**{c['date']}** - {c['name']}" for c in cw_contests[:3]])
                embed.add_field(name="📻 CW Contests", value=cw_list, inline=False)
            
            if ssb_contests:
                ssb_list = '\n'.join([f"**{c['date']}** - {c['name']}" for c in ssb_contests[:3]])
                embed.add_field(name="🎤 SSB/Phone Contests", value=ssb_list, inline=False)
            
            if digital_contests:
                digital_list = '\n'.join([f"**{c['date']}** - {c['name']}" for c in digital_contests[:3]])
                embed.add_field(name="💻 Digital Contests", value=digital_list, inline=False)
            
            if vhf_contests:
                vhf_list = '\n'.join([f"**{c['date']}** - {c['name']}" for c in vhf_contests[:3]])
                embed.add_field(name="📡 VHF/UHF Contests", value=vhf_list, inline=False)
            
            if mixed_contests:
                mixed_list = '\n'.join([f"**{c['date']}** - {c['name']}" for c in mixed_contests[:3]])
                embed.add_field(name="🎯 All-Mode Contests", value=mixed_list or "None scheduled", inline=False)
            
            embed.add_field(
                name="📅 Contest Resources",
                value=(
                    "[WA7BNM Contest Calendar](https://www.contestcalendar.com/)\n"
                    "[CQ Magazine Contests](https://www.cq-amateur-radio.com/)\n"
                    "[ARRL Contest Calendar](https://www.arrl.org/contest-calendar)\n"
                    "[SM3CER Contest Service](https://www.sk3bg.se/contest/)"
                ),
                inline=False
            )
            
            embed.set_footer(text="73 and Good DX! • Use !contests 14 for 2-week view")
            
            await ctx.send(embed=embed)
            
        except Exception as e:
            logger.error(f"Error fetching contests: {e}", exc_info=True)
            
            # Fallback embed with useful contest info
            embed = discord.Embed(
                title="🏆 Amateur Radio Contest Information",
                description="Unable to fetch live contest calendar. Here are major contests:",
                color=0xF39C12
            )
            
            embed.add_field(
                name="🌍 Major DX Contests",
                value=(
                    "**CQ WW DX** - Last full weekend Oct (CW) & Nov (SSB)\n"
                    "**ARRL DX** - Feb (CW) & Mar (SSB)\n"
                    "**CQ WPX** - Last full weekend Mar (SSB) & May (CW)\n"
                    "**IARU HF Championship** - 2nd full weekend July"
                ),
                inline=False
            )
            
            embed.add_field(
                name="📻 Popular Contests",
                value=(
                    "**Sweepstakes** - Nov (ARRL SS)\n"
                    "**Field Day** - 4th full weekend June\n"
                    "**10-10 Int'l** - Fall/Winter\n"
                    "**NAQP** - Monthly (CW/SSB/RTTY)"
                ),
                inline=False
            )
            
            embed.add_field(
                name="📅 Contest Calendars",
                value=(
                    "[WA7BNM](https://www.contestcalendar.com/)\n"
                    "[ARRL](https://www.arrl.org/contest-calendar)"
                ),
                inline=False
            )
            
            await ctx.send(embed=embed)
    
    @commands.hybrid_command(name='grid', description='Convert coordinates to Maidenhead grid square or calculate distance between grids')
    async def grid(self, ctx: commands.Context, *, input_data: str = None):
        """
        Maidenhead grid square calculator and distance/bearing calculator.
        
        Usage:
            !grid 40.7128 -74.0060          - Convert lat/lon to grid square
            !grid FN20xr                    - Show grid square info
            !grid FN20xr EM79vx             - Distance and bearing between two grids
            !grid distance FN20xr to EM79vx - Alternative distance syntax
        """
        if not input_data:
            embed = discord.Embed(
                title="🗺️ Maidenhead Grid Square Calculator",
                description=(
                    "**Usage Examples:**\n"
                    "`!grid 40.7128 -74.0060` - Convert lat/lon to grid\n"
                    "`!grid FN20xr` - Show grid square details\n"
                    "`!grid FN20xr EM79vx` - Distance between grids\n"
                    "`!grid distance FN20xr to EM79vx` - Alternative syntax\n\n"
                    "**Grid Square Format:**\n"
                    "• 4 characters (e.g., FN20) - Field + Square (≈70x100 km)\n"
                    "• 6 characters (e.g., FN20xr) - Adds subsquare (≈3x5 km)\n"
                    "• 8 characters (e.g., FN20xr12) - Adds extended square (≈125x250m)\n\n"
                    "Used for VHF/UHF contesting, satellite work, and location reporting."
                ),
                color=0x3498DB
            )
            await ctx.send(embed=embed)
            return
        
        # Helper function to convert lat/lon to grid square
        def latlon_to_grid(lat, lon, precision=6):
            """Convert latitude/longitude to Maidenhead grid square."""
            lat += 90
            lon += 180
            
            grid = ""
            # Field (20° lon x 10° lat)
            grid += chr(int(lon / 20) + ord('A'))
            grid += chr(int(lat / 10) + ord('A'))
            
            # Square (2° lon x 1° lat)
            grid += str(int((lon % 20) / 2))
            grid += str(int(lat % 10))
            
            if precision >= 6:
                # Subsquare (5' lon x 2.5' lat)
                grid += chr(int(((lon % 2) * 12)) + ord('a'))
                grid += chr(int(((lat % 1) * 24)) + ord('a'))
            
            if precision >= 8:
                # Extended square (12.5" lon x 6.25" lat)
                grid += str(int(((lon % 2) * 120) % 10))
                grid += str(int(((lat % 1) * 240) % 10))
            
            return grid.upper() if precision == 4 else grid
        
        # Helper function to convert grid square to lat/lon (center)
        def grid_to_latlon(grid):
            """Convert Maidenhead grid square to center lat/lon."""
            grid = grid.upper()
            lon = (ord(grid[0]) - ord('A')) * 20 - 180
            lat = (ord(grid[1]) - ord('A')) * 10 - 90
            
            if len(grid) >= 4:
                lon += int(grid[2]) * 2
                lat += int(grid[3])
            
            if len(grid) >= 6:
                lon += (ord(grid[4].upper()) - ord('A')) / 12
                lat += (ord(grid[5].upper()) - ord('A')) / 24
            
            if len(grid) >= 8:
                lon += int(grid[6]) / 120
                lat += int(grid[7]) / 240
            
            # Return center of grid square
            if len(grid) == 4:
                lon += 1  # Center of 2° square
                lat += 0.5  # Center of 1° square
            elif len(grid) == 6:
                lon += 1/12  # Center of subsquare
                lat += 1/24
            elif len(grid) == 8:
                lon += 1/120  # Center of extended square
                lat += 1/240
            
            return lat, lon
        
        # Helper function to calculate distance and bearing
        def calculate_distance_bearing(lat1, lon1, lat2, lon2):
            """Calculate great circle distance and bearing between two points."""
            from math import radians, cos, sin, asin, sqrt, atan2, degrees
            
            # Convert to radians
            lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
            
            # Haversine formula
            dlat = lat2 - lat1
            dlon = lon2 - lon1
            a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
            c = 2 * asin(sqrt(a))
            
            # Earth radius in km and miles
            km = 6371 * c
            miles = km * 0.621371
            
            # Calculate bearing
            y = sin(dlon) * cos(lat2)
            x = cos(lat1) * sin(lat2) - sin(lat1) * cos(lat2) * cos(dlon)
            bearing = degrees(atan2(y, x))
            bearing = (bearing + 360) % 360
            
            return km, miles, bearing
        
        # Parse input
        input_clean = input_data.replace(',', ' ').replace('distance', '').replace('to', ' ').strip()
        parts = input_clean.split()
        
        # Check if it's lat/lon conversion
        if len(parts) == 2:
            try:
                lat = float(parts[0])
                lon = float(parts[1])
                
                if -90 <= lat <= 90 and -180 <= lon <= 180:
                    grid_4 = latlon_to_grid(lat, lon, precision=4)
                    grid_6 = latlon_to_grid(lat, lon, precision=6)
                    grid_8 = latlon_to_grid(lat, lon, precision=8)
                    
                    embed = discord.Embed(
                        title="🗺️ Coordinate to Grid Square",
                        description=f"**Coordinates:** {lat:.4f}°, {lon:.4f}°",
                        color=0x2ECC71
                    )
                    embed.add_field(name="Grid Square (4-char)", value=f"`{grid_4}`", inline=True)
                    embed.add_field(name="Grid Square (6-char)", value=f"`{grid_6}`", inline=True)
                    embed.add_field(name="Grid Square (8-char)", value=f"`{grid_8}`", inline=True)
                    embed.add_field(
                        name="📍 Usage",
                        value=f"Use `{grid_6}` for VHF/UHF logging\nUse `{grid_4}` for HF/general reference",
                        inline=False
                    )
                    embed.set_footer(text=f"Center of {grid_6} grid square")
                    await ctx.send(embed=embed)
                    return
            except ValueError:
                pass
        
        # Check if it's a single grid square lookup
        if len(parts) == 1 and len(parts[0]) in [4, 6, 8]:
            grid = parts[0].upper()
            try:
                lat, lon = grid_to_latlon(grid)
                
                embed = discord.Embed(
                    title=f"🗺️ Grid Square: {grid}",
                    description=f"**Center Coordinates:** {lat:.4f}°, {lon:.4f}°",
                    color=0x3498DB
                )
                
                # Calculate grid square size
                if len(grid) == 4:
                    size = "~70 × 100 km (Field + Square)"
                elif len(grid) == 6:
                    size = "~3 × 5 km (Subsquare)"
                else:
                    size = "~125 × 250 m (Extended square)"
                
                embed.add_field(name="Grid Square Size", value=size, inline=False)
                embed.add_field(
                    name="📍 Common Uses",
                    value="• VHF/UHF contest exchanges\n• Satellite QSO reporting\n• Location privacy (approximate location)",
                    inline=False
                )
                embed.set_footer(text="Use !grid <grid1> <grid2> to calculate distance between grids")
                await ctx.send(embed=embed)
                return
            except Exception as e:
                await ctx.send(f"❌ Invalid grid square format: {grid}")
                return
        
        # Check if it's distance calculation between two grids
        if len(parts) == 2 and all(len(p) in [4, 6, 8] for p in parts):
            grid1, grid2 = parts[0].upper(), parts[1].upper()
            
            try:
                lat1, lon1 = grid_to_latlon(grid1)
                lat2, lon2 = grid_to_latlon(grid2)
                
                km, miles, bearing = calculate_distance_bearing(lat1, lon1, lat2, lon2)
                
                # Compass direction
                compass = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", 
                          "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
                compass_dir = compass[int((bearing + 11.25) / 22.5) % 16]
                
                embed = discord.Embed(
                    title="📏 Grid Square Distance Calculator",
                    description=f"**From:** {grid1} → **To:** {grid2}",
                    color=0xE74C3C
                )
                embed.add_field(name="Distance", value=f"**{km:.1f} km** ({miles:.1f} mi)", inline=False)
                embed.add_field(name="Bearing", value=f"**{bearing:.1f}°** ({compass_dir})", inline=False)
                embed.add_field(
                    name="📡 Propagation Notes",
                    value=f"• Point antenna {compass_dir} ({bearing:.0f}°)\n"
                          f"• Distance class: {'Local' if km < 50 else 'Regional' if km < 500 else 'Long-haul'}\n"
                          f"• Good for: {'2m/70cm' if km < 300 else '6m/2m with Es' if km < 1500 else 'HF skywave'}",
                    inline=False
                )
                embed.set_footer(text=f"Grid centers: {lat1:.2f},{lon1:.2f} to {lat2:.2f},{lon2:.2f}")
                await ctx.send(embed=embed)
                return
            except Exception as e:
                await ctx.send(f"❌ Error calculating distance: {str(e)}")
                return
        
        # If we got here, invalid format
        await ctx.send("❌ Invalid format. Use `!grid` with no arguments for help.")
    
    @commands.hybrid_command(name='satellite', description='Show amateur radio satellite pass predictions')
    async def satellite(self, ctx: commands.Context, grid: str = None):
        """
        Display information about amateur radio satellites and pass predictions.
        
        Usage:
            !satellite              - List active FM and SSB satellites
            !satellite FN20xr       - Get pass predictions for your grid (coming soon)
            !satellite ISS          - Get ISS pass info (coming soon)
        """
        embed = discord.Embed(
            title="🛰️ Amateur Radio Satellites",
            description="Currently active amateur radio satellites for voice and digital",
            color=0x9B59B6,
            timestamp=datetime.now(timezone.utc)
        )
        
        # FM Voice Satellites
        embed.add_field(
            name="📻 FM Voice Satellites (Easy Start)",
            value=(
                "**SO-50** (SaudiSat 1C)\n"
                "• Uplink: 145.850 MHz (67.0 Hz PL)\n"
                "• Downlink: 436.795 MHz\n"
                "• Status: Active, popular for beginners\n\n"
                
                "**ISS** (International Space Station)\n"
                "• Uplink: 145.990 MHz\n"
                "• Downlink: 145.800 MHz\n"
                "• Status: Active when crew operates (check schedule)\n"
                "• Also: APRS digipeater on 145.825 MHz\n\n"
                
                "**PO-101** (Diwata-2B)\n"
                "• Uplink: 145.900 MHz (141.3 Hz PL)\n"
                "• Downlink: 437.500 MHz\n"
                "• Status: Active, FM voice transponder"
            ),
            inline=False
        )
        
        # Linear Transponder Satellites
        embed.add_field(
            name="📡 Linear Transponder Satellites (SSB/CW)",
            value=(
                "**AO-91** (Fox-1B)\n"
                "• Uplink: 435.250 MHz (67.0 Hz)\n"
                "• Downlink: 145.960 MHz\n"
                "• Mode: FM voice transponder\n\n"
                
                "**AO-92** (Fox-1D)\n"
                "• Uplink: 435.350 MHz (67.0 Hz)\n"
                "• Downlink: 145.880 MHz\n"
                "• Mode: FM voice, L-band uplink\n\n"
                
                "**XW-2 Series** (CAS-3 constellation)\n"
                "• Multiple satellites in constellation\n"
                "• Various linear transponders\n"
                "• Check current status before attempting"
            ),
            inline=False
        )
        
        # Digital Satellites
        embed.add_field(
            name="💻 Digital/Packet Satellites",
            value=(
                "**ISS APRS** - 145.825 MHz digipeater\n"
                "**PSAT** - Naval Academy satellite\n"
                "**Various CubeSats** - Check AMSAT status page"
            ),
            inline=False
        )
        
        # Operating Tips
        embed.add_field(
            name="🎯 Operating Tips",
            value=(
                "• Use **full-duplex** operation (hear yourself on downlink)\n"
                "• Start with **FM satellites** (easier than SSB)\n"
                "• **Doppler shift**: Compensate ~3 kHz on VHF, ~10 kHz on UHF\n"
                "• **Handheld setup**: 5W HT + Arrow antenna works!\n"
                "• **Pass duration**: Typically 5-15 minutes\n"
                "• **Best passes**: Higher elevation = better signal\n"
                "• **Keep it short**: Many ops, limited time!"
            ),
            inline=False
        )
        
        # Resources
        embed.add_field(
            name="📅 Pass Prediction Resources",
            value=(
                "[AMSAT Live Pass Predictions](https://www.amsat.org/track/)\n"
                "[Heavens-Above](https://www.heavens-above.com/) - Free pass predictions\n"
                "[N2YO Satellite Tracking](https://www.n2yo.com/) - Real-time tracking\n"
                "[AMSAT Frequency Guide](https://www.amsat.org/ans/) - Latest status\n"
                "[Gpredict](http://gpredict.oz9aec.net/) - Free tracking software"
            ),
            inline=False
        )
        
        if grid:
            embed.add_field(
                name="🔮 Future Feature",
                value=f"Pass predictions for grid {grid.upper()} coming soon!\nFor now, use the resources above with your grid square.",
                inline=False
            )
        
        embed.set_footer(text="73 and good satellite DX! • Start with SO-50 or ISS for first contact")
        
        await ctx.send(embed=embed)
    
    @commands.hybrid_command(name='repeater', description='Find amateur radio repeaters by location')
    async def repeater(self, ctx: commands.Context, *, location: str = None):
        """
        Find amateur radio repeaters by ZIP code, city, or grid square.
        
        Usage:
            !repeater 12345          - Find repeaters near ZIP code
            !repeater Portland OR    - Find repeaters near city
            !repeater FN20xr         - Find repeaters near grid square (coming soon)
        """
        if not location:
            embed = discord.Embed(
                title="📻 Repeater Directory",
                description="Find amateur radio repeaters in your area",
                color=0x16A085
            )
            
            embed.add_field(
                name="🔍 How to Search",
                value=(
                    "`!repeater 12345` - Search by ZIP code\n"
                    "`!repeater Portland OR` - Search by city\n"
                    "`!repeater FN20xr` - Search by grid square"
                ),
                inline=False
            )
            
            embed.add_field(
                name="📡 What You'll Find",
                value=(
                    "• **Output frequency** - Where to listen\n"
                    "• **Input offset** - Where to transmit (+/-)\n"
                    "• **CTCSS/PL tone** - Required access tone\n"
                    "• **Location** - Repeater site\n"
                    "• **Notes** - Coverage, linked systems, etc."
                ),
                inline=False
            )
            
            embed.add_field(
                name="🌐 Repeater Databases",
                value=(
                    "[RepeaterBook](https://www.repeaterbook.com/) - Largest worldwide database\n"
                    "[ARRL Repeater Directory](https://www.arrl.org/repeater-directory) - ARRL members\n"
                    "[RadioReference](https://www.radioreference.com/) - Comprehensive database\n"
                    "[RFinder](https://www.rfinder.net/) - Mobile app with offline maps"
                ),
                inline=False
            )
            
            embed.add_field(
                name="💡 Repeater Etiquette",
                value=(
                    "• **Listen first** - Don't interrupt ongoing QSOs\n"
                    "• **ID properly** - Say your callsign at start/end\n"
                    "• **Pause between transmissions** - Let others in\n"
                    "• **Keep it brief** - Others may need the repeater\n"
                    "• **Use correct tone** - Many require CTCSS/PL\n"
                    "• **Kerchunk = rude** - Don't key up without IDing"
                ),
                inline=False
            )
            
            await ctx.send(embed=embed)
            return
        
        # Try to determine search type
        location_clean = location.strip()
        
        # Check if it's a ZIP code (5 digits)
        if location_clean.isdigit() and len(location_clean) == 5:
            search_type = "ZIP code"
            search_url = f"https://www.repeaterbook.com/repeaters/downloads/app_direct.php?zip={location_clean}&distance=25"
        # Check if it's a grid square
        elif len(location_clean) in [4, 6] and location_clean[:2].isalpha() and location_clean[2:4].isdigit():
            search_type = "grid square"
            # Convert grid to approx coordinates
            grid_upper = location_clean.upper()
            # This would require grid-to-latlon conversion
            search_url = f"https://www.repeaterbook.com/repeaters/index.php?state_id=none"
        else:
            search_type = "city/state"
            search_url = f"https://www.repeaterbook.com/repeaters/index.php?state_id=none"
        
        embed = discord.Embed(
            title=f"📻 Repeaters Near: {location}",
            description=f"Searching by {search_type}...",
            color=0x27AE60
        )
        
        # Since we'd need to scrape RepeaterBook or use their API (which requires key),
        # provide links instead
        embed.add_field(
            name="🔍 Search Results",
            value=(
                f"[View on RepeaterBook](https://www.repeaterbook.com/repeaters/index.php?state_id=none)\n"
                f"[Search RadioReference](https://www.radioreference.com/apps/ham/)\n\n"
                "**Direct API access coming soon!**\n"
                "For now, use the links above to search repeaters in your area."
            ),
            inline=False
        )
        
        embed.add_field(
            name="📱 Mobile Apps",
            value=(
                "**RepeaterBook** - Free (iOS/Android)\n"
                "**RFinder** - $9.99, offline maps (iOS/Android)\n"
                "**EchoLink** - Free, internet linking (iOS/Android)\n"
                "**Repeater Finder** - Free alternative"
            ),
            inline=False
        )
        
        embed.add_field(
            name="🎤 Common Bands",
            value=(
                "**2 meters (VHF)** - 144-148 MHz\n"
                "• Most popular, best range\n"
                "• Typical offset: +/- 600 kHz\n\n"
                "**70 cm (UHF)** - 420-450 MHz\n"
                "• More repeaters in cities\n"
                "• Typical offset: +/- 5 MHz\n\n"
                "**6 meters** - 50-54 MHz\n"
                "• Less common, great for DX"
            ),
            inline=False
        )
        
        embed.set_footer(text=f"Search location: {location} • Full API integration coming soon!")
        
        await ctx.send(embed=embed)


async def setup(bot):
    """Load the Radiohead cog."""
    await bot.add_cog(Radiohead(bot))
    logger.info("Radiohead cog loaded")
