# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Events embeds: what members and moderators see, and the one mention
policy every post goes through."""

import types

import pytest

from utils import events_cards as cards
from utils.events_logic import load_regions


@pytest.fixture(scope='module')
def regions():
    return load_regions()


def event(**over):
    base = dict(id=12, guild_id=1, title='GrrCON', topic='cyber', start_date='2026-09-24',
                end_date='2026-09-25', date_status='confirmed', city='Grand Rapids',
                region_code='US-MI', country_code='US', scope='regional',
                url='https://grrcon.com', notes=None, status='approved', provenance='member',
                submitted_by=42, decided_by=None, decided_at=None, reject_reason=None,
                created_at='2026-09-01T12:00:00+00:00')
    base.update(over)
    return base


# -- mention policy -----------------------------------------------------------

def test_allowed_mentions_never_pings_users_or_everyone():
    role = types.SimpleNamespace(id=5, name='Michigan')
    am = cards.allowed_mentions([role])
    assert am.everyone is False and am.users is False
    assert am.roles == [role]


def test_allowed_mentions_with_no_roles_pings_nothing():
    am = cards.allowed_mentions([])
    assert am.roles == [] and am.users is False and am.everyone is False


# -- text pieces --------------------------------------------------------------

@pytest.mark.parametrize('start, end, status, expected', [
    ('2026-09-24', '2026-09-25', 'confirmed', 'Sep 24 to 25, 2026'),
    ('2026-09-12', '2026-09-12', 'confirmed', 'Sep 12, 2026'),
    ('2026-08-06', '2026-08-09', 'estimated', 'Aug 6 to 9, 2026 (estimated)'),
    ('2026-12-30', '2027-01-02', 'confirmed', 'Dec 30, 2026 to Jan 2, 2027'),
])
def test_format_dates(start, end, status, expected):
    assert cards.format_dates(event(start_date=start, end_date=end, date_status=status)) == expected


def test_location_variants(regions):
    assert cards.location(event(), regions) == 'Grand Rapids, Michigan'
    assert cards.location(event(city='Online', region_code=None, country_code=None), regions) == 'Online'
    assert cards.location(event(city='Berlin', region_code=None, country_code='DE', scope='national'),
                          regions) == 'Berlin, Germany (national)'
    assert cards.location(event(city='Las Vegas', region_code='US-NV', scope='national'),
                          regions) == 'Las Vegas, Nevada (national)'


@pytest.mark.parametrize('days, expected', [(30, 'in 30 days'), (7, 'in 7 days'), (1, 'tomorrow'), (0, 'today')])
def test_countdown(days, expected):
    assert cards.countdown(days) == expected


# -- review card --------------------------------------------------------------

def test_review_card_shows_everything_a_mod_needs(regions):
    embed = cards.review_card(event(notes='Bring a badge'), regions,
                              provenance_line='Submitted by <@42>')
    assert embed.title == 'Event #12: GrrCON'
    names = {f.name: f.value for f in embed.fields}
    assert names['When'] == 'Sep 24 to 25, 2026'
    assert names['Where'] == 'Grand Rapids, Michigan'
    assert names['Topic'] == 'Cybersecurity'
    assert names['Link'] == 'https://grrcon.com'
    assert names['Notes'] == 'Bring a badge'
    assert names['Reminder tags'] == 'Cybersecurity Events, Michigan'
    assert 'Submitted by <@42>' in embed.description
    assert embed.footer.text == 'Pending review'


def test_review_card_decided_footer(regions):
    embed = cards.review_card(event(status='rejected', reject_reason='dupe'), regions,
                              provenance_line='Submitted by <@42>',
                              decided='Rejected by <@7> at 2026-09-02 10:00 ET: dupe')
    assert embed.footer.text == 'Rejected by <@7> at 2026-09-02 10:00 ET: dupe'


def test_review_card_has_no_em_dash(regions):
    embed = cards.review_card(event(), regions, provenance_line='Imported from the calendar')
    blob = (embed.title or '') + (embed.description or '') + ''.join(f.value for f in embed.fields)
    assert '—' not in blob


# -- reminders ----------------------------------------------------------------

def test_reminder_embed_and_text(regions):
    embed = cards.reminder_embed(event(), regions, 7)
    assert embed.title == 'GrrCON in 7 days'
    assert embed.url == 'https://grrcon.com'
    assert 'Sep 24 to 25, 2026' in embed.description
    assert 'Grand Rapids, Michigan' in embed.description
    assert embed.author.name == 'Con Recon'
    text = cards.reminder_text(event(), ['<@&1>', '<@&2>'], missing=['Michigan'])
    assert text.startswith('<@&1> <@&2>')
    assert 'Michigan' in text            # missing role named in plain text


def test_reminder_text_with_nothing_to_mention_is_plain(regions):
    assert cards.reminder_text(event(), [], missing=[]) == 'Upcoming event'


def test_cancelled_reminder_says_so(regions):
    embed = cards.reminder_embed(event(status='cancelled', reject_reason='venue lost'), regions, 0)
    assert embed.title.startswith('Cancelled: GrrCON')
    assert 'venue lost' in embed.description


def test_changed_reminder_is_marked_updated(regions):
    embed = cards.reminder_embed(event(), regions, 12, changed=True)
    assert embed.title == 'Updated: GrrCON in 12 days'


# -- lists and digest ---------------------------------------------------------

def test_list_embed_pages_and_strikes_cancelled(regions):
    rows = [event(), event(id=13, title='Ontario Hamfest', topic='ham', start_date='2026-09-12',
                           end_date='2026-09-12', city='Milton', region_code='CA-ON',
                           country_code='CA', status='cancelled')]
    embed = cards.list_embed(rows, regions, today='2026-09-03', page=1, pages=3, heading='Next 90 days')
    assert embed.title == 'Next 90 days'
    assert embed.footer.text == 'Page 1 of 3'
    assert '~~Ontario Hamfest~~' in embed.description
    assert '**GrrCON**' in embed.description and 'in 21 days' in embed.description
    assert '—' not in embed.description


def test_list_embed_empty(regions):
    embed = cards.list_embed([], regions, today='2026-09-03', page=1, pages=1, heading='Next 90 days')
    assert 'Nothing' in embed.description


def test_digest_embed_groups_by_week(regions):
    rows = [event(start_date='2026-09-08', end_date='2026-09-08'),
            event(id=14, title='Later', start_date='2026-09-30', end_date='2026-09-30')]
    embed = cards.digest_embed(rows, regions, today='2026-09-07')
    assert embed.title == 'Con Recon: this month'
    assert 'GrrCON' in embed.description and 'Later' in embed.description
    assert embed.description.index('GrrCON') < embed.description.index('Later')


def test_mine_lines(regions):
    text = cards.mine_lines([event(status='pending'), event(id=9, status='rejected', reject_reason='dupe')])
    assert '#12' in text and 'pending' in text
    assert '#9' in text and 'rejected (dupe)' in text


# -- Hacker Tracker link -------------------------------------------------------

def ht_event(**over):
    base = dict(provenance='hackertracker', source_url='https://hackertracker.app/DEFCON34',
               source_note='ht:DEFCON34', url='https://defcon.org')
    base.update(over)
    return event(**base)


def test_source_link_only_for_hackertracker_rows():
    assert cards.source_link(ht_event()) == 'On Hacker Tracker: https://hackertracker.app/DEFCON34'
    assert cards.source_link(event(source_url='https://example.com')) is None
    assert cards.source_link(ht_event(source_url=None)) is None


def test_review_card_link_field_carries_both_links(regions):
    embed = cards.review_card(ht_event(), regions, provenance_line='Found on Hacker Tracker')
    link = next(f for f in embed.fields if f.name == 'Link')
    assert link.value == 'https://defcon.org\nOn Hacker Tracker: https://hackertracker.app/DEFCON34'
    plain = cards.review_card(event(), regions, provenance_line='x')
    assert 'Hacker Tracker' not in next(f for f in plain.fields if f.name == 'Link').value


def test_reminder_embed_ends_with_the_listing_link(regions):
    embed = cards.reminder_embed(ht_event(), regions, 7)
    assert embed.description.splitlines()[-1] == '[On Hacker Tracker](https://hackertracker.app/DEFCON34)'
    assert embed.url == 'https://defcon.org'
    assert 'Hacker Tracker' not in cards.reminder_embed(event(), regions, 7).description


def test_mismatch_embed_names_both_date_pairs_and_the_edit_command():
    embed = cards.mismatch_embed(ht_event(id=12), ht_start='2026-08-05', ht_end='2026-08-09',
                                 source_url='https://hackertracker.app/DEFCON34')
    assert embed.title == 'Hacker Tracker disagrees on #12: GrrCON'
    assert 'Sep 24 to 25, 2026' in embed.description
    assert '2026-08-05' in embed.description and '2026-08-09' in embed.description
    assert '/events edit 12' in embed.description
    assert 'https://hackertracker.app/DEFCON34' in embed.description
    assert embed.author.name == 'Con Recon'


def test_list_embed_line_carries_the_hacker_tracker_link(regions):
    embed = cards.list_embed([ht_event()], regions, today='2026-09-03', page=1, pages=1, heading='Next 90 days')
    assert embed.description.endswith('[On Hacker Tracker](<https://hackertracker.app/DEFCON34>)')
    assert '<https://defcon.org> [On Hacker Tracker]' in embed.description


def test_list_embed_line_omits_the_link_for_non_hackertracker_rows(regions):
    embed = cards.list_embed([event()], regions, today='2026-09-03', page=1, pages=1, heading='Next 90 days')
    assert 'Hacker Tracker' not in embed.description
