# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Role picker: MEE6-style self-roles as persistent select menus, one role
per exclusive panel, roles provisioned from the JSON panel definitions."""

import types

import discord
import pytest

from cogs import role_picker as rp
from cogs.role_picker import RolePicker


# -- shipped panel definitions ----------------------------------------------

def test_shipped_panels_load_and_fit_discord_limits():
    panels = rp.load_panels()
    assert set(panels) >= {'country', 'us_states', 'ca_provinces'}
    for key, panel in panels.items():
        assert panel.key == key
        assert 1 <= len(panel.groups) <= 5, key          # one action row each
        for group in panel.groups:
            assert 1 <= len(group.options) <= 25, key    # select option cap
        roles = panel.role_names()
        assert len(roles) == len(set(roles)), key        # no duplicates


def test_us_states_panel_has_fifty_states_plus_dc():
    panel = rp.load_panels()['us_states']
    assert len(panel.role_names()) == 51
    assert 'Michigan' in panel.role_names()
    assert 'District of Columbia' in panel.role_names()


def test_country_panel_leads_with_us_and_canada():
    panel = rp.load_panels()['country']
    first_two = [o.role for o in panel.groups[0].options[:2]]
    assert first_two == ['United States', 'Canada']
    assert 'International' in panel.role_names()


def test_provinces_panel_has_thirteen():
    assert len(rp.load_panels()['ca_provinces'].role_names()) == 13


# -- the pure decisions ------------------------------------------------------

def _panel():
    return rp.Panel.from_dict({
        'key': 'demo', 'title': 't', 'description': 'd', 'exclusive': True,
        'groups': [{'placeholder': 'p', 'options': [
            {'label': 'Ohio', 'role': 'Ohio'},
            {'label': 'Michigan', 'role': 'Michigan'},
        ]}],
    })


def test_missing_roles_are_the_ones_the_guild_lacks():
    assert rp.missing_roles(_panel(), {'Ohio', 'Penguins'}) == ['Michigan']


def test_choosing_a_role_swaps_out_the_old_one():
    add, remove = rp.plan_change(_panel(), {'Ohio', 'Penguins'}, ['Michigan'])
    assert add == ['Michigan'] and remove == ['Ohio']


def test_choosing_the_same_role_again_is_a_noop():
    add, remove = rp.plan_change(_panel(), {'Michigan'}, ['Michigan'])
    assert add == [] and remove == []


def test_clearing_the_menu_drops_every_panel_role():
    add, remove = rp.plan_change(_panel(), {'Michigan', 'Penguins'}, [])
    assert add == [] and remove == ['Michigan']


def test_unknown_value_is_ignored_not_granted():
    add, remove = rp.plan_change(_panel(), set(), ['Administrator'])
    assert add == [] and remove == []


# -- view construction --------------------------------------------------------

def test_view_has_one_persistent_select_per_group():
    panel = rp.load_panels()['us_states']
    view = rp.build_view(panel)
    ids = [item.custom_id for item in view.children]
    assert ids == ['rolepick:us_states:0', 'rolepick:us_states:1', 'rolepick:us_states:2']
    assert view.timeout is None
    select = view.children[0]
    assert select.min_values == 0 and select.max_values == 1
    assert len(select.options) == 17


def test_select_option_values_are_role_names_with_emoji_when_given():
    view = rp.build_view(rp.load_panels()['country'])
    first = view.children[0].options[0]
    assert first.value == 'United States' and str(first.emoji) == '🇺🇸'


# -- the cog applying a choice -------------------------------------------------

def _role(name, rid):
    return types.SimpleNamespace(name=name, id=rid, mention=f'<@&{rid}>')


def _member(roles):
    m = types.SimpleNamespace(roles=list(roles), added=[], removed=[],
                              display_name='someone')

    async def add_roles(*rs, reason=None):
        m.added.extend(r.name for r in rs)

    async def remove_roles(*rs, reason=None):
        m.removed.extend(r.name for r in rs)
    m.add_roles = add_roles
    m.remove_roles = remove_roles
    return m


def _guild(role_names):
    roles = [_role(n, 100 + i) for i, n in enumerate(role_names)]
    return types.SimpleNamespace(roles=roles)


@pytest.fixture
def cog(monkeypatch):
    monkeypatch.setenv('ROLE_PICKER_ENABLED', 'true')
    return RolePicker(types.SimpleNamespace())


async def test_apply_swaps_roles_and_reports(cog):
    panel = _panel()
    guild = _guild(['Ohio', 'Michigan', 'Penguins'])
    member = _member([guild.roles[0], guild.roles[2]])   # Ohio + Penguins
    text = await cog.apply(panel, guild, member, ['Michigan'])
    assert member.added == ['Michigan'] and member.removed == ['Ohio']
    assert 'Michigan' in text


async def test_apply_with_nothing_chosen_clears(cog):
    panel = _panel()
    guild = _guild(['Ohio', 'Michigan'])
    member = _member([guild.roles[1]])
    text = await cog.apply(panel, guild, member, [])
    assert member.removed == ['Michigan'] and member.added == []
    assert 'cleared' in text.lower() or 'removed' in text.lower()


async def test_apply_when_role_is_missing_from_guild_says_so(cog):
    panel = _panel()
    guild = _guild(['Ohio'])                  # Michigan was never provisioned
    member = _member([])
    text = await cog.apply(panel, guild, member, ['Michigan'])
    assert member.added == []
    assert 'moderator' in text.lower() or 'not set up' in text.lower()


async def test_apply_forbidden_is_a_message_not_a_crash(cog):
    panel = _panel()
    guild = _guild(['Ohio', 'Michigan'])
    member = _member([])

    async def add_roles(*rs, reason=None):
        raise discord.Forbidden(types.SimpleNamespace(status=403, reason='f'), 'nope')
    member.add_roles = add_roles
    text = await cog.apply(panel, guild, member, ['Michigan'])
    assert 'permission' in text.lower()


# -- provisioning guard --------------------------------------------------------

def test_provision_check_refuses_without_manage_roles():
    me = types.SimpleNamespace(guild_permissions=discord.Permissions(manage_roles=False),
                               top_role=types.SimpleNamespace(position=50))
    problem = rp.provision_problem(me, existing_role_count=10, needed=5)
    assert problem and 'Manage Roles' in problem


def test_provision_check_refuses_past_the_role_cap():
    me = types.SimpleNamespace(guild_permissions=discord.Permissions(manage_roles=True),
                               top_role=types.SimpleNamespace(position=50))
    problem = rp.provision_problem(me, existing_role_count=248, needed=5)
    assert problem and '250' in problem


def test_provision_check_passes_when_fine():
    me = types.SimpleNamespace(guild_permissions=discord.Permissions(manage_roles=True),
                               top_role=types.SimpleNamespace(position=50))
    assert rp.provision_problem(me, existing_role_count=80, needed=51) is None
