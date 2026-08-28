# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
XKCD Cog - Commands for fetching and displaying XKCD comics.
"""

import asyncio
import logging
import random
import aiohttp
import discord
from discord.ext import commands
from discord import app_commands

logger = logging.getLogger(__name__)


class XKCD(commands.Cog):
    """XKCD comic commands - because everyone loves XKCD!"""

    XKCD_API_BASE = "https://xkcd.com"
    # Concurrency cap for the search fan-out so we don't hammer xkcd.com
    SEARCH_CONCURRENCY = 8

    def __init__(self, bot):
        self.bot = bot
        self.session = None

    async def cog_load(self):
        self.session = aiohttp.ClientSession()

    async def cog_unload(self):
        if self.session:
            await self.session.close()

    async def _fetch_comic(self, comic_num: int = None) -> dict:
        """
        Fetch an XKCD comic from the API.

        Args:
            comic_num: Comic number to fetch, or None for latest

        Returns:
            Dict with comic data or None on error
        """
        try:
            if comic_num:
                url = f"{self.XKCD_API_BASE}/{comic_num}/info.0.json"
            else:
                url = f"{self.XKCD_API_BASE}/info.0.json"

            if not self.session:
                self.session = aiohttp.ClientSession()

            async with self.session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status == 404:
                    logger.warning(f"XKCD comic {comic_num} not found")
                    return None
                response.raise_for_status()
                return await response.json()
        except aiohttp.ClientResponseError as e:
            logger.error(f"HTTP error fetching XKCD comic: {e}")
            return None
        except Exception as e:
            logger.error(f"Error fetching XKCD comic: {e}")
            return None

    def _create_comic_embed(self, comic_data: dict) -> discord.Embed:
        """
        Create a Discord embed for an XKCD comic.

        Args:
            comic_data: Comic data from XKCD API

        Returns:
            Discord embed with comic information
        """
        embed = discord.Embed(
            title=f"#{comic_data['num']}: {comic_data['title']}",
            url=f"{self.XKCD_API_BASE}/{comic_data['num']}",
            color=discord.Color.blue()
        )

        embed.set_image(url=comic_data['img'])

        # Add alt text as description
        if comic_data.get('alt'):
            embed.description = f"_{comic_data['alt']}_"

        # Add date published (convert to int in case they're strings)
        year = int(comic_data['year'])
        month = int(comic_data['month'])
        day = int(comic_data['day'])
        date_str = f"{year}-{month:02d}-{day:02d}"
        embed.set_footer(text=f"Published: {date_str}")

        return embed

    @commands.hybrid_command(name='xkcd', description='Get an XKCD comic')
    @app_commands.describe(number='Comic number (leave blank for latest)')
    async def xkcd_command(self, ctx: commands.Context, number: int = None):
        """
        Get an XKCD comic by number, or the latest if no number is provided.

        Usage:
            !xkcd - Get the latest comic
            !xkcd 1234 - Get comic #1234
        """
        await ctx.defer()

        comic_data = await self._fetch_comic(number)

        if not comic_data:
            if number:
                await ctx.send(f"❌ Could not find XKCD comic #{number}. Please check the number and try again.")
            else:
                await ctx.send("❌ Could not fetch the latest XKCD comic. Please try again later.")
            return

        embed = self._create_comic_embed(comic_data)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name='xkcd_random', description='Get a random XKCD comic')
    async def xkcd_random(self, ctx: commands.Context):
        """
        Get a random XKCD comic.

        Usage:
            !xkcd_random
        """
        await ctx.defer()

        # First, get the latest comic to know the max number
        latest = await self._fetch_comic()
        if not latest:
            await ctx.send("❌ Could not fetch XKCD data. Please try again later.")
            return

        max_comic = latest['num']
        random_num = random.randint(1, max_comic)

        comic_data = await self._fetch_comic(random_num)

        if not comic_data:
            await ctx.send(f"❌ Could not fetch XKCD comic #{random_num}. Please try again.")
            return

        embed = self._create_comic_embed(comic_data)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name='xkcd_latest', description='Get the latest XKCD comic')
    async def xkcd_latest(self, ctx: commands.Context):
        """
        Get the latest XKCD comic.

        Usage:
            !xkcd_latest
        """
        await ctx.defer()

        comic_data = await self._fetch_comic()

        if not comic_data:
            await ctx.send("❌ Could not fetch the latest XKCD comic. Please try again later.")
            return

        embed = self._create_comic_embed(comic_data)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name='xkcd_search', description='Search for XKCD comics by keyword')
    @app_commands.describe(keyword='Keyword to search for in comic titles')
    async def xkcd_search(self, ctx: commands.Context, *, keyword: str):
        """
        Search for XKCD comics containing a keyword in the title.
        Note: This is a simple search that checks recent comics.

        Usage:
            !xkcd_search python
        """
        await ctx.defer()

        # Get the latest comic to know the range
        latest = await self._fetch_comic()
        if not latest:
            await ctx.send("❌ Could not fetch XKCD data. Please try again later.")
            return

        max_comic = latest['num']
        keyword_lower = keyword.lower()

        # Search the last 100 comics for matches
        search_start = max(1, max_comic - 99)

        await ctx.send(f"🔍 Searching comics #{search_start} to #{max_comic} for '{keyword}'...")

        semaphore = asyncio.Semaphore(self.SEARCH_CONCURRENCY)

        async def fetch_bounded(num: int) -> dict:
            async with semaphore:
                return await self._fetch_comic(num)

        results = await asyncio.gather(
            *(fetch_bounded(num) for num in range(max_comic, search_start - 1, -1))
        )

        matches = [
            comic_data for comic_data in results
            if comic_data and keyword_lower in comic_data['title'].lower()
        ][:5]  # Limit to 5 results, newest first

        if not matches:
            await ctx.send(f"❌ No comics found matching '{keyword}' in the last 100 comics.")
            return

        # Show the first match as an embed
        embed = self._create_comic_embed(matches[0])

        # Add other matches to the footer
        if len(matches) > 1:
            other_nums = ", ".join(f"#{c['num']}" for c in matches[1:])
            embed.add_field(
                name="Other matches",
                value=f"{other_nums}",
                inline=False
            )

        await ctx.send(f"Found {len(matches)} match(es):", embed=embed)


async def setup(bot):
    """Load the XKCD cog."""
    await bot.add_cog(XKCD(bot))
    logger.info("XKCD cog loaded")
