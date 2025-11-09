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
from discord.ext import commands
import aiohttp
from datetime import datetime

logger = logging.getLogger(__name__)


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


class Radiohead(commands.Cog):
    """HAM Radio bot - propagation, news, and frequency trivia."""
    
    def __init__(self, bot):
        self.bot = bot
        self.session = None
    
    async def cog_load(self):
        """Create aiohttp session when cog loads."""
        self.session = aiohttp.ClientSession()
    
    async def cog_unload(self):
        """Close aiohttp session when cog unloads."""
        if self.session:
            await self.session.close()
    
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
        
        embed.set_footer(text="73! • Use !hamradio for more • !propagation for current conditions")
        
        await ctx.send(embed=embed)
    
    @commands.hybrid_command(name='frequency', description='Get frequency band information')
    async def frequency(self, ctx: commands.Context):
        """
        Get information about HAM radio frequency bands.
        
        Usage:
            !frequency
            /frequency
        """
        freq_info = random.choice(FREQUENCY_TRIVIA)
        
        embed = discord.Embed(
            title=f"📡 Frequency Band: {freq_info['freq']}",
            description=freq_info['desc'],
            color=0x43A047
        )
        
        embed.add_field(name="Propagation", value=freq_info['propagation'], inline=False)
        
        embed.set_footer(text="73! • Use !frequency for more bands")
        
        await ctx.send(embed=embed)
    
    @commands.hybrid_command(name='propagation', description='Get current HF propagation conditions')
    async def propagation(self, ctx: commands.Context):
        """
        Get current HF propagation conditions from NOAA Space Weather.
        
        Usage:
            !propagation
            /propagation
        """
        await ctx.defer()
        
        try:
            # Fetch space weather data from NOAA
            async with self.session.get('https://services.swpc.noaa.gov/products/noaa-scales.json') as resp:
                if resp.status == 200:
                    data = await resp.json()
                    
                    # Get current conditions
                    current = data.get('0', {}) if isinstance(data, dict) else data[0] if data else {}
                    
                    embed = discord.Embed(
                        title="📡 Current HF Propagation Conditions",
                        description="Live data from NOAA Space Weather Prediction Center",
                        color=0x1E88E5,
                        timestamp=datetime.utcnow()
                    )
                    
                    # Space weather scales
                    r_scale = current.get('R', {}).get('Scale', 'N/A')
                    s_scale = current.get('S', {}).get('Scale', 'N/A')
                    g_scale = current.get('G', {}).get('Scale', 'N/A')
                    
                    embed.add_field(
                        name="🌟 Radio Blackout (R-Scale)",
                        value=f"Current: R{r_scale}\nR0=None, R5=Extreme",
                        inline=True
                    )
                    
                    embed.add_field(
                        name="☀️ Solar Radiation Storm (S-Scale)",
                        value=f"Current: S{s_scale}\nS0=None, S5=Extreme",
                        inline=True
                    )
                    
                    embed.add_field(
                        name="🧲 Geomagnetic Storm (G-Scale)",
                        value=f"Current: G{g_scale}\nG0=None, G5=Extreme",
                        inline=True
                    )
                    
                    # Interpretation
                    interpretation = []
                    if r_scale == 'R0' or r_scale == 'N/A':
                        interpretation.append("✅ No radio blackouts - HF bands open!")
                    else:
                        interpretation.append(f"⚠️ R{r_scale} blackout - HF may be degraded")
                    
                    if g_scale == 'G0' or g_scale == 'N/A':
                        interpretation.append("✅ Geomagnetic field calm")
                    elif int(g_scale.replace('G', '')) >= 3:
                        interpretation.append(f"🌈 G{g_scale} storm - possible aurora!")
                    else:
                        interpretation.append(f"⚠️ G{g_scale} storm - degraded propagation")
                    
                    embed.add_field(
                        name="📊 Interpretation",
                        value="\n".join(interpretation),
                        inline=False
                    )
                    
                    embed.add_field(
                        name="💡 Quick Tips",
                        value="• Lower bands (80m/40m) work better during storms\n"
                              "• Higher bands (20m/15m/10m) need calm conditions\n"
                              "• Check !hamradio for more propagation tips",
                        inline=False
                    )
                    
                    embed.set_footer(text="73! • Data from NOAA SWPC • Updates every 15 minutes")
                    
                    await ctx.send(embed=embed)
                else:
                    await ctx.send("❌ Unable to fetch propagation data from NOAA. Try again later!")
                    
        except Exception as e:
            logger.error(f"Error fetching propagation data: {e}")
            
            # Fallback to general advice
            embed = discord.Embed(
                title="📡 HF Propagation Tips",
                description="Unable to fetch live data, here's general propagation advice:",
                color=0x1E88E5
            )
            
            embed.add_field(
                name="Day Bands",
                value="20m, 17m, 15m, 12m, 10m\nBest for DX during daylight",
                inline=True
            )
            
            embed.add_field(
                name="Night Bands",
                value="80m, 40m, 30m\nBest for regional to DX at night",
                inline=True
            )
            
            embed.add_field(
                name="All-Around",
                value="40m works day and night!\nMost reliable band.",
                inline=True
            )
            
            embed.set_footer(text="73! • Try !hamradio for more tips")
            
            await ctx.send(embed=embed)
    
    @commands.hybrid_command(name='solar', description='Get detailed solar weather report and band predictions')
    async def solar(self, ctx: commands.Context):
        """
        Get comprehensive solar weather report with band-by-band propagation predictions.
        Fetches live data from NOAA Space Weather Prediction Center.
        
        Usage:
            !solar
            /solar
        """
        try:
            if not self.session:
                self.session = aiohttp.ClientSession()
            
            async with self.session.get('https://services.swpc.noaa.gov/products/noaa-scales.json', timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    
                    # Extract current conditions
                    r_scale = 'N/A'
                    s_scale = 'N/A'
                    g_scale = 'N/A'
                    
                    if isinstance(data, dict):
                        r_scale = data.get('R', {}).get('Scale', 'N/A')
                        s_scale = data.get('S', {}).get('Scale', 'N/A')
                        g_scale = data.get('G', {}).get('Scale', 'N/A')
                    
                    # Now fetch solar flux and other indices
                    async with self.session.get('https://services.swpc.noaa.gov/text/wwv.txt', timeout=10) as wwv_resp:
                        sfi = 'N/A'
                        a_index = 'N/A'
                        k_index = 'N/A'
                        
                        if wwv_resp.status == 200:
                            wwv_text = await wwv_resp.text()
                            # Parse WWV text format
                            for line in wwv_text.split('\n'):
                                if 'Solar flux' in line:
                                    parts = line.split()
                                    for i, part in enumerate(parts):
                                        if part == 'flux' and i + 1 < len(parts):
                                            sfi = parts[i + 1]
                                elif 'A' in line and 'index' in line.lower():
                                    parts = line.split()
                                    for i, part in enumerate(parts):
                                        if part.upper() == 'A' and i + 1 < len(parts):
                                            a_index = parts[i + 1]
                                elif 'K' in line and 'index' in line.lower():
                                    parts = line.split()
                                    for i, part in enumerate(parts):
                                        if part.upper() == 'K' and i + 1 < len(parts):
                                            k_index = parts[i + 1]
                    
                    # Determine overall conditions based on all factors
                    conditions_good = (
                        (r_scale in ['R0', 'N/A'] or r_scale == 'R0') and
                        (g_scale in ['G0', 'N/A', 'G1'] or g_scale in ['G0', 'G1'])
                    )
                    
                    # Try to parse SFI for band predictions
                    try:
                        sfi_value = int(sfi) if sfi != 'N/A' else 100
                    except:
                        sfi_value = 100
                    
                    # Create main embed
                    embed = discord.Embed(
                        title="☀️ Solar Weather Report",
                        description=f"Comprehensive propagation forecast • {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC",
                        color=0xFF9800 if conditions_good else 0xF44336
                    )
                    
                    # Current Indices
                    embed.add_field(
                        name="📊 Solar Indices",
                        value=(
                            f"**Solar Flux (SFI):** {sfi}\n"
                            f"**A-index:** {a_index}\n"
                            f"**K-index:** {k_index}\n"
                            f"*SFI >150=Excellent, 70-150=Good, <70=Poor*"
                        ),
                        inline=False
                    )
                    
                    # NOAA Scales
                    embed.add_field(
                        name="⚡ Radio Blackout",
                        value=f"**{r_scale}** (R0-R5)\n{'✅ Clear' if r_scale in ['R0', 'N/A'] else '⚠️ Degraded'}",
                        inline=True
                    )
                    
                    embed.add_field(
                        name="☀️ Solar Radiation",
                        value=f"**{s_scale}** (S0-S5)\n{'✅ Normal' if s_scale in ['S0', 'N/A'] else '⚠️ Elevated'}",
                        inline=True
                    )
                    
                    embed.add_field(
                        name="🧲 Geomagnetic Storm",
                        value=f"**{g_scale}** (G0-G5)\n{'✅ Calm' if g_scale in ['G0', 'N/A'] else '⚠️ Disturbed'}",
                        inline=True
                    )
                    
                    # Band-by-band predictions
                    band_predictions = []
                    
                    # 160m/80m - Always work
                    band_predictions.append("**160m/80m:** 🟢 Good (Night) - Always reliable for regional")
                    
                    # 40m - Most reliable
                    band_predictions.append("**40m:** 🟢 Excellent - Works day and night")
                    
                    # 30m
                    if conditions_good and sfi_value > 80:
                        band_predictions.append("**30m:** 🟢 Good - Digital modes DX possible")
                    else:
                        band_predictions.append("**30m:** 🟡 Fair - Try CW/digital for best results")
                    
                    # 20m - Depends heavily on conditions
                    if conditions_good and sfi_value > 100:
                        band_predictions.append("**20m:** 🟢 Excellent - Worldwide DX open!")
                    elif sfi_value > 80:
                        band_predictions.append("**20m:** 🟡 Fair - DX possible with patience")
                    else:
                        band_predictions.append("**20m:** 🟡 Fair - Limited to regional")
                    
                    # 17m
                    if conditions_good and sfi_value > 100:
                        band_predictions.append("**17m:** 🟢 Good - Try for DX")
                    else:
                        band_predictions.append("**17m:** 🟡 Fair - May be open briefly")
                    
                    # 15m - Solar dependent
                    if conditions_good and sfi_value > 120:
                        band_predictions.append("**15m:** 🟢 Good - Long path DX possible")
                    elif sfi_value > 90:
                        band_predictions.append("**15m:** 🟡 Fair - Check for openings")
                    else:
                        band_predictions.append("**15m:** 🔴 Poor - Likely closed")
                    
                    # 12m
                    if conditions_good and sfi_value > 120:
                        band_predictions.append("**12m:** 🟡 Fair - Worth checking")
                    else:
                        band_predictions.append("**12m:** 🔴 Poor - Probably closed")
                    
                    # 10m - Highly solar dependent
                    if conditions_good and sfi_value > 150:
                        band_predictions.append("**10m:** 🟢 Good - Magic band is open!")
                    elif sfi_value > 120:
                        band_predictions.append("**10m:** 🟡 Fair - Possible short openings")
                    else:
                        band_predictions.append("**10m:** 🔴 Poor - Closed, try WSPR")
                    
                    # 6m
                    band_predictions.append("**6m:** 🟡 Check for Sporadic-E (summer) or aurora")
                    
                    embed.add_field(
                        name="📻 Band Conditions (HF)",
                        value="\n".join(band_predictions),
                        inline=False
                    )
                    
                    # Operating recommendations
                    recommendations = []
                    
                    if r_scale != 'R0' and r_scale != 'N/A':
                        recommendations.append("⚠️ **Radio Blackout Active:** Expect HF absorption, especially on higher frequencies")
                    
                    if g_scale and g_scale not in ['G0', 'N/A']:
                        g_val = int(g_scale.replace('G', '')) if g_scale.replace('G', '').isdigit() else 0
                        if g_val >= 3:
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
                        name="🕐 Time-Based Suggestion",
                        value=f"{best_now}\n*Gray line propagation may enhance any band!*",
                        inline=False
                    )
                    
                    embed.set_footer(text="73 de Penguin Overlord! • Data from NOAA SWPC • !propagation for simple view")
                    
                    await ctx.send(embed=embed)
                else:
                    await ctx.send("❌ Unable to fetch solar data from NOAA. Try again later!")
                    
        except Exception as e:
            logger.error(f"Error fetching solar weather data: {e}")
            await ctx.send("❌ Error fetching solar weather data. Please try again later!")


async def setup(bot):
    """Load the Radiohead cog."""
    await bot.add_cog(Radiohead(bot))
    logger.info("Radiohead cog loaded")
