# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Describing AI endpoints without publishing infrastructure.

`/mod status` posts into a Discord channel, and a channel is not a private
place: it has moderators, screenshots, and whoever gets invited next month.
An answer like "192.168.214.10:11434 (up)" hands all of them the address of
an inference host.

What a moderator actually needs is which provider is serving them and
whether it is up. So a private address collapses to `RFC1918`, a public one
is withheld entirely, and a public API keeps its hostname — `api.openai.com`
is not a secret and naming it is genuinely informative.
"""

import ipaddress
import re
from urllib.parse import urlparse

# Hostname -> the name people call the service. Anything not listed falls
# back to its hostname, which is safe: a public API's domain is public.
_KNOWN_SERVICES = {
    'generativelanguage.googleapis.com': 'Gemini',
    'api.openai.com': 'OpenAI',
    'api.anthropic.com': 'Claude',
    'api.moonshot.cn': 'Kimi',
    'api.moonshot.ai': 'Kimi',
    'api.deepseek.com': 'DeepSeek',
    'api.mistral.ai': 'Mistral',
    'api.groq.com': 'Groq',
    'openrouter.ai': 'OpenRouter',
}


def _host_only(endpoint: str) -> str:
    """Hostname from a URL, a host:port pair, or a bare host."""
    text = (endpoint or '').strip()
    if not text:
        return ''
    if '://' not in text:
        text = f'//{text}'
    parsed = urlparse(text)
    return parsed.hostname or ''


def describe_endpoint(endpoint: str) -> str:
    """A publishable description of where a model is served from.

    Private/loopback/link-local/CGNAT -> 'RFC1918' (a local address, and
    saying which one adds nothing for a moderator). Public IP literal ->
    'remote host' with the address withheld. Hostname -> the service name if
    we know it, otherwise the hostname itself.
    """
    host = _host_only(endpoint)
    if not host:
        return 'unknown'

    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        lowered = host.lower()
        if lowered in ('localhost', 'localhost.localdomain'):
            return 'RFC1918'
        return _KNOWN_SERVICES.get(lowered, lowered)

    if ip.is_loopback or ip.is_private or ip.is_link_local:
        return 'RFC1918'
    if ip in ipaddress.ip_network('100.64.0.0/10'):   # CGNAT / Tailscale
        return 'RFC1918'
    return 'remote host'


def describe_provider_status(provider: str, endpoints: dict) -> str:
    """One status line per provider, with no addresses in it.

    `endpoints` maps endpoint -> connected. Identical descriptions collapse,
    so two private Ollama hosts read 'Ollama: RFC1918 (2 up)' rather than
    naming either of them.
    """
    if not endpoints:
        return f'{provider}: not configured'

    grouped: dict[str, list[bool]] = {}
    for endpoint, connected in endpoints.items():
        grouped.setdefault(describe_endpoint(endpoint), []).append(bool(connected))

    parts = []
    for description, states in grouped.items():
        up = sum(states)
        if len(states) == 1:
            parts.append(f"{description} ({'up' if up else 'down'})")
        else:
            parts.append(f'{description} ({up}/{len(states)} up)')
    return f"{provider}: {', '.join(parts)}"


def scrub_addresses(text: str) -> str:
    """Last line of defence for free-form text headed to Discord.

    Model reasoning and error strings quote whatever they were given, and an
    exception like 'Cannot connect to host 192.168.214.10:11434' would carry
    the address into an alert embed.
    """
    if not text:
        return text
    return re.sub(
        r'\b(?:\d{1,3}\.){3}\d{1,3}\b(?::\d+)?',
        lambda m: describe_endpoint(m.group(0).split(':')[0]),
        text,
    )
