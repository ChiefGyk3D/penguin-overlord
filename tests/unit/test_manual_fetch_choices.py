# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The manual-fetch slash commands offer a fixed list of source choices.
Every choice has to be a key in the cog's own source table, otherwise the
pick returns nothing and the "no results" message KeyErrors on the name
lookup. Found while writing docs/reference/COMMANDS.md: the EU and UK
commands offered names that had drifted from their tables."""

import typing

import pytest

from cogs import eu_legislation, general_news, uk_legislation, us_legislation


@pytest.mark.parametrize('module, cog_class', [
    (us_legislation, 'USLegislation'),
    (eu_legislation, 'EULegislation'),
    (uk_legislation, 'UKLegislation'),
    (general_news, 'GeneralNews'),
])
def test_every_offered_source_exists_in_the_table(module, cog_class):
    cog = getattr(module, cog_class)
    command = next(c for c in vars(cog).values()
                   if hasattr(c, 'callback') and hasattr(c, 'name'))
    offered = set(typing.get_args(typing.get_type_hints(command.callback)['source']))
    assert offered, 'source argument should be a Literal of choices'
    assert offered <= set(module.NEWS_SOURCES), (
        f'{command.name}: offers {sorted(offered - set(module.NEWS_SOURCES))} '
        f'but the table has {sorted(module.NEWS_SOURCES)}')
