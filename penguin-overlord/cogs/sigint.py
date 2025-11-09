# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
SIGINT Cog - Signal Intelligence bot for frequency monitoring.
Provides information about interesting frequencies, decoders, and SDR news.
"""

import logging
import random
import discord
from discord.ext import commands

logger = logging.getLogger(__name__)


# Interesting frequencies to monitor
INTERESTING_FREQUENCIES = [
    {"freq": "14.313 MHz USB", "what": "Maritime Mobile Service Net", "desc": "Daily HAM radio net for maritime mobile operators. 20:00 UTC", "type": "HAM"},
    {"freq": "3.756 MHz LSB", "what": "Hurricane Watch Net", "desc": "Activated during Atlantic hurricanes. Emergency traffic only when active.", "type": "HAM"},
    {"freq": "7.200 MHz LSB", "what": "FEMA Interop", "desc": "Federal emergency management frequency. Active during disasters.", "type": "Government"},
    {"freq": "4.625 MHz USB", "what": "The Buzzer (UVB-76)", "desc": "Russian numbers station. Buzzes 24/7, occasionally broadcasts coded messages.", "type": "Numbers Station"},
    {"freq": "5.448 MHz USB", "what": "The Pip", "desc": "Russian time signal station. Distinctive pip sound followed by voice announcements.", "type": "Military"},
    {"freq": "6.998 MHz USB", "what": "Russian Naval Aviation", "desc": "Russian naval air traffic control. Call sign 'Skyking'.", "type": "Military"},
    {"freq": "8.992 MHz USB", "what": "US Air Force", "desc": "High Frequency Global Communications System (HFGCS). Emergency Action Messages!", "type": "Military"},
    {"freq": "11.175 MHz USB", "what": "HFGCS", "desc": "USAF EAM (Emergency Action Messages). Listen for 'Skyking' callsign.", "type": "Military"},
    {"freq": "137.5 MHz", "what": "NOAA Weather Satellites", "desc": "NOAA-15/18/19 APT transmissions. Decode weather satellite images!", "type": "Weather"},
    {"freq": "137.9125 MHz", "what": "NOAA-18 APT", "desc": "Automatic Picture Transmission from NOAA-18. Visible/IR imagery.", "type": "Weather"},
    {"freq": "1544-1545 MHz", "what": "Inmarsat C", "desc": "Maritime satellite communications. Ships, aircraft emergency beacons.", "type": "Satellite"},
    {"freq": "156.8 MHz", "what": "VHF Marine Channel 16", "desc": "International maritime distress and calling. 'Mayday' calls.", "type": "Maritime"},
    {"freq": "162.55 MHz", "what": "NOAA Weather Radio", "desc": "WX2 - Continuous weather broadcasts and emergency alerts.", "type": "Weather"},
    {"freq": "162.40 MHz", "what": "NOAA Weather Radio", "desc": "WX1 - Most common weather radio frequency.", "type": "Weather"},
    {"freq": "259.7 MHz AM", "what": "Military UHF Tactical", "desc": "Common tactical frequency for military air operations.", "type": "Military"},
    {"freq": "2182 kHz", "what": "Marine Distress", "desc": "International maritime distress frequency (being phased out for GMDSS).", "type": "Maritime"},
    {"freq": "406-406.1 MHz", "what": "EPIRB/PLB Beacons", "desc": "Emergency Position Indicating Radio Beacons. Satellite-detected distress.", "type": "Emergency"},
    {"freq": "121.5 MHz", "what": "Aviation Emergency", "desc": "Aeronautical emergency frequency. ELT beacons and distress calls.", "type": "Emergency"},
    {"freq": "243.0 MHz", "what": "Military Emergency", "desc": "Military guard frequency. Combat Search and Rescue.", "type": "Military"},
    {"freq": "123.1 MHz", "what": "Search and Rescue", "desc": "International SAR air-to-ground frequency.", "type": "Emergency"},
    {"freq": "28-30 MHz", "what": "10m Beacon Band", "desc": "HF propagation beacons. Check band openings!", "type": "HAM"},
    {"freq": "14.1-14.112 MHz", "what": "20m CW/Digital", "desc": "FT8, RTTY, PSK31. Worldwide digital communications.", "type": "HAM"},
    {"freq": "7.074 MHz", "what": "40m FT8", "desc": "Most popular FT8 frequency. Worldwide weak signal digital.", "type": "HAM"},
    {"freq": "10.140 MHz", "what": "30m FT8", "desc": "30 meters FT8/FT4. Digital mode only band (no voice!).", "type": "HAM"},
]


# SDR decoder software and tools
SDR_TOOLS = [
    {"tool": "dump1090", "desc": "ADS-B aircraft tracking decoder. Track planes on 1090 MHz.", "platform": "Linux/Windows", "use": "Aviation"},
    {"tool": "rtl_433", "desc": "Decode 433 MHz ISM devices: weather stations, tire pressure sensors, smart meters.", "platform": "Linux/Windows", "use": "IoT/Weather"},
    {"tool": "multimon-ng", "desc": "Decode POCSAG, FLEX pagers, AFSK, DTMF tones. Listen to pager traffic!", "platform": "Linux", "use": "Pagers"},
    {"tool": "direwolf", "desc": "Software TNC for APRS packet radio. Decode HAM radio digital packets.", "platform": "Linux/Windows", "use": "HAM Radio"},
    {"tool": "WSJT-X", "desc": "Decode FT8, FT4, JT65 weak signal modes. Essential for digital HAM radio.", "platform": "Cross-platform", "use": "HAM Radio"},
    {"tool": "SDR#", "desc": "Popular SDR software for Windows. Great for beginners with plugins.", "platform": "Windows", "use": "General SDR"},
    {"tool": "GQRX", "desc": "Software defined radio receiver for Linux. Clean interface, great waterfall.", "platform": "Linux/macOS", "use": "General SDR"},
    {"tool": "CubicSDR", "desc": "Cross-platform SDR software. Modern UI with good performance.", "platform": "Cross-platform", "use": "General SDR"},
    {"tool": "Inspectrum", "desc": "Offline signal analysis. Examine recordings, decode unknown signals.", "platform": "Linux", "use": "Signal Analysis"},
    {"tool": "URH", "desc": "Universal Radio Hacker. Reverse engineer wireless protocols!", "platform": "Cross-platform", "use": "Reverse Engineering"},
    {"tool": "GNU Radio", "desc": "Software radio framework. Build your own decoders with flowgraphs.", "platform": "Cross-platform", "use": "Advanced SDR"},
    {"tool": "DSD+", "desc": "Decode P25, DMR, NXDN digital voice. Listen to trunked radio systems.", "platform": "Windows", "use": "Digital Voice"},
    {"tool": "JAERO", "desc": "Decode Inmarsat Aero signals. Aircraft SATCOM communications!", "platform": "Windows", "use": "SATCOM"},
    {"tool": "WXtoImg", "desc": "Decode NOAA APT weather satellite images. See Earth from space!", "platform": "Windows/Linux", "use": "Weather Satellites"},
    {"tool": "SatDump", "desc": "Modern satellite decoder. NOAA, Meteor-M, MetOp and more!", "platform": "Cross-platform", "use": "Weather Satellites"},
    {"tool": "SDRAngel", "desc": "Multi-purpose SDR software with many built-in decoders.", "platform": "Cross-platform", "use": "General SDR"},
    {"tool": "rtl_ais", "desc": "Decode AIS (Automatic Identification System) ship tracking.", "platform": "Linux", "use": "Maritime"},
    {"tool": "dumpvdl2", "desc": "VHF Data Link decoder for aircraft ACARS-like messages.", "platform": "Linux", "use": "Aviation"},
    {"tool": "acarsdec", "desc": "Decode ACARS aircraft messages. See plane positions, weather, maintenance!", "platform": "Linux", "use": "Aviation"},
    {"tool": "FalconEye", "desc": "All-in-one SIGINT framework. Multiple decoders integrated.", "platform": "Linux", "use": "SIGINT"},
]


# SIGINT tips and facts
SIGINT_FACTS = [
    "The RTL-SDR dongle was originally a $10 TV tuner - hacked to become a wideband SDR receiver!",
    "You can receive signals from 24 MHz to 1.7 GHz with a basic RTL-SDR. That covers HAM, aviation, satellites!",
    "TEMPEST attacks can reconstruct computer screens from RF emissions. Your monitor leaks your data!",
    "Van Eck phreaking: Eavesdrop on monitors from the RF they emit. CRTs are especially vulnerable.",
    "Numbers stations broadcast coded messages to spies worldwide. Still active today! (UVB-76, The Buzzer)",
    "The Conet Project recorded numbers stations for years. Creepy, mysterious, and real espionage.",
    "SIGINT (Signals Intelligence) is different from COMINT (Communications) and ELINT (Electronic).",
    "During Cold War, both sides monitored each other's military communications 24/7 with massive antenna arrays.",
    "Project ECHELON: Global surveillance network intercepts satellite, microwave, cellular, and fiber communications.",
    "Five Eyes (FVEY): US, UK, Canada, Australia, New Zealand intelligence sharing. Massive SIGINT cooperation.",
    "The NSA's mission is SIGINT. CIA is HUMINT. Different intelligence gathering methods.",
    "Rubber-hose cryptanalysis: Sometimes it's easier to force the password than break the encryption!",
    "Software Defined Radio democratized SIGINT. Used to require millions in hardware - now just $25!",
    "Military uses 25 kHz channels for VHF/UHF. Public safety uses 12.5 kHz. Narrower = more channels!",
    "Trunked radio systems share frequencies dynamically. Harder to monitor than conventional systems.",
    "P25 is the US public safety standard. Can be encrypted, but many agencies leave it in the clear.",
    "DMR (Digital Mobile Radio) is popular in Europe and commercial use. Two voice channels per frequency!",
    "TETRA is the European public safety standard. Used by police, fire, ambulance across EU.",
    "LoRa (Long Range) operates on ISM bands. Can receive LoRaWAN IoT traffic with SDR!",
    "Zigbee, Z-Wave, and Bluetooth LE all operate around 2.4 GHz and can be monitored with HackRF/USRP.",
    "ADS-B aircraft tracking is unencrypted by design. FAA mandated it for collision avoidance.",
    "TCAS (Traffic Collision Avoidance System) operates on 1030/1090 MHz. Also monitorable!",
    "Meteor M2 weather satellites transmit 137 MHz LRPT. Better quality than NOAA APT!",
    "HRPT is high-resolution satellite imagery. Requires dish antenna but amazing quality!",
    "Iridium satellites create distinctive 'Iridium flare' - predictable, visible glints. Also listen on 1.6 GHz!",
    "Amateur radio satellites (OSCAR) are free to use worldwide. No license needed to receive!",
    "The ISS (International Space Station) has SSTV image transmissions. Decode pictures from space!",
    "Doppler shift causes frequency changes as satellites pass overhead. Must compensate when tracking!",
    "Most satellites are in polar orbits. Pass overhead twice daily at roughly same times.",
    "Pager traffic (POCSAG/FLEX) is mostly unencrypted. Restaurants, hospitals, emergency services.",
    "APRS (Automatic Packet Reporting System) broadcasts position on 144.39 MHz (US). Track vehicles!",
    "LoJack vehicle recovery operates 173 MHz. Can be tracked by police when car is stolen.",
    "EAS (Emergency Alert System) uses FSK encoding. Can decode with multimon-ng!",
    "SAME (Specific Area Message Encoding) headers identify alert type and geographic area.",
    "Weak signal propagation modes like FT8 work at -20dB SNR. Incredible digital signal processing!",
    "WSPR (Weak Signal Propagation Reporter) maps HF propagation worldwide. Crowd-sourced ionosphere!",
    "Software defined radio can transmit AND receive. HackRF, bladeRF, LimeSDR, USRP do both.",
    "Transmitting without license is illegal! Receive-only is legal (except cellular in some countries).",
    "The FCC monitors spectrum with direction-finding trucks. They WILL find illegal transmitters.",
    "Faraday cages block RF. Wrap phone in aluminum foil = no signal. (Looks crazy though!)",
]


class SIGINT(commands.Cog):
    """SIGINT - Signal Intelligence for frequency monitoring."""
    
    def __init__(self, bot):
        self.bot = bot
    
    @commands.hybrid_command(name='frequency_log', description='Get interesting frequencies to monitor')
    async def frequency_log(self, ctx: commands.Context):
        """
        Get interesting frequencies to monitor with your SDR.
        
        Usage:
            !frequency_log
            /frequency_log
        """
        freq = random.choice(INTERESTING_FREQUENCIES)
        
        # Color based on type
        colors = {
            "HAM": 0x43A047,
            "Military": 0x1976D2,
            "Government": 0xFF6F00,
            "Numbers Station": 0x5E35B1,
            "Weather": 0x00ACC1,
            "Maritime": 0x1E88E5,
            "Satellite": 0x7B1FA2,
            "Emergency": 0xE53935,
        }
        color = colors.get(freq['type'], 0x607D8B)
        
        embed = discord.Embed(
            title=f"📡 {freq['what']}",
            description=f"**Frequency:** {freq['freq']}",
            color=color
        )
        
        embed.add_field(name="Description", value=freq['desc'], inline=False)
        embed.add_field(name="Type", value=freq['type'], inline=True)
        
        if freq['type'] == "Military":
            embed.add_field(
                name="⚠️ Note",
                value="Monitoring is legal, but don't transmit on military frequencies!",
                inline=False
            )
        
        embed.set_footer(text="Use !frequency_log for more • !sdrtool for decoder software")
        
        await ctx.send(embed=embed)
    
    @commands.hybrid_command(name='sdrtool', description='Get SDR decoder tools and software')
    async def sdrtool(self, ctx: commands.Context):
        """
        Get information about SDR tools and decoder software.
        
        Usage:
            !sdrtool
            /sdrtool
        """
        tool = random.choice(SDR_TOOLS)
        
        # Color based on use
        colors = {
            "Aviation": 0x1E88E5,
            "HAM Radio": 0x43A047,
            "SIGINT": 0x1976D2,
            "General SDR": 0x5E35B1,
            "Weather Satellites": 0x00ACC1,
            "Maritime": 0x00897B,
            "Signal Analysis": 0xFF6F00,
            "Digital Voice": 0x7B1FA2,
            "Reverse Engineering": 0xE53935,
            "IoT/Weather": 0xFFB300,
            "Pagers": 0x6D4C41,
            "SATCOM": 0x3949AB,
            "Advanced SDR": 0x8B4513,
        }
        color = colors.get(tool['use'], 0x607D8B)
        
        embed = discord.Embed(
            title=f"🛠️ {tool['tool']}",
            description=tool['desc'],
            color=color
        )
        
        embed.add_field(name="Platform", value=tool['platform'], inline=True)
        embed.add_field(name="Use Case", value=tool['use'], inline=True)
        
        embed.set_footer(text="Use !sdrtool for more • !sigintfact for SIGINT trivia")
        
        await ctx.send(embed=embed)
    
    @commands.hybrid_command(name='sigintfact', description='Get SIGINT facts and tips')
    async def sigintfact(self, ctx: commands.Context):
        """
        Get signal intelligence facts, tips, and trivia.
        
        Usage:
            !sigintfact
            /sigintfact
        """
        fact = random.choice(SIGINT_FACTS)
        
        embed = discord.Embed(
            title="🔍 SIGINT Fact",
            description=fact,
            color=0x1976D2
        )
        
        embed.set_footer(text="Use !sigintfact for more • !frequency_log for frequencies")
        
        await ctx.send(embed=embed)


async def setup(bot):
    """Load the SIGINT cog."""
    await bot.add_cog(SIGINT(bot))
    logger.info("SIGINT cog loaded")
