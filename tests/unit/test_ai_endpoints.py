# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tests for ai/endpoints.py.

`/mod status` posts into a Discord channel. Anything these functions let
through is published to everyone in it, so the assertions below are about
what must NOT appear.
"""

from ai.endpoints import describe_endpoint, describe_provider_status, scrub_addresses


def test_private_addresses_collapse_to_rfc1918():
    for endpoint in (
        'http://192.168.214.10:11434',
        '192.168.213.13',
        '10.20.30.40:11434',
        'http://172.16.4.4/api',
        '127.0.0.1:11434',
        'localhost',
        'http://[::1]:11434',
        '169.254.1.1',
        '100.64.9.9',            # CGNAT / Tailscale
    ):
        assert describe_endpoint(endpoint) == 'RFC1918', endpoint


def test_public_ip_literals_are_withheld_entirely():
    # Note: 203.0.113.0/24 and friends are documentation ranges, which
    # ipaddress classifies as private — real routable addresses here.
    for endpoint in ('http://93.184.216.34:11434', '8.8.8.8', '1.1.1.1:443'):
        described = describe_endpoint(endpoint)
        assert described == 'remote host'
        assert '93.184' not in described and '8.8' not in described


def test_known_services_are_named():
    assert describe_endpoint('https://api.openai.com/v1') == 'OpenAI'
    assert describe_endpoint('https://api.anthropic.com') == 'Claude'
    assert describe_endpoint('https://generativelanguage.googleapis.com') == 'Gemini'
    assert describe_endpoint('https://api.moonshot.ai/v1') == 'Kimi'


def test_unknown_public_hostnames_keep_their_domain():
    # A public API's domain is already public, and naming it is useful.
    assert describe_endpoint('https://llm.example.com:8443/v1') == 'llm.example.com'


def test_provider_status_never_names_a_host():
    line = describe_provider_status('Ollama', {
        'http://192.168.214.10:11434': True,
        'http://192.168.214.10:11435': False,
    })
    assert '192.168' not in line
    assert line == 'Ollama: RFC1918 (1/2 up)'


def test_provider_status_single_endpoint_reads_up_or_down():
    assert describe_provider_status(
        'Ollama', {'http://10.0.0.5:11434': True}) == 'Ollama: RFC1918 (up)'
    assert describe_provider_status(
        'Ollama', {'http://10.0.0.5:11434': False}) == 'Ollama: RFC1918 (down)'


def test_provider_status_with_nothing_configured():
    assert describe_provider_status('Gemini', {}) == 'Gemini: not configured'


def test_scrub_addresses_cleans_error_text():
    # The exact shape of a live aiohttp failure, which would otherwise be
    # quoted verbatim into an alert embed.
    text = 'Cannot connect to host 192.168.214.10:11434 ssl:default'
    scrubbed = scrub_addresses(text)
    assert '192.168.214.10' not in scrubbed
    assert 'RFC1918' in scrubbed


def test_scrub_addresses_leaves_ordinary_text_alone():
    text = 'second opinion (gemma4:12b): the phrase is a known antisemitic trope'
    assert scrub_addresses(text) == text


def test_empty_and_missing_endpoints_do_not_crash():
    assert describe_endpoint('') == 'unknown'
    assert describe_endpoint(None) == 'unknown'
    assert scrub_addresses('') == ''
