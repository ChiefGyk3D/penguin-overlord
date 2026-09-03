# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The categorized help is hand-written text, so it drifts: it was telling
members to type /cybersecuritynews when the command is /cybersecurity, and
quoting a news count from 2025. Every command the help pages mention must
be one the cogs register, and the headline numbers must match the code."""

import re
from pathlib import Path

from cogs import help_categorized

COGS_DIR = Path(help_categorized.__file__).parent

# name='x' / name="x" inside command decorators, plus bare @hybrid_command
# on a `def x` (rare here, but cheap to cover).
_NAMED = re.compile(r"""\.(?:hybrid_command|command|group)\(\s*name\s*=\s*['"]([a-z0-9_-]+)['"]""")
_GROUPS = re.compile(r"""app_commands\.Group\(\s*name\s*=\s*['"]([a-z0-9_-]+)['"]""")
_PAGES = ['overview', 'comics', 'news', 'ham', 'aviation', 'sigint',
          'events', 'utilities', 'admin']


def registered_names() -> set:
    names = set()
    for path in COGS_DIR.glob('*.py'):
        text = path.read_text(encoding='utf-8')
        names.update(_NAMED.findall(text))
        names.update(_GROUPS.findall(text))
    return names


def mentioned_commands(embed) -> set:
    text = (embed.description or '') + ''.join(
        f.name + f.value for f in embed.fields)
    return set(re.findall(r'`[/!]([a-z][a-z0-9_-]*)', text))


def test_every_command_the_help_mentions_exists():
    known = registered_names()
    assert 'cybersecurity' in known and 'help' in known   # sanity on the scan
    missing = {}
    for page in _PAGES:
        embed = help_categorized.get_category_embed(page)
        bad = sorted(mentioned_commands(embed) - known)
        if bad:
            missing[page] = bad
    assert not missing, f'help mentions commands that do not exist: {missing}'


def test_news_page_counts_match_the_news_manager():
    overview = help_categorized.get_category_embed('overview').description
    news = help_categorized.get_category_embed('news')
    assert '11 categories' in overview
    assert '8 categories' not in overview
    assert '11 categories' in (news.description or '')
    joined = ''.join(f.value for f in news.fields)
    for expected in ('KEV', 'UK Legislation', 'Vendor Alerts'):
        assert expected in joined, f'{expected} missing from the news help page'
