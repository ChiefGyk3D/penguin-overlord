# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The gateway-latency gauge must skip NaN (no heartbeat ack yet)."""

import types

from cogs import metrics as metrics_cog


class _Gauge:
    def __init__(self):
        self.values = []

    def set(self, value):
        self.values.append(value)


async def _beat(monkeypatch, latency):
    gauge = _Gauge()
    monkeypatch.setattr(metrics_cog.metrics, 'BOT_CONNECTED', _Gauge())
    monkeypatch.setattr(metrics_cog.metrics, 'GATEWAY_LATENCY', gauge)
    monkeypatch.setattr(metrics_cog.metrics, 'GUILD_COUNT', _Gauge())
    bot = types.SimpleNamespace(
        latency=latency, guilds=[], is_ready=lambda: True, is_closed=lambda: False,
    )
    cog = object.__new__(metrics_cog.Metrics)
    cog.bot = bot
    await metrics_cog.Metrics.heartbeat.coro(cog)
    return gauge.values


async def test_nan_latency_is_not_recorded(monkeypatch):
    assert await _beat(monkeypatch, float('nan')) == []


async def test_real_latency_is_recorded(monkeypatch):
    assert await _beat(monkeypatch, 0.042) == [0.042]
