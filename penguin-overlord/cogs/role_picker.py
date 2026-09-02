# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Role Picker — MEE6-style self-roles, done with select menus.

MEE6's reaction-role model predates Discord components: 20 reactions per
message, one emoji per role, and mapping fifty states onto emoji is a
chore nobody finishes. This cog posts persistent PANELS instead: an embed
plus one select menu per group of up to 25 options. The selects carry their
identity in a fixed custom_id, so they survive restarts with no state to
store (the same DynamicItem pattern the moderation review buttons use).

A panel is a JSON file in assets/role_panels/ (see country.json):

    key          short id, used in custom_ids and slash-command choices
    title        embed title
    description  embed body, in the operator's voice
    exclusive    true: picking one role in the panel removes the others
    groups[]     placeholder + options[] of {label, role, emoji?}

The shipped panels are country (US and Canada first, then common
countries, then International), us_states (50 + DC across three menus),
and ca_provinces. Roles are named plainly ("Michigan", "Ontario") so the
events system can resolve a region to a role by name.

Provisioning: `/roles post <panel> [#channel]` creates any missing roles
(not hoisted, not mentionable by members: only the bot pings them) and
posts the panel. It refuses, and says why, when the bot lacks Manage Roles
or the guild would pass Discord's 250-role cap.

Configuration:
    ROLE_PICKER_ENABLED=false   master switch (commands and menus both)
"""

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

logger = logging.getLogger(__name__)

_PANELS_DIR = Path(__file__).resolve().parent.parent / 'assets' / 'role_panels'
ROLE_CAP = 250        # Discord's hard limit per guild
ROLE_WARN = 200       # warn early; other bots and humans make roles too


@dataclass
class Option:
    label: str
    role: str
    emoji: str | None = None


@dataclass
class Group:
    placeholder: str
    options: list = field(default_factory=list)


@dataclass
class Panel:
    key: str
    title: str
    description: str
    exclusive: bool
    groups: list = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> 'Panel':
        groups = [Group(g['placeholder'],
                        [Option(o['label'], o['role'], o.get('emoji'))
                         for o in g['options']])
                  for g in data['groups']]
        return cls(data['key'], data['title'], data['description'],
                   bool(data.get('exclusive', True)), groups)

    def role_names(self) -> list:
        return [o.role for g in self.groups for o in g.options]


def load_panels(directory: Path = _PANELS_DIR) -> dict:
    panels = {}
    for path in sorted(directory.glob('*.json')):
        try:
            panel = Panel.from_dict(json.loads(path.read_text(encoding='utf-8')))
        except (OSError, ValueError, KeyError) as e:
            logger.error('Role panel %s is unreadable: %s', path.name, e)
            continue
        panels[panel.key] = panel
    return panels


def missing_roles(panel: Panel, existing: set) -> list:
    return [name for name in panel.role_names() if name not in existing]


def plan_change(panel: Panel, member_roles: set, chosen: list) -> tuple:
    """Pure: which panel roles to add and remove for a member's choice.
    Unknown values are dropped (the API could never send one, but a stale
    panel definition could), and an empty choice clears the panel."""
    valid = set(panel.role_names())
    wanted = [v for v in chosen if v in valid]
    if panel.exclusive:
        wanted = wanted[:1]
    add = [name for name in wanted if name not in member_roles]
    if panel.exclusive or not wanted:
        remove = [name for name in panel.role_names()
                  if name in member_roles and name not in wanted]
    else:
        remove = []
    return add, remove


def provision_problem(me, existing_role_count: int, needed: int) -> str | None:
    if not me.guild_permissions.manage_roles:
        return 'I need the Manage Roles permission to create and assign these roles.'
    if existing_role_count + needed > ROLE_CAP:
        return (f'This would put the server at {existing_role_count + needed} roles; '
                f'Discord caps a server at {ROLE_CAP}.')
    return None


class PanelSelect(discord.ui.DynamicItem[discord.ui.Select],
                  template=r'rolepick:(?P<panel>[a-z0-9_]+):(?P<group>[0-9]+)'):
    """One dropdown of a panel. Everything it needs is in the custom_id and
    the panel file, so a restart or a redeploy never orphans a menu."""

    def __init__(self, panel: Panel, index: int):
        group = panel.groups[index]
        options = [discord.SelectOption(label=o.label, value=o.role, emoji=o.emoji)
                   for o in group.options]
        super().__init__(discord.ui.Select(
            placeholder=group.placeholder, min_values=0, max_values=1,
            options=options, custom_id=f'rolepick:{panel.key}:{index}'))
        self.panel = panel
        self.index = index

    # DynamicItem wraps the real Select in .item; expose what tests and
    # callers read.
    @property
    def options(self):
        return self.item.options

    @property
    def min_values(self):
        return self.item.min_values

    @property
    def max_values(self):
        return self.item.max_values

    @classmethod
    async def from_custom_id(cls, interaction, item, match):
        panels = load_panels()
        panel = panels.get(match['panel'])
        index = int(match['group'])
        if panel is None or index >= len(panel.groups):
            raise ValueError(f'unknown role panel {match["panel"]}:{index}')
        return cls(panel, index)

    async def callback(self, interaction: discord.Interaction):
        cog = interaction.client.get_cog('RolePicker')
        if cog is None or not cog.enabled:
            await interaction.response.send_message(
                'Role picking is switched off right now.', ephemeral=True)
            return
        values = list(interaction.data.get('values') or [])
        text = await cog.apply(self.panel, interaction.guild, interaction.user, values)
        await interaction.response.send_message(text, ephemeral=True)


def build_view(panel: Panel) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    for index in range(len(panel.groups)):
        view.add_item(PanelSelect(panel, index))
    return view


def build_embed(panel: Panel) -> discord.Embed:
    return discord.Embed(title=panel.title, description=panel.description,
                         color=0x5865F2)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ('1', 'true', 'yes', 'on')


class RolePicker(commands.Cog):
    """Self-service roles from JSON-defined panels."""

    def __init__(self, bot):
        self.bot = bot
        self.enabled = _env_bool('ROLE_PICKER_ENABLED', False)

    async def cog_load(self):
        self.bot.add_dynamic_items(PanelSelect)
        panels = load_panels()
        logger.info('Role picker %s: %d panels (%s)',
                    'active' if self.enabled else 'disabled', len(panels),
                    ', '.join(sorted(panels)) or 'none')

    # -------------------------------------------------------------- apply

    async def apply(self, panel: Panel, guild, member, chosen: list) -> str:
        """Carry out a member's menu choice; returns the ephemeral reply."""
        by_name = {r.name: r for r in guild.roles}
        have = {r.name for r in member.roles}
        add, remove = plan_change(panel, have, chosen)

        missing = [n for n in add if n not in by_name]
        if missing:
            logger.error('Role panel %s: role(s) %s not provisioned', panel.key, missing)
            return (f'The {missing[0]} role is not set up yet. Poke a moderator '
                    f'and ask them to run /roles post {panel.key}.')

        reason = f'Role picker: {panel.key}'
        try:
            if remove:
                await member.remove_roles(
                    *[by_name[n] for n in remove if n in by_name], reason=reason)
            if add:
                await member.add_roles(*[by_name[n] for n in add], reason=reason)
        except discord.Forbidden:
            logger.error('Role panel %s: Forbidden changing roles for %s',
                         panel.key, member.display_name)
            return ('I do not have permission to change that role. My role '
                    'probably sits below it; tell a moderator.')
        except discord.HTTPException as e:
            logger.warning('Role panel %s: HTTP %s', panel.key, e.status)
            return 'Discord did not take that change. Try again in a moment.'

        logger.info('Role panel %s: %s +%s -%s', panel.key, member.display_name,
                    add, remove)
        if add:
            return f'You are now **{add[0]}**.' + (
                f' (Swapped out {", ".join(remove)}.)' if remove else '')
        if remove:
            return f'Cleared: {", ".join(remove)} removed.'
        return 'No change; you already had that.'

    # ----------------------------------------------------------- commands

    roles = app_commands.Group(
        name='roles', description='Self-role panels',
        default_permissions=discord.Permissions(manage_roles=True))

    @roles.command(name='list', description='List the role panels the bot knows')
    async def roles_list(self, interaction: discord.Interaction):
        panels = load_panels()
        if not panels:
            await interaction.response.send_message('No panels found.', ephemeral=True)
            return
        existing = {r.name for r in interaction.guild.roles}
        lines = []
        for key, panel in sorted(panels.items()):
            missing = missing_roles(panel, existing)
            lines.append(f'`{key}`: {panel.title}; {len(panel.role_names())} roles, '
                         f'{len(missing)} not yet created')
        await interaction.response.send_message('\n'.join(lines), ephemeral=True)

    @roles.command(name='post', description='Create any missing roles for a panel and post it')
    @app_commands.describe(panel='Panel key (see /roles list)',
                           channel='Where to post; defaults to here')
    async def roles_post(self, interaction: discord.Interaction, panel: str,
                         channel: discord.TextChannel | None = None):
        if not self.enabled:
            await interaction.response.send_message(
                'ROLE_PICKER_ENABLED is off; menus would not respond.', ephemeral=True)
            return
        panels = load_panels()
        definition = panels.get(panel)
        if definition is None:
            await interaction.response.send_message(
                f'No panel called `{panel}`. Known: {", ".join(sorted(panels))}',
                ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        existing = {r.name for r in guild.roles}
        missing = missing_roles(definition, existing)
        problem = provision_problem(guild.me, len(guild.roles), len(missing))
        if problem:
            await interaction.followup.send(problem, ephemeral=True)
            return

        created = []
        try:
            for name in missing:
                await guild.create_role(name=name, hoist=False, mentionable=False,
                                        reason=f'Role picker panel {definition.key}')
                created.append(name)
        except discord.HTTPException as e:
            await interaction.followup.send(
                f'Created {len(created)} of {len(missing)} roles, then Discord '
                f'refused: {e.text or type(e).__name__}. Fix and rerun; it only '
                f'creates what is missing.', ephemeral=True)
            return

        target = channel or interaction.channel
        try:
            await target.send(embed=build_embed(definition), view=build_view(definition))
        except discord.Forbidden:
            await interaction.followup.send(
                f'Roles are ready but I cannot post in {target.mention}.', ephemeral=True)
            return

        note = ''
        if len(guild.roles) + len(created) >= ROLE_WARN:
            note = (f'\nHeads up: the server is at about {len(guild.roles) + len(created)} '
                    f'roles; Discord stops at {ROLE_CAP}.')
        await interaction.followup.send(
            f'Posted `{definition.key}` in {target.mention}; created {len(created)} '
            f'role(s).{note}', ephemeral=True)

    @roles_post.autocomplete('panel')
    async def _panel_autocomplete(self, interaction: discord.Interaction, current: str):
        return [app_commands.Choice(name=k, value=k)
                for k in sorted(load_panels()) if current.lower() in k][:25]


async def setup(bot):
    await bot.add_cog(RolePicker(bot))
    logger.info('RolePicker cog loaded')
