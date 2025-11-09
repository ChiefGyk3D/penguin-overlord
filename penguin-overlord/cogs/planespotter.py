# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
Plane Spotter Cog - Aviation tracking and identification.
Provides aircraft information, transponder codes, and aviation facts.
"""

import logging
import random
import discord
from discord.ext import commands

logger = logging.getLogger(__name__)


# Aviation transponder codes and their meanings
TRANSPONDER_CODES = [
    {"code": "7500", "meaning": "Aircraft Hijacking", "action": "Immediate military response", "severity": "🚨"},
    {"code": "7600", "meaning": "Radio Failure", "action": "Continue flight, tower provides light signals", "severity": "⚠️"},
    {"code": "7700", "meaning": "General Emergency", "action": "Priority handling, emergency services alerted", "severity": "🚨"},
    {"code": "7777", "meaning": "Military Interceptor", "action": "Military aircraft on intercept mission", "severity": "⚔️"},
    {"code": "1200", "meaning": "VFR Flight (US)", "action": "Standard VFR code below 18,000 feet", "severity": "✈️"},
    {"code": "1202", "meaning": "VFR Glider", "action": "Identifies gliders/sailplanes in flight", "severity": "🪂"},
    {"code": "1255", "meaning": "Fire Fighting", "action": "Aircraft engaged in fire suppression", "severity": "🚒"},
    {"code": "1277", "meaning": "Search and Rescue", "action": "SAR operations in progress", "severity": "🚁"},
    {"code": "2000", "meaning": "UK/Europe VFR", "action": "Standard VFR code in UK/Europe", "severity": "✈️"},
    {"code": "7000", "meaning": "Conspicuity Code", "action": "International VFR code", "severity": "✈️"},
    {"code": "0000", "meaning": "Military Aircraft", "action": "Military mission, Mode 3/A not required", "severity": "⚔️"},
    {"code": "4000-4777", "meaning": "Special Use", "action": "Reserved for special military/government use", "severity": "⚔️"},
]


# Aircraft types and interesting facts
AIRCRAFT_TYPES = [
    {"type": "Cessna 172 Skyhawk", "desc": "Most produced aircraft in history with 44,000+ built. The Honda Civic of aviation.", "category": "General Aviation"},
    {"type": "Boeing 747", "desc": "The 'Queen of the Skies' - first widebody airliner. Instantly recognizable hump.", "category": "Airliners"},
    {"type": "Airbus A380", "desc": "World's largest passenger airliner. Full double-deck, can carry 850+ passengers.", "category": "Airliners"},
    {"type": "SR-71 Blackbird", "desc": "Fastest manned aircraft ever: Mach 3.3 (2,200 mph). Still unbeaten since 1976.", "category": "Military"},
    {"type": "F-22 Raptor", "desc": "Stealth air superiority fighter with thrust vectoring. Nearly invisible to radar.", "category": "Military"},
    {"type": "C-130 Hercules", "desc": "Tactical airlifter in service since 1956. Can land on dirt strips and aircraft carriers!", "category": "Military"},
    {"type": "Piper J-3 Cub", "desc": "Iconic yellow trainer. Trained 80% of WWII pilots. Cruises at 75mph!", "category": "General Aviation"},
    {"type": "Beechcraft Bonanza", "desc": "V-tail 'Doctor Killer' - fast, complex single-engine aircraft. Distinctive design.", "category": "General Aviation"},
    {"type": "Concorde", "desc": "Supersonic airliner, Mach 2.04. NYC to London in 3.5 hours. Retired 2003.", "category": "Airliners"},
    {"type": "Boeing 737", "desc": "Best-selling jetliner ever with 10,000+ delivered. Workhorse of regional airlines.", "category": "Airliners"},
    {"type": "Antonov An-225 Mriya", "desc": "World's largest aircraft by weight. Single example, sadly destroyed in Ukraine war 2022.", "category": "Cargo"},
    {"type": "C-5 Galaxy", "desc": "One of largest military aircraft. Can carry tanks, helicopters, entire cargo planes!", "category": "Military"},
    {"type": "P-51 Mustang", "desc": "WWII fighter icon. Rolls-Royce Merlin engine, long range bomber escort.", "category": "Warbirds"},
    {"type": "Spitfire", "desc": "British WWII legend. Distinctive elliptical wings. Saved Britain in Battle of Britain.", "category": "Warbirds"},
    {"type": "B-17 Flying Fortress", "desc": "WWII heavy bomber. Could survive massive damage and still fly home.", "category": "Warbirds"},
    {"type": "B-2 Spirit", "desc": "Stealth bomber, each costs $2.2 billion. Looks like UFO, invisible to radar.", "category": "Military"},
    {"type": "U-2 Dragon Lady", "desc": "High-altitude spy plane, flies at 70,000+ feet. Extremely difficult to land.", "category": "Military"},
    {"type": "MQ-9 Reaper", "desc": "Military drone for surveillance and strikes. Can stay airborne for 27+ hours.", "category": "UAV"},
    {"type": "Cirrus SR22", "desc": "Most popular single-engine aircraft. Built-in parachute for the ENTIRE plane!", "category": "General Aviation"},
    {"type": "Robinson R44", "desc": "Most popular civilian helicopter. Four-seat, used for training and touring.", "category": "Rotorcraft"},
]


# Aviation frequency bands and uses
AVIATION_FREQUENCIES = [
    {"freq": "121.5 MHz", "use": "Emergency Frequency", "desc": "International aeronautical emergency - monitored 24/7 by ATC and satellites"},
    {"freq": "118-137 MHz", "use": "VHF Air Band", "desc": "Primary aircraft communications with ATC. AM modulation."},
    {"freq": "243.0 MHz", "use": "Military Emergency", "desc": "Military emergency frequency, monitored by military assets worldwide"},
    {"freq": "1090 MHz", "use": "Mode S / ADS-B", "desc": "Automatic aircraft position reporting. Track planes on FlightRadar24!"},
    {"freq": "978 MHz", "use": "UAT ADS-B", "desc": "US ADS-B frequency below 18,000 feet. Weather and traffic info."},
    {"freq": "123.45 MHz", "use": "Air-to-Air", "desc": "Unofficial frequency for pilot chat in flight (not official, but widely used)"},
    {"freq": "122.75 MHz", "use": "Air-to-Air (official)", "desc": "Official air-to-air communication frequency for non-emergency use"},
    {"freq": "122.9 MHz", "use": "Multicom", "desc": "Coordination at non-towered airports - pilots announce positions"},
    {"freq": "126.7 MHz", "use": "ARINC", "desc": "Company frequency for airline operational communications"},
    {"freq": "121.9 MHz", "use": "Ground Control", "desc": "Common ground control frequency at towered airports"},
    {"freq": "ACARS", "use": "Aircraft Communications Addressing and Reporting System", "desc": "Data link for position, weather, maintenance - decodeable with SDR!"},
]


# Aviation facts and trivia
AVIATION_FACTS = [
    "ADS-B (Automatic Dependent Surveillance-Broadcast) transmits aircraft position, altitude, and velocity on 1090 MHz every second.",
    "You can track aircraft worldwide with a $25 RTL-SDR dongle and free software like dump1090!",
    "Modern airliners transmit their position data unencrypted - that's how FlightRadar24 and FlightAware work.",
    "Squawk codes are 4-digit octal numbers (0-7 only), giving 4,096 possible combinations.",
    "The black box isn't black - it's bright orange for visibility in wreckage. Can survive 1,100°C fire!",
    "Commercial jets fly at FL350-430 (35,000-43,000 feet) for fuel efficiency and less turbulence.",
    "Pilots set altimeter to 29.92 inHg above 18,000 feet (transition altitude) for standard pressure.",
    "TCAS (Traffic Collision Avoidance System) saved countless lives by warning pilots of nearby aircraft.",
    "An aircraft's registration (tail number) is unique worldwide, like a VIN for cars.",
    "Military aircraft often fly 'squawk off' (no transponder) during training or tactical operations.",
    "The sound barrier was first broken by Chuck Yeager in the Bell X-1 in 1947.",
    "Contrails form when hot exhaust meets cold air at high altitude, creating ice crystals.",
    "Chemtrails are not real. Contrails are just water vapor and depend on temperature/humidity.",
    "Airbus aircraft use fly-by-wire - pilot inputs go to computers that control the plane.",
    "Boeing philosophy: Let pilots override automation. Airbus: Trust the automation's limits.",
    "A fully loaded 747 weighs around 412,000 kg (900,000 lbs) - and it flies!",
    "Gliders can stay aloft for hours using thermals and ridge lift - no engine needed!",
    "The Gimli Glider: 767 ran out of fuel at 41,000 feet, pilot glided to abandoned runway. Everyone survived!",
    "Pilots and co-pilots eat different meals to prevent food poisoning from grounding both.",
    "Lightning strikes aircraft regularly - they're designed for it. Faraday cage effect protects passengers.",
]


class PlaneSpotter(commands.Cog):
    """Plane Spotter - Aviation tracking and identification."""
    
    def __init__(self, bot):
        self.bot = bot
    
    @commands.hybrid_command(name='squawk', description='Get transponder code information')
    async def squawk(self, ctx: commands.Context, code: str = None):
        """
        Get information about aviation transponder (squawk) codes.
        Optionally specify a code, or get a random one.
        
        Usage:
            !squawk - Random squawk code
            !squawk 7700 - Info about specific code
            /squawk
        """
        if code:
            # Look up specific code
            matching = [s for s in TRANSPONDER_CODES if s['code'] == code]
            if matching:
                squawk = matching[0]
            else:
                await ctx.send(f"❌ Unknown squawk code: {code}\nTry: 7500, 7600, 7700, 1200, 2000")
                return
        else:
            # Random code
            squawk = random.choice(TRANSPONDER_CODES)
        
        # Color based on severity
        color_map = {"🚨": 0xFF0000, "⚠️": 0xFF6F00, "⚔️": 0x1976D2, "✈️": 0x43A047, "🪂": 0x00ACC1, "🚒": 0xE53935, "🚁": 0x00897B}
        color = color_map.get(squawk['severity'], 0x607D8B)
        
        embed = discord.Embed(
            title=f"{squawk['severity']} Squawk Code: {squawk['code']}",
            description=f"**{squawk['meaning']}**",
            color=color
        )
        
        embed.add_field(name="Response/Action", value=squawk['action'], inline=False)
        
        if squawk['code'] in ['7500', '7600', '7700']:
            embed.add_field(
                name="⚠️ Emergency Code",
                value="This is an emergency code! If you see this on ADS-B, aircraft is in distress.",
                inline=False
            )
        
        embed.set_footer(text="Use !squawk [code] for specific codes • !aircraft for plane info")
        
        await ctx.send(embed=embed)
    
    @commands.hybrid_command(name='aircraft', description='Get aircraft type information')
    async def aircraft(self, ctx: commands.Context):
        """
        Get information about aircraft types and interesting facts.
        
        Usage:
            !aircraft
            /aircraft
        """
        aircraft = random.choice(AIRCRAFT_TYPES)
        
        # Color based on category
        colors = {
            "General Aviation": 0x43A047,
            "Airliners": 0x1E88E5,
            "Military": 0x1976D2,
            "Cargo": 0xFF6F00,
            "Warbirds": 0x8B4513,
            "UAV": 0x5E35B1,
            "Rotorcraft": 0x00ACC1,
        }
        color = colors.get(aircraft['category'], 0x607D8B)
        
        embed = discord.Embed(
            title=f"✈️ {aircraft['type']}",
            description=aircraft['desc'],
            color=color
        )
        
        embed.add_field(name="Category", value=aircraft['category'], inline=True)
        
        embed.set_footer(text="Use !aircraft for more • !avfact for aviation trivia")
        
        await ctx.send(embed=embed)
    
    @commands.hybrid_command(name='avfreq', description='Get aviation frequency information')
    async def avfreq(self, ctx: commands.Context):
        """
        Get information about aviation frequencies and their uses.
        
        Usage:
            !avfreq
            /avfreq
        """
        freq = random.choice(AVIATION_FREQUENCIES)
        
        embed = discord.Embed(
            title=f"📡 Aviation Frequency",
            description=f"**{freq['freq']}** - {freq['use']}",
            color=0x1E88E5
        )
        
        embed.add_field(name="Description", value=freq['desc'], inline=False)
        
        if '121.5' in freq['freq'] or '243.0' in freq['freq']:
            embed.add_field(
                name="🚨 Emergency Frequency",
                value="Never transmit on this frequency unless it's an actual emergency!",
                inline=False
            )
        
        embed.set_footer(text="Monitor aviation frequencies with an RTL-SDR! • !avfact for more")
        
        await ctx.send(embed=embed)
    
    @commands.hybrid_command(name='avfact', description='Get aviation facts and trivia')
    async def avfact(self, ctx: commands.Context):
        """
        Get random aviation facts and trivia.
        
        Usage:
            !avfact
            /avfact
        """
        fact = random.choice(AVIATION_FACTS)
        
        embed = discord.Embed(
            title="✈️ Aviation Fact",
            description=fact,
            color=0x43A047
        )
        
        embed.set_footer(text="Use !avfact for more • !squawk for transponder codes")
        
        await ctx.send(embed=embed)


async def setup(bot):
    """Load the PlaneSpotter cog."""
    await bot.add_cog(PlaneSpotter(bot))
    logger.info("PlaneSpotter cog loaded")
