# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
Event Pinger Cog - Cybersecurity conference reminders.
Posts reminders for DEF CON, BSides, GrrCon, and other security events.
"""

import logging
import csv
import os
from datetime import datetime
import discord
from discord.ext import commands, tasks

logger = logging.getLogger(__name__)


class EventPaginatorView(discord.ui.View):
    """Paginator view for browsing through multiple pages of events."""
    
    def __init__(self, embeds: list[discord.Embed]):
        super().__init__(timeout=180)  # 3 minutes timeout
        self.embeds = embeds
        self.current_page = 0
        self.message = None
        
        # Update button states
        self._update_buttons()
    
    def _update_buttons(self):
        """Update button enabled/disabled state based on current page."""
        self.first_page.disabled = self.current_page == 0
        self.prev_page.disabled = self.current_page == 0
        self.next_page.disabled = self.current_page >= len(self.embeds) - 1
        self.last_page.disabled = self.current_page >= len(self.embeds) - 1
    
    @discord.ui.button(label="⏮️", style=discord.ButtonStyle.secondary)
    async def first_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Go to first page."""
        self.current_page = 0
        self._update_buttons()
        await interaction.response.edit_message(embed=self.embeds[self.current_page], view=self)
    
    @discord.ui.button(label="◀️", style=discord.ButtonStyle.primary)
    async def prev_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Go to previous page."""
        self.current_page = max(0, self.current_page - 1)
        self._update_buttons()
        await interaction.response.edit_message(embed=self.embeds[self.current_page], view=self)
    
    @discord.ui.button(label="▶️", style=discord.ButtonStyle.primary)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Go to next page."""
        self.current_page = min(len(self.embeds) - 1, self.current_page + 1)
        self._update_buttons()
        await interaction.response.edit_message(embed=self.embeds[self.current_page], view=self)
    
    @discord.ui.button(label="⏭️", style=discord.ButtonStyle.secondary)
    async def last_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Go to last page."""
        self.current_page = len(self.embeds) - 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self.embeds[self.current_page], view=self)
    
    @discord.ui.button(label="🗑️", style=discord.ButtonStyle.danger)
    async def delete(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Delete the message."""
        await interaction.message.delete()
        self.stop()
    
    async def on_timeout(self):
        """Called when the view times out."""
        if self.message:
            try:
                # Disable all buttons when timed out
                for item in self.children:
                    item.disabled = True
                await self.message.edit(view=self)
            except:
                pass


class EventPinger(commands.Cog):
    """Event Pinger - Cybersecurity conference reminders."""
    
    def __init__(self, bot):
        self.bot = bot
        self.events = []
        self.load_events()
        # Start the background task to check for upcoming events
        # Uncomment when ready to enable automatic reminders
        # self.check_upcoming_events.start()
    
    def cog_unload(self):
        """Clean up when cog is unloaded."""
        # Cancel the background task if it's running
        if hasattr(self, 'check_upcoming_events'):
            self.check_upcoming_events.cancel()
    
    def load_events(self):
        """Load all events from CSV files in the events folder."""
        # Get the path to the events folder
        # Assuming bot is run from penguin-overlord/penguin-overlord/
        events_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), '..', 'events')
        events_dir = os.path.normpath(events_dir)
        
        self.events = []
        today = datetime.now()
        
        try:
            # Find all CSV files in the events directory
            csv_files = [f for f in os.listdir(events_dir) if f.endswith('.csv')]
            
            if not csv_files:
                logger.warning(f"No CSV files found in {events_dir}")
                return
            
            logger.info(f"Found {len(csv_files)} CSV file(s) in events directory")
            
            for csv_file in csv_files:
                csv_path = os.path.join(events_dir, csv_file)
                logger.info(f"Loading events from {csv_file}")
                
                try:
                    with open(csv_path, 'r', encoding='utf-8') as f:
                        reader = csv.DictReader(f)
                        
                        for row in reader:
                            # Parse dates
                            try:
                                start_date = datetime.strptime(row['Start Date'], '%Y-%m-%d')
                                
                                # End date might be empty for some events (e.g., single-day without end date)
                                end_date_str = row.get('End Date', '').strip()
                                if end_date_str:
                                    end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
                                else:
                                    # If no end date, assume same as start date
                                    end_date = start_date
                                
                                # Skip events that have already ended
                                if end_date.date() < today.date():
                                    continue
                                
                                event_data = {
                                    'name': row['Event'],
                                    'start_date': start_date,
                                    'end_date': end_date,
                                    'city': row.get('City', 'Unknown'),
                                    'state': row.get('State', 'Unknown'),
                                    'url': row.get('URL', ''),
                                    'source': row.get('Source', 'Unknown'),
                                    'type': row.get('Type', 'Event'),  # Cybersecurity, Ham Radio, etc.
                                    'date_status': row.get('Date Status', 'Unknown')  # Confirmed, Estimated
                                }
                                self.events.append(event_data)
                            except (ValueError, KeyError) as e:
                                logger.warning(f"Error parsing event row in {csv_file}: {e}")
                                continue
                        
                except Exception as e:
                    logger.error(f"Error reading {csv_file}: {e}")
                    continue
            
            logger.info(f"Loaded {len(self.events)} total events (excluding past events)")
        except FileNotFoundError:
            logger.error(f"Events directory not found at {events_dir}")
        except Exception as e:
            logger.error(f"Error loading events: {e}")
    
    def get_upcoming_events(self, days_ahead=30):
        """Get events happening within the next N days."""
        today = datetime.now()
        upcoming = []
        
        for event in self.events:
            days_until = (event['start_date'] - today).days
            
            # Include events happening within the specified days
            if 0 <= days_until <= days_ahead:
                event_copy = event.copy()
                event_copy['days_until'] = days_until
                upcoming.append(event_copy)
        
        # Sort by start date
        upcoming.sort(key=lambda x: x['start_date'])
        return upcoming
    
    def get_events_by_timeframe(self, weeks=4):
        """Get events grouped by week for the next N weeks."""
        today = datetime.now()
        events_by_week = {}
        
        for event in self.events:
            days_until = (event['start_date'] - today).days
            
            if days_until < 0:
                continue  # Skip past events
            
            week_num = days_until // 7
            if week_num < weeks:
                if week_num not in events_by_week:
                    events_by_week[week_num] = []
                events_by_week[week_num].append(event)
        
        return events_by_week
    
    @commands.hybrid_command(name='events', description='List upcoming cybersecurity and ham radio events')
    async def events_list(self, ctx: commands.Context, days: int = 30, event_type: str = None):
        """
        List upcoming conferences and events.
        
        Usage:
            !events - Show all events in the next 30 days
            !events 60 - Show all events in the next 60 days
            !events 30 cybersecurity - Show only cybersecurity events
            !events 60 ham - Show only ham radio events
            /events
        """
        upcoming = self.get_upcoming_events(days_ahead=days)
        
        # Filter by event type if specified
        if event_type:
            event_type_lower = event_type.lower()
            if 'ham' in event_type_lower or 'radio' in event_type_lower:
                upcoming = [e for e in upcoming if 'ham' in e.get('type', '').lower() or 'radio' in e.get('type', '').lower()]
                type_filter = "Ham Radio"
            elif 'cyber' in event_type_lower or 'security' in event_type_lower:
                upcoming = [e for e in upcoming if 'cyber' in e.get('type', '').lower() or 'security' in e.get('type', '').lower()]
                type_filter = "Cybersecurity"
            else:
                type_filter = event_type.title()
                upcoming = [e for e in upcoming if event_type_lower in e.get('type', '').lower()]
        else:
            type_filter = "All"
        
        if not upcoming:
            await ctx.send(f"📅 No {type_filter.lower()} events found in the next {days} days.")
            return
        
        # Choose emoji based on type filter
        if type_filter == "Ham Radio":
            title_emoji = "📻"
        elif type_filter == "Cybersecurity":
            title_emoji = "🔐"
        else:
            title_emoji = "📅"
        
        embed = discord.Embed(
            title=f"{title_emoji} Upcoming {type_filter} Events",
            description=f"Events happening in the next {days} days",
            color=0xFF6B00
        )
        
        for event in upcoming[:10]:  # Limit to 10 events to avoid embed size limits
            days_until = event['days_until']
            
            if days_until == 0:
                time_str = "**TODAY!**"
            elif days_until == 1:
                time_str = "**Tomorrow!**"
            else:
                time_str = f"In {days_until} days"
            
            # Format date range
            if event['start_date'].date() == event['end_date'].date():
                date_str = event['start_date'].strftime('%b %d, %Y')
            else:
                date_str = f"{event['start_date'].strftime('%b %d')} - {event['end_date'].strftime('%b %d, %Y')}"
            
            location = f"{event['city']}, {event['state']}"
            
            # Add event type emoji
            event_type = event.get('type', 'Event')
            if 'ham' in event_type.lower() or 'radio' in event_type.lower():
                type_emoji = "📻"
            elif 'cyber' in event_type.lower() or 'security' in event_type.lower():
                type_emoji = "🔐"
            else:
                type_emoji = "📅"
            
            # Add date status indicator
            date_status = event.get('date_status', '')
            if 'estimated' in date_status.lower():
                date_indicator = "⚠️ (Estimated)"
            else:
                date_indicator = "✅ (Confirmed)"
            
            field_value = (
                f"{type_emoji} **Type:** {event_type}\n"
                f"📍 **Location:** {location}\n"
                f"📆 **Date:** {date_str} {date_indicator}\n"
                f"⏰ **Time Until:** {time_str}\n"
                f"🔗 [Event Website]({event['url']})" if event.get('url') else f"{type_emoji} Type: {event_type}\n📍 Location: {location}\n📆 Date: {date_str} {date_indicator}\n⏰ Time Until: {time_str}"
            )
            
            embed.add_field(
                name=f"{event['name']}",
                value=field_value,
                inline=False
            )
        
        if len(upcoming) > 10:
            embed.set_footer(text=f"Showing 10 of {len(upcoming)} events • Use !allevents for paginated view")
        else:
            embed.set_footer(text="Filter by type: !events 30 cybersecurity or !events 60 ham")
        
        await ctx.send(embed=embed)
    
    @commands.hybrid_command(name='allevents', description='Browse all upcoming events with pagination')
    async def all_events(self, ctx: commands.Context, event_type: str = None):
        """
        Browse all upcoming events with pagination controls.
        
        Usage:
            !allevents - Browse all upcoming events
            !allevents cybersecurity - Browse only cybersecurity events
            !allevents ham - Browse only ham radio events
            /allevents
        """
        # Get all upcoming events (365 days ahead to catch all)
        upcoming = self.get_upcoming_events(days_ahead=365)
        
        # Filter by event type if specified
        if event_type:
            event_type_lower = event_type.lower()
            if 'ham' in event_type_lower or 'radio' in event_type_lower:
                upcoming = [e for e in upcoming if 'ham' in e.get('type', '').lower() or 'radio' in e.get('type', '').lower()]
                type_filter = "Ham Radio"
            elif 'cyber' in event_type_lower or 'security' in event_type_lower:
                upcoming = [e for e in upcoming if 'cyber' in e.get('type', '').lower() or 'security' in e.get('type', '').lower()]
                type_filter = "Cybersecurity"
            else:
                type_filter = event_type.title()
                upcoming = [e for e in upcoming if event_type_lower in e.get('type', '').lower()]
        else:
            type_filter = "All"
        
        if not upcoming:
            await ctx.send(f"📅 No {type_filter.lower()} events found in the database.")
            return
        
        # Choose emoji based on type filter
        if type_filter == "Ham Radio":
            title_emoji = "📻"
            color = 0xFF9800
        elif type_filter == "Cybersecurity":
            title_emoji = "🔐"
            color = 0xFF6B00
        else:
            title_emoji = "📅"
            color = 0x2196F3
        
        # Create pages - 5 events per page
        events_per_page = 5
        embeds = []
        
        for page_num in range(0, len(upcoming), events_per_page):
            page_events = upcoming[page_num:page_num + events_per_page]
            current_page = (page_num // events_per_page) + 1
            total_pages = (len(upcoming) + events_per_page - 1) // events_per_page
            
            embed = discord.Embed(
                title=f"{title_emoji} {type_filter} Events - Page {current_page}/{total_pages}",
                description=f"Showing {len(upcoming)} upcoming event(s)",
                color=color
            )
            
            for event in page_events:
                days_until = event['days_until']
                
                if days_until == 0:
                    time_str = "**TODAY!**"
                elif days_until == 1:
                    time_str = "**Tomorrow!**"
                else:
                    time_str = f"In {days_until} days"
                
                # Format date range
                if event['start_date'].date() == event['end_date'].date():
                    date_str = event['start_date'].strftime('%b %d, %Y')
                else:
                    date_str = f"{event['start_date'].strftime('%b %d')} - {event['end_date'].strftime('%b %d, %Y')}"
                
                location = f"{event['city']}, {event['state']}"
                
                # Add event type emoji
                event_type_val = event.get('type', 'Event')
                if 'ham' in event_type_val.lower() or 'radio' in event_type_val.lower():
                    type_emoji = "📻"
                elif 'cyber' in event_type_val.lower() or 'security' in event_type_val.lower():
                    type_emoji = "🔐"
                else:
                    type_emoji = "📅"
                
                # Add date status indicator
                date_status = event.get('date_status', '')
                if 'estimated' in date_status.lower():
                    date_indicator = "⚠️ (Estimated)"
                else:
                    date_indicator = "✅ (Confirmed)"
                
                field_value = (
                    f"{type_emoji} **Type:** {event_type_val}\n"
                    f"📍 **Location:** {location}\n"
                    f"📆 **Date:** {date_str} {date_indicator}\n"
                    f"⏰ **Time Until:** {time_str}\n"
                )
                
                if event.get('url'):
                    field_value += f"🔗 [Event Website]({event['url']})"
                
                embed.add_field(
                    name=f"{event['name']}",
                    value=field_value,
                    inline=False
                )
            
            embed.set_footer(text=f"Page {current_page}/{total_pages} • Use buttons to navigate")
            embeds.append(embed)
        
        # Create paginator view and send
        if len(embeds) > 1:
            view = EventPaginatorView(embeds)
            message = await ctx.send(embed=embeds[0], view=view)
            view.message = message
        else:
            # Only one page, no need for pagination
            await ctx.send(embed=embeds[0])
    
    @commands.hybrid_command(name='nextevent', description='Get the next upcoming cybersecurity event')
    async def next_event(self, ctx: commands.Context):
        """
        Get details about the next upcoming cybersecurity event.
        
        Usage:
            !nextevent
            /nextevent
        """
        upcoming = self.get_upcoming_events(days_ahead=365)
        
        if not upcoming:
            await ctx.send("📅 No upcoming cybersecurity events found in the database.")
            return
        
        event = upcoming[0]
        days_until = event['days_until']
        
        if days_until == 0:
            time_str = "🔥 **HAPPENING TODAY!**"
            color = 0xFF0000
        elif days_until == 1:
            time_str = "⚡ **TOMORROW!**"
            color = 0xFF6B00
        elif days_until <= 7:
            time_str = f"📅 **In {days_until} days**"
            color = 0xFFB300
        else:
            time_str = f"📅 In {days_until} days"
            color = 0x4CAF50
        
        # Format date range
        if event['start_date'].date() == event['end_date'].date():
            date_str = event['start_date'].strftime('%B %d, %Y')
        else:
            date_str = f"{event['start_date'].strftime('%B %d')} - {event['end_date'].strftime('%B %d, %Y')}"
        
        embed = discord.Embed(
            title=f"🔐 Next Event: {event['name']}",
            description=time_str,
            color=color,
            url=event['url']
        )
        
        # Add event type emoji to title
        event_type = event.get('type', 'Event')
        if 'ham' in event_type.lower() or 'radio' in event_type.lower():
            type_emoji = "📻"
        elif 'cyber' in event_type.lower() or 'security' in event_type.lower():
            type_emoji = "🔐"
        else:
            type_emoji = "📅"
        
        embed.add_field(
            name=f"{type_emoji} Event Type",
            value=event_type,
            inline=True
        )
        
        embed.add_field(
            name="📍 Location",
            value=f"{event['city']}, {event['state']}",
            inline=True
        )
        
        # Add date status
        date_status = event.get('date_status', 'Unknown')
        date_indicator = "✅ Confirmed" if 'confirmed' in date_status.lower() else "⚠️ Estimated"
        
        embed.add_field(
            name="📆 Date",
            value=f"{date_str}\n{date_indicator}",
            inline=True
        )
        
        if event.get('url'):
            embed.add_field(
                name="🔗 Website",
                value=f"[{event['name']} Site]({event['url']})",
                inline=False
            )
        
        # Add countdown
        if days_until > 0:
            embed.add_field(
                name="⏰ Countdown",
                value=f"{days_until} days until event starts!",
                inline=False
            )
        
        embed.set_footer(text="Use !events to see more upcoming events")
        
        await ctx.send(embed=embed)
    
    @commands.hybrid_command(name='searchevent', description='Search for a specific event or location')
    async def search_event(self, ctx: commands.Context, *, query: str):
        """
        Search for cybersecurity events by name or location.
        
        Usage:
            !searchevent DEF CON
            !searchevent Seattle
            !searchevent BSides
            /searchevent query:Chicago
        """
        query_lower = query.lower()
        matches = []
        
        for event in self.events:
            # Search in event name, city, and state
            if (query_lower in event['name'].lower() or
                query_lower in event['city'].lower() or
                query_lower in event['state'].lower()):
                
                # Calculate days until
                today = datetime.now()
                days_until = (event['start_date'] - today).days
                
                event_copy = event.copy()
                event_copy['days_until'] = days_until
                matches.append(event_copy)
        
        if not matches:
            await ctx.send(f"❌ No events found matching '{query}'")
            return
        
        # Sort by start date
        matches.sort(key=lambda x: x['start_date'])
        
        embed = discord.Embed(
            title=f"🔍 Search Results: '{query}'",
            description=f"Found {len(matches)} matching event(s)",
            color=0x2196F3
        )
        
        for event in matches[:10]:  # Limit to 10 results
            days_until = event['days_until']
            
            if days_until < 0:
                time_str = f"Passed {abs(days_until)} days ago"
            elif days_until == 0:
                time_str = "**TODAY!**"
            elif days_until == 1:
                time_str = "**Tomorrow!**"
            else:
                time_str = f"In {days_until} days"
            
            # Format date range
            if event['start_date'].date() == event['end_date'].date():
                date_str = event['start_date'].strftime('%b %d, %Y')
            else:
                date_str = f"{event['start_date'].strftime('%b %d')} - {event['end_date'].strftime('%b %d, %Y')}"
            
            location = f"{event['city']}, {event['state']}"
            
            # Add event type emoji
            event_type = event.get('type', 'Event')
            if 'ham' in event_type.lower() or 'radio' in event_type.lower():
                type_emoji = "📻"
            elif 'cyber' in event_type.lower() or 'security' in event_type.lower():
                type_emoji = "🔐"
            else:
                type_emoji = "📅"
            
            # Add date status
            date_status = event.get('date_status', '')
            if 'estimated' in date_status.lower():
                date_indicator = "⚠️"
            else:
                date_indicator = "✅"
            
            field_value = (
                f"{type_emoji} **{event_type}** {date_indicator}\n"
                f"📍 {location}\n"
                f"📆 {date_str}\n"
                f"⏰ {time_str}\n"
            )
            
            if event.get('url'):
                field_value += f"🔗 [Website]({event['url']})"
            
            embed.add_field(
                name=event['name'],
                value=field_value,
                inline=False
            )
        
        if len(matches) > 10:
            embed.set_footer(text=f"Showing 10 of {len(matches)} results")
        
        await ctx.send(embed=embed)
    
    @tasks.loop(hours=24)
    async def check_upcoming_events(self):
        """
        Background task that checks for upcoming events and posts reminders.
        Runs once per day.
        
        This is currently disabled. To enable:
        1. Uncomment the start call in __init__
        2. Set up a channel ID where reminders should be posted
        """
        # Get events happening in the next 7, 3, and 1 days
        for days_threshold in [7, 3, 1]:
            events = self.get_upcoming_events(days_ahead=1)
            events_at_threshold = [e for e in events if e['days_until'] == days_threshold]
            
            for event in events_at_threshold:
                # TODO: Configure channel ID for reminders
                # channel = self.bot.get_channel(YOUR_CHANNEL_ID)
                # if channel:
                #     embed = self.create_reminder_embed(event)
                #     await channel.send(embed=embed)
                logger.info(f"Reminder: {event['name']} in {days_threshold} days")
    
    @check_upcoming_events.before_loop
    async def before_check_events(self):
        """Wait for bot to be ready before starting the loop."""
        await self.bot.wait_until_ready()


async def setup(bot):
    """Load the EventPinger cog."""
    await bot.add_cog(EventPinger(bot))
    logger.info("EventPinger cog loaded")
