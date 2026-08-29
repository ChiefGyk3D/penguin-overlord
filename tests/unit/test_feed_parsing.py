# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Feed XML parsing must reject entity-expansion attacks (billion laughs)
while still parsing normal RSS — the cogs previously used the stdlib parser
directly on remote feed bytes."""

from unittest.mock import MagicMock

import defusedxml
import pytest

from cogs import us_legislation

BILLION_LAUGHS = """<?xml version="1.0"?>
<!DOCTYPE lolz [
 <!ENTITY lol "lol">
 <!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">
 <!ENTITY lol3 "&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;">
 <!ENTITY lol4 "&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;">
]>
<rss version="2.0"><channel><item>
  <title>&lol4;</title>
  <link>https://example.gov/evil</link>
</item></channel></rss>
"""


class FakeResponse:
    def __init__(self, text, status=200):
        self._text = text
        self.status = status

    async def text(self):
        return self._text

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


class FakeSession:
    def __init__(self, text):
        self._text = text

    def get(self, url):
        return FakeResponse(self._text)


async def test_billion_laughs_is_rejected(tmp_data_dir):
    cog = us_legislation.USLegislation.__new__(us_legislation.USLegislation)
    cog.bot = MagicMock()
    cog.session = FakeSession(BILLION_LAUGHS)
    cog.state_file = str(tmp_data_dir / "state.json")
    cog.posted_items = {}
    # Must not expand entities; the item is dropped, not detonated.
    result = await cog._fetch_rss_feed("house_floor")
    assert result is None


def test_direct_fromstring_raises_on_entities():
    import defusedxml.ElementTree as DET
    with pytest.raises(defusedxml.EntitiesForbidden):
        DET.fromstring(BILLION_LAUGHS)
