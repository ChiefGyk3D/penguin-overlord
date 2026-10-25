# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The one definition of "this value is a placeholder, not a real setting".

Every place that reads a secret or a setting (utils/config.py, the Doppler
and Vault backends in utils/secrets.py) goes through `is_placeholder`, so
`.env.example` leftovers behave the same everywhere: the value is treated as
unset, and a required secret refuses to start.

A value is a placeholder when, after trimming and ignoring case, it is:
  - empty
  - `your_*`, `changeme*`, `xxx*` or `dp.st.your*`
  - exactly `example`, or `placeholder*`
  - wrapped in angle brackets (`<token>`), except a Discord mention such as
    `<@123>`, `<#123>` or `<@&123>`, which is a real value.
"""

import re

_PREFIXES = ('your_', 'changeme', 'xxx', 'dp.st.your', 'placeholder')
_EXACT = frozenset({'example'})
_ANGLE = re.compile(r'<[^<>]*>')
_MENTION = re.compile(r'<[#@][!&]?\d+>')


def is_placeholder(value) -> bool:
    if value is None:
        return True
    text = str(value).strip().lower()
    if not text:
        return True
    if text in _EXACT or text.startswith(_PREFIXES):
        return True
    return bool(_ANGLE.fullmatch(text)) and not _MENTION.fullmatch(text)
