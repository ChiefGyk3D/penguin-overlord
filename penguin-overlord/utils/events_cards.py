# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Everything the events cog shows in Discord.

One rule lives here that every poster path must honour: member-facing
posts mention roles and nothing else. `allowed_mentions` is the only way
to build the AllowedMentions for an events post, and it pins users and
everyone to False.
"""

from datetime import date

import discord

from utils.events_logic import TOPIC_LABELS, days_until, role_names_for

COLOUR = {
    'pending': 0xF1C40F,
    'approved': 0x2ECC71,
    'rejected': 0x95A5A6,
    'cancelled': 0xE74C3C,
    'retired': 0x7F8C8D,
}


def allowed_mentions(roles) -> discord.AllowedMentions:
    """Roles only. Never users, never everyone."""
    return discord.AllowedMentions(everyone=False, users=False, roles=list(roles), replied_user=False)


def format_dates(event: dict) -> str:
    start = date.fromisoformat(event['start_date'])
    end = date.fromisoformat(event['end_date'])
    if start == end:
        text = f'{start:%b} {start.day}, {start.year}'
    elif start.year == end.year and start.month == end.month:
        text = f'{start:%b} {start.day} to {end.day}, {start.year}'
    elif start.year == end.year:
        text = f'{start:%b} {start.day} to {end:%b} {end.day}, {start.year}'
    else:
        text = f'{start:%b} {start.day}, {start.year} to {end:%b} {end.day}, {end.year}'
    if event.get('date_status') == 'estimated':
        text += ' (estimated)'
    return text


def location(event: dict, regions) -> str:
    parts = [event['city']]
    if event.get('region_code'):
        parts.append(regions.name(event['region_code']))
    elif event.get('country_code'):
        parts.append(regions.name(event['country_code']))
    text = ', '.join(p for p in parts if p)
    if event.get('scope') == 'national' and (event.get('region_code') or event.get('country_code')):
        text += ' (national)'
    return text


def countdown(days: int) -> str:
    if days <= 0:
        return 'today'
    if days == 1:
        return 'tomorrow'
    return f'in {days} days'


def source_link(event: dict) -> str | None:
    """The second link a discovered row carries: the listing it came from.
    Only Hacker Tracker rows have one today; the text names the source so
    a member knows what they are clicking."""
    if event.get('provenance') == 'hackertracker' and event.get('source_url'):
        return f"On Hacker Tracker: {event['source_url']}"
    return None


def review_card(event: dict, regions, *, provenance_line: str, decided: str | None = None) -> discord.Embed:
    embed = discord.Embed(title=f"Event #{event['id']}: {event['title']}",
                          description=provenance_line,
                          colour=COLOUR.get(event['status'], 0x95A5A6))
    embed.add_field(name='When', value=format_dates(event), inline=True)
    embed.add_field(name='Where', value=location(event, regions), inline=True)
    embed.add_field(name='Topic', value=TOPIC_LABELS[event['topic']], inline=True)
    link_value = event['url'] or 'none given'
    extra = source_link(event)
    if extra:
        link_value = f'{link_value}\n{extra}'
    embed.add_field(name='Link', value=link_value, inline=False)
    if event.get('notes'):
        embed.add_field(name='Notes', value=event['notes'][:1024], inline=False)
    # Plain names, not mentions: the review channel must never ping.
    embed.add_field(name='Reminder tags', value=', '.join(role_names_for(event, regions)) or 'none',
                    inline=False)
    embed.set_footer(text=decided or 'Pending review')
    embed.set_author(name='Con Recon')
    return embed


def reminder_embed(event: dict, regions, days: int, *, changed: bool = False) -> discord.Embed:
    cancelled = event['status'] == 'cancelled'
    if cancelled:
        title = f"Cancelled: {event['title']}"
    elif changed:
        title = f"Updated: {event['title']} {countdown(days)}"
    else:
        title = f"{event['title']} {countdown(days)}"
    lines = [format_dates(event), location(event, regions), TOPIC_LABELS[event['topic']]]
    if cancelled and event.get('reject_reason'):
        lines.append(f"Reason: {event['reject_reason']}")
    if event.get('notes'):
        lines.append('')
        lines.append(event['notes'])
    ht_url = event.get('source_url')
    if event.get('provenance') == 'hackertracker' and ht_url:
        lines.append(f"[On Hacker Tracker]({ht_url})")
    embed = discord.Embed(title=title, url=event['url'], description='\n'.join(lines),
                          colour=COLOUR['cancelled' if cancelled else 'approved'])
    embed.set_footer(text=f"Event #{event['id']}")
    embed.set_author(name='Con Recon')
    return embed


def mismatch_embed(event: dict, *, ht_start: str, ht_end: str, source_url: str) -> discord.Embed:
    """Review-channel notice, no buttons: the organizer's dates on Hacker
    Tracker differ from an approved row. Phase 2b's verify job replaces
    this with a proposal card that applies the change in one click."""
    ours = format_dates(event)
    theirs = ht_start if ht_start == ht_end else f'{ht_start} to {ht_end}'
    body = (f'Calendar: {ours}\nHacker Tracker: {theirs}\n'
            f'Check {source_url} and use `/events edit {event["id"]}` if the organizer is right.')
    embed = discord.Embed(title=f"Hacker Tracker disagrees on #{event['id']}: {event['title']}",
                          description=body, colour=COLOUR['pending'])
    embed.set_author(name='Con Recon')
    return embed


def reminder_text(event: dict, role_mentions: list, missing: list) -> str:
    """Message content above the embed: the role pings, plus the plain
    names of roles the guild is missing so the post still says who it
    was for."""
    parts = list(role_mentions) + list(missing)
    return ' '.join(parts) if parts else 'Upcoming event'


def _line(event: dict, regions, today: date) -> str:
    name = f"~~{event['title']}~~" if event['status'] == 'cancelled' else f"**{event['title']}**"
    when = format_dates(event)
    link = f" <{event['url']}>" if event.get('url') else ''
    ht_link = f" [On Hacker Tracker](<{event['source_url']}>)" if source_link(event) else ''
    return (f"{name}: {when}, {location(event, regions)} "
            f"({countdown(days_until(event['start_date'], today))}){link}{ht_link}")


def list_embed(events: list, regions, *, today: str, page: int, pages: int, heading: str) -> discord.Embed:
    day = date.fromisoformat(today)
    body = '\n'.join(_line(e, regions, day) for e in events) or 'Nothing scheduled in this window.'
    embed = discord.Embed(title=heading, description=body[:4000], colour=COLOUR['approved'])
    embed.set_footer(text=f'Page {page} of {pages}')
    embed.set_author(name='Con Recon')
    return embed


def digest_embed(events: list, regions, *, today: str) -> discord.Embed:
    day = date.fromisoformat(today)
    body = '\n'.join(_line(e, regions, day) for e in events) or 'Nothing scheduled in the next 30 days.'
    embed = discord.Embed(title='Con Recon: this month', description=body[:4000], colour=COLOUR['approved'])
    embed.set_author(name='Con Recon')
    return embed


def mine_lines(events: list) -> str:
    lines = []
    for e in events:
        state = e['status']
        if state == 'rejected' and e.get('reject_reason'):
            state = f"rejected ({e['reject_reason']})"
        lines.append(f"#{e['id']} {e['title']} ({e['start_date']}): {state}")
    return '\n'.join(lines) or 'You have not submitted any events.'
