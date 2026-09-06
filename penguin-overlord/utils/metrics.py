# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Prometheus metrics for Grafana dashboards.

Opt-in via METRICS_ENABLED=true (+ METRICS_PORT, default 9200). When
disabled — or when prometheus_client isn't installed — every metric call
is a no-op, so instrumented code never needs to check.

The /metrics endpoint doubles as the container healthcheck: it only serves
while the bot process is alive, and bot_connected/bot_gateway_latency say
whether the Discord gateway is actually up.
"""

import logging

from utils.config import load_metrics_config

logger = logging.getLogger(__name__)

# Import-time constants: cogs import this module before any of them could
# be handed a Config. The section loader is lenient (a bad METRICS_PORT
# falls back to 9200 here) because bot.py's load_config() has already
# refused to start on that same value by the time a cog imports us.
_settings = load_metrics_config()
METRICS_ENABLED = _settings.enabled
METRICS_PORT = _settings.port

try:
    from prometheus_client import Counter, Gauge, Histogram, start_http_server
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False


class _NoopMetric:
    def labels(self, *args, **kwargs):
        return self

    def inc(self, *args, **kwargs):
        pass

    def set(self, *args, **kwargs):
        pass

    def observe(self, *args, **kwargs):
        pass


if METRICS_ENABLED and PROMETHEUS_AVAILABLE:
    BOT_CONNECTED = Gauge('penguin_bot_connected', 'Whether the bot is connected to the Discord gateway')
    GATEWAY_LATENCY = Gauge('penguin_gateway_latency_seconds', 'Discord gateway heartbeat latency')
    GUILD_COUNT = Gauge('penguin_guilds', 'Number of guilds the bot is in')

    AI_REQUESTS = Counter('penguin_ai_requests_total', 'AI generation requests', ['feature', 'outcome'])
    AI_LATENCY = Histogram('penguin_ai_request_seconds', 'AI generation latency', ['feature'],
                           buckets=(0.5, 1, 2, 5, 10, 20, 30, 60))
    AI_QUEUE_DROPPED = Counter('penguin_ai_queue_dropped_total', 'AI requests dropped by the bounded queue')

    MOD_SCANS = Counter('penguin_mod_scans_total', 'Messages scanned by AI moderation')
    MOD_ALERTS = Counter('penguin_mod_alerts_total', 'Moderation alerts posted', ['category'])
    MOD_ACTIONS = Counter('penguin_mod_actions_total', 'Moderation actions executed', ['action'])
    MOD_VERDICTS = Counter('penguin_mod_verdicts_total', 'Moderator labels on alerts', ['verdict'])
    MOD_ADJUDICATIONS = Counter('penguin_mod_adjudications_total', 'Context adjudications by the second-stage model', ['kind', 'outcome'])
    MOD_ATTACK_MARKERS = Counter('penguin_mod_attack_markers_total', 'Prompt-injection and filter-evasion techniques seen in scanned messages', ['marker'])
    HELPER_REPLIES = Counter('penguin_helper_replies_total', 'Newcomer resource pointers sent')

    EVENTS_SUBMISSIONS = Counter('penguin_events_submissions_total', 'Event rows created', ['provenance'])
    EVENTS_DECISIONS = Counter('penguin_events_decisions_total', 'Moderator and sweep decisions on events', ['decision'])
    EVENTS_REMINDERS = Counter('penguin_events_reminders_total', 'Event reminders posted', ['window'])
    EVENTS_POST_ERRORS = Counter('penguin_events_post_errors_total', 'Event posts that failed to send')
    EVENTS_ROLE_MISSING = Counter('penguin_events_role_missing_total', 'Reminders sent with a role the guild lacks', ['role'])
    EVENTS_PENDING = Gauge('penguin_events_pending', 'Event submissions awaiting a moderator')
else:
    BOT_CONNECTED = GATEWAY_LATENCY = GUILD_COUNT = _NoopMetric()
    AI_REQUESTS = AI_LATENCY = AI_QUEUE_DROPPED = _NoopMetric()
    MOD_SCANS = MOD_ALERTS = MOD_ACTIONS = MOD_VERDICTS = MOD_ADJUDICATIONS = _NoopMetric()
    MOD_ATTACK_MARKERS = HELPER_REPLIES = _NoopMetric()

    EVENTS_SUBMISSIONS = EVENTS_DECISIONS = EVENTS_REMINDERS = _NoopMetric()
    EVENTS_POST_ERRORS = EVENTS_ROLE_MISSING = EVENTS_PENDING = _NoopMetric()


_server_started = False


def start_metrics_server() -> bool:
    """Start the /metrics HTTP endpoint once. Returns True when serving."""
    global _server_started
    if not METRICS_ENABLED:
        return False
    if not PROMETHEUS_AVAILABLE:
        logger.error('METRICS_ENABLED=true but prometheus_client is not installed')
        return False
    if _server_started:
        return True
    try:
        start_http_server(METRICS_PORT)
        _server_started = True
        logger.info(f'✓ Prometheus metrics on :{METRICS_PORT}/metrics')
        return True
    except OSError as e:
        logger.error(f'Could not start metrics server on :{METRICS_PORT}: {e}')
        return False
