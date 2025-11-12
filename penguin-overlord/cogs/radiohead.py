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
from datetime import datetime
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
            !frequency lora            - LoRa frequencies
            !frequency wifi            - Wi-Fi band info
            !frequency bluetooth       - Bluetooth frequencies
            !frequency gmrs            - GMRS info
            
        Supported services: lora, wifi, bluetooth, zigbee, ism, frs, gmrs, murs, cb, aprs, rfid
        
        Use /bandplan for full ARRL band plan
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
            if not self.session:
                self.session = aiohttp.ClientSession()
            
            # Fetch NOAA scales (R, S, G scales)
            async with self.session.get('https://services.swpc.noaa.gov/products/noaa-scales.json', timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    
                    # Extract current conditions from "0" key (current time)
                    r_scale = 'N/A'
                    s_scale = 'N/A'
                    g_scale = 'N/A'
                    
                    if isinstance(data, dict) and '0' in data:
                        current = data['0']
                        r_scale = current.get('R', {}).get('Scale', 'N/A')
                        s_scale = current.get('S', {}).get('Scale', 'N/A')
                        g_scale = current.get('G', {}).get('Scale', 'N/A')
                    
                    # Fetch solar flux from JSON endpoint
                    sfi = 'N/A'
                    async with self.session.get('https://services.swpc.noaa.gov/json/f107_cm_flux.json', timeout=10) as flux_resp:
                        if flux_resp.status == 200:
                            flux_data = await flux_resp.json()
                            # Get the most recent entry with reporting_schedule="Noon" (official value)
                            if flux_data:
                                for entry in reversed(flux_data):
                                    if entry.get('reporting_schedule') == 'Noon':
                                        sfi = str(int(entry.get('flux', 0)))
                                        break
                                # If no Noon value, just take the latest
                                if sfi == 'N/A' and flux_data:
                                    sfi = str(int(flux_data[-1].get('flux', 0)))
                    
                    # Fetch K-index from JSON endpoint
                    k_index = 'N/A'
                    async with self.session.get('https://services.swpc.noaa.gov/json/planetary_k_index_1m.json', timeout=10) as k_resp:
                        if k_resp.status == 200:
                            k_data = await k_resp.json()
                            # Get the most recent K-index
                            if k_data:
                                k_index = str(k_data[-1].get('kp_index', 'N/A'))
                    
                    # Calculate A-index from K-index (approximation: K to A conversion)
                    # Typical conversion: A ≈ (K^2) * 3.3
                    a_index = 'N/A'
                    if k_index != 'N/A':
                        try:
                            k_val = int(k_index)
                            a_val = int((k_val ** 2) * 3.3)
                            a_index = str(a_val)
                        except:
                            pass
                    
                    # Parse SFI for propagation calculations
                    try:
                        sfi_value = int(sfi) if sfi != 'N/A' else 100
                    except:
                        sfi_value = 100
                    
                    # Parse K-index for geomagnetic impact
                    try:
                        k_value = float(k_index) if k_index != 'N/A' else 2.0
                    except:
                        k_value = 2.0
                    
                    # Get current UTC hour for time-of-day effects
                    utc_hour = datetime.utcnow().hour
                    
                    # Calculate propagation parameters using physics-based models
                    fof2 = estimate_fof2_from_sfi(sfi_value)
                    
                    # Calculate MUF for typical DX distance (3000km)
                    muf_dx = calculate_muf_for_distance(fof2, 3000)
                    
                    # Calculate MUF for regional distance (1000km)
                    muf_regional = calculate_muf_for_distance(fof2, 1000)
                    
                    # Calculate D-layer absorption
                    d_absorption = calculate_d_layer_absorption(utc_hour, r_scale, sfi_value)
                    
                    # Check for gray line enhancement
                    is_gray_line, gray_line_msg = calculate_gray_line_enhancement(utc_hour)
                    
                    # Determine overall conditions based on all factors
                    conditions_good = (
                        (r_scale in ['R0', 'N/A'] or r_scale == 'R0') and
                        (g_scale in ['G0', 'N/A', 'G1'] or g_scale in ['G0', 'G1']) and
                        d_absorption < 0.5 and
                        k_value < 4
                    )
                    
                    # Create main embed
                    embed = discord.Embed(
                        title="☀️ Solar Weather Report",
                        description=f"Comprehensive propagation forecast • {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC",
                        color=0xFF9800 if conditions_good else 0xF44336
                    )
                    
                    # Current Indices and Propagation Parameters
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
                    
                    # NOAA Scales - convert to int for comparison
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
                    
                    # Band-by-band predictions using physics-based model
                    hf_predictions = []
                    
                    # Get current month for seasonal adjustments
                    current_month = datetime.utcnow().month
                    
                    # Define bands with frequencies and typical usage
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
                        # Calculate K-index impact for this band
                        k_impact = get_k_index_impact(k_value, freq_mhz)
                        
                        # Get band conditions prediction with seasonal awareness
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
                            # Check month for Sporadic-E prediction
                            month = datetime.utcnow().month
                            if 5 <= month <= 8:
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
                    
                    # VHF/UHF predictions - these are mostly line-of-sight
                    vhf_predictions = []
                    
                    # 2m (144 MHz) - check for aurora
                    g_val = int(g_scale.replace('G', '')) if g_scale not in ['N/A', 'G0'] and g_scale.replace('G', '').isdigit() else 0
                    if g_val >= 3:
                        vhf_predictions.append("**2m:** 🟢 Aurora possible! Try north, use SSB/CW")
                    elif g_val >= 1:
                        vhf_predictions.append("**2m:** 🟡 Minor aurora possible, watch for activity")
                    else:
                        vhf_predictions.append("**2m:** 🟡 Normal - Line of sight, tropospheric scatter")
                    
                    # 70cm (440 MHz)
                    vhf_predictions.append("**70cm:** 🟡 Normal - Line of sight, repeaters, satellites")
                    
                    embed.add_field(
                        name="📡 VHF/UHF Conditions",
                        value="\n".join(vhf_predictions),
                        inline=False
                    )
                    
                    # ISM/WiFi band effects - only show during R2+ radio blackouts
                    r_val = int(r_scale.replace('R', '')) if r_scale not in ['R0', 'N/A'] and r_scale.replace('R', '').isdigit() else 0
                    if r_val >= 2:
                        ism_effects = []
                        
                        if r_val >= 4:
                            # R4-R5: Severe/Extreme radio blackout
                            ism_effects.append("**900MHz (33cm/ISM):** 🔴 Likely interference - LoRa, Zigbee, ISM devices affected")
                            ism_effects.append("**2.4GHz (WiFi/BT):** 🔴 Likely disruption - WiFi, Bluetooth, Zigbee may degrade")
                            ism_effects.append("**5GHz WiFi:** 🟠 Possible minor impact - Monitor for issues")
                            ism_effects.append("**6GHz WiFi 6E:** 🟡 Minimal impact expected")
                        elif r_val >= 3:
                            # R3: Strong radio blackout
                            ism_effects.append("**900MHz (33cm/ISM):** 🟠 Possible interference - LoRa, Zigbee, ISM devices")
                            ism_effects.append("**2.4GHz (WiFi/BT):** 🟠 Possible disruption - WiFi, Bluetooth may be affected")
                            ism_effects.append("**5GHz WiFi:** 🟡 Minor impact possible")
                            ism_effects.append("**6GHz WiFi 6E:** 🟡 Minimal impact expected")
                        else:
                            # R2: Moderate radio blackout
                            ism_effects.append("**900MHz (33cm/ISM):** 🟡 Monitor for issues - LoRa, Zigbee, ISM devices")
                            ism_effects.append("**2.4GHz (WiFi/BT):** 🟡 Monitor for issues - WiFi, Bluetooth")
                            ism_effects.append("**5/6GHz WiFi:** 🟢 Minimal impact expected")
                        
                        # Add note about indirect effects
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
                    
                    # Operating recommendations based on physics
                    recommendations = []
                    
                    # D-layer absorption warnings
                    if d_absorption > 0.7:
                        recommendations.append("⚠️ **High D-Layer Absorption:** Lower frequencies heavily affected. Try 40m/80m.")
                    elif d_absorption > 0.4:
                        recommendations.append("⚠️ **Moderate Absorption:** Higher bands (20m+) may be challenging.")
                    
                    # Radio blackout warnings
                    r_val = int(r_scale.replace('R', '')) if r_scale not in ['R0', 'N/A'] and r_scale.replace('R', '').isdigit() else 0
                    if r_val >= 3:
                        recommendations.append("🚨 **Major Radio Blackout (R3+):** HF severely degraded. Try lower bands.")
                    elif r_val >= 1:
                        recommendations.append("⚠️ **Radio Blackout Active:** Expect absorption on higher frequencies.")
                    
                    # Geomagnetic storm recommendations
                    if g_val >= 4:
                        recommendations.append("🌈 **Major Geomagnetic Storm!** Aurora likely on 6m/2m. HF disturbed.")
                    elif g_val >= 3:
                        recommendations.append("🌈 **Aurora Possible!** Check 6m/2m for aurora propagation.")
                    elif g_val >= 1:
                        recommendations.append("💡 **Tip:** Lower bands (80m/40m) handle geomagnetic activity better.")
                    
                    # MUF-based recommendations
                    if muf_dx > 28:
                        recommendations.append("🎉 **Excellent MUF!** 10m should be open - check for magic band DX!")
                    elif muf_dx > 21:
                        recommendations.append("✨ **Great Conditions!** 15m and 20m excellent for DX hunting.")
                    elif muf_dx < 14:
                        recommendations.append("💡 **Low MUF:** Focus on 40m and 80m for reliable contacts.")
                    
                    # K-index recommendations
                    if k_value >= 5:
                        recommendations.append("⚡ **High K-Index:** Expect flutter and fading on higher bands.")
                    
                    # Overall assessment
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
                    
                    # Best bands right now based on absorption and MUF
                    best_bands = []
                    if d_absorption < 0.3:  # Low absorption - daytime can use higher bands
                        if muf_dx > 28:
                            best_bands = ["10m", "15m", "20m", "17m"]
                        elif muf_dx > 21:
                            best_bands = ["20m", "17m", "15m", "40m"]
                        elif muf_dx > 14:
                            best_bands = ["20m", "30m", "40m"]
                        else:
                            best_bands = ["40m", "30m", "80m"]
                    else:  # High absorption - nighttime or disturbed daytime
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
                    
                    embed.set_footer(text="73 de Penguin Overlord! • Data from NOAA SWPC • !solar for detailed info")
                    
                    await ctx.send(embed=embed)
                else:
                    await ctx.send("❌ Unable to fetch solar data from NOAA. Try again later!")
                    
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


async def setup(bot):
    """Load the Radiohead cog."""
    await bot.add_cog(Radiohead(bot))
    logger.info("Radiohead cog loaded")
