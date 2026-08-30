# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""How long someone has been here, and what that earns them.

Moderation uses tiers to decide who gets a context check instead of an
automatic flag; the newcomer helper uses them to decide who gets a friendly
pointer to the resources channel. Two features asking the same question
deserve one answer, so this lives here rather than in either cog.

    new      -> joined within MEMBER_DAYS (default 30)
    member   -> past MEMBER_DAYS
    veteran  -> past VETERAN_DAYS (default 365)
    trusted  -> holds a configured staff role, whatever their tenure
    creator  -> holds a configured creator role (outranks trusted)

An unknown join date reads as `new`: the strict answer for moderation, and
a harmless one for a welcome message.
"""

import discord

TIERS = ('new', 'member', 'veteran', 'trusted', 'creator')


def trust_tier(member, *, member_days: int = 30, veteran_days: int = 365,
               trusted_roles=frozenset(), creator_roles=frozenset()) -> str:
    """Tier for a guild member. Roles outrank tenure; creator outranks trusted."""
    role_ids = {r.id for r in getattr(member, 'roles', [])}
    if role_ids & set(creator_roles):
        return 'creator'
    if role_ids & set(trusted_roles):
        return 'trusted'

    joined = getattr(member, 'joined_at', None)
    if joined is None:
        return 'new'
    days = (discord.utils.utcnow() - joined).days
    if days >= veteran_days:
        return 'veteran'
    if days >= member_days:
        return 'member'
    return 'new'
