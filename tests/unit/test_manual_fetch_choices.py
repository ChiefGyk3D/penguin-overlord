# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The manual-fetch slash commands' `source` choices must be real source keys.

A Literal choice that is not a NEWS_SOURCES key raises KeyError the moment a
user picks it. Historical bugs: /generalnews offered 7 of its 12 keys (the
five BBC feeds were missing), /uklegislation offered 'public_bills' when the
only key is 'all_bills', and /eulegislation offered three keys that do not
exist at all.
"""

import importlib

import pytest

# (module, cog class, command name, must the choices cover every key?)
MANUAL_FETCH_COMMANDS = [
    ("general_news", "GeneralNews", "generalnews", True),
    ("uk_legislation", "UKLegislation", "uklegislation", True),
    ("eu_legislation", "EULegislation", "eulegislation", True),
    ("us_legislation", "USLegislation", "uslegislation", True),
]


def _offered_sources(cls, command_name) -> set:
    for command in cls.__cog_app_commands__:
        if command.name == command_name:
            param = command._params["source"]
            return {choice.value for choice in param.choices}
    raise AssertionError(f"{cls.__name__} has no /{command_name}")


@pytest.mark.parametrize("module_name,class_name,command_name,exhaustive", MANUAL_FETCH_COMMANDS)
def test_offered_sources_are_real_keys(module_name, class_name, command_name, exhaustive):
    module = importlib.import_module(f"cogs.{module_name}")
    cls = getattr(module, class_name)
    offered = _offered_sources(cls, command_name)
    available = set(module.NEWS_SOURCES)

    assert offered, f"/{command_name} offers no sources"
    assert offered <= available, f"/{command_name} offers keys that are not sources: {offered - available}"
    if exhaustive:
        assert offered == available, f"/{command_name} hides sources: {available - offered}"
