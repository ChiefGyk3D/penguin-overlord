# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Every cog module must import cleanly — a broken cog previously slipped
through CI because import failures were swallowed."""

import importlib
from pathlib import Path

import pytest

COGS_DIR = Path(__file__).resolve().parents[2] / "penguin-overlord" / "cogs"
COG_MODULES = sorted(
    f"cogs.{p.stem}" for p in COGS_DIR.glob("*.py") if not p.name.startswith("_")
)


@pytest.mark.parametrize("module_name", COG_MODULES)
def test_cog_imports(module_name):
    importlib.import_module(module_name)


def test_bot_module_imports():
    importlib.import_module("bot")


def test_bot_enables_members_intent():
    # The welcome greeter listens on on_member_update, which Discord only
    # delivers when the Server Members intent is enabled. Without this the
    # greeter is silent for everyone — a bug that shipped once already.
    import bot as bot_module
    instance = bot_module.PenguinOverlord()
    assert instance.intents.members is True
    assert instance.intents.message_content is True
