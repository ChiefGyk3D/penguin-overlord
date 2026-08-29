# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tests for ai/config.py and ai/manager.py: opt-in defaults, moderation
privacy floor, provider fallback, and queue bounding."""

import asyncio

import pytest

from ai import config as ai_config
from ai.manager import AIManager
from ai.queue import BoundedRequestQueue


@pytest.fixture(autouse=True)
def ai_env(monkeypatch):
    """Clean AI-related env for each test."""
    for var in list(__import__('os').environ):
        if var.startswith('AI_') or var.startswith('OLLAMA') or var.startswith('GEMINI') or var == 'ARCH_BANTER_LLM':
            monkeypatch.delenv(var, raising=False)
    monkeypatch.delenv('DOPPLER_TOKEN', raising=False)
    yield monkeypatch


# -- config -----------------------------------------------------------------

def test_ai_disabled_by_default():
    assert ai_config.ai_enabled() is False
    assert ai_config.get_feature_config('roasting').enabled is False


def test_feature_needs_both_flags(ai_env):
    ai_env.setenv('AI_ENABLED', 'true')
    assert ai_config.get_feature_config('roasting').enabled is False
    ai_env.setenv('AI_ROASTING_ENABLED', 'true')
    assert ai_config.get_feature_config('roasting').enabled is True


def test_moderation_never_falls_back_to_gemini(ai_env):
    ai_env.setenv('AI_ENABLED', 'true')
    ai_env.setenv('AI_MODERATION_ENABLED', 'true')
    ai_env.setenv('AI_GEMINI_FALLBACK', 'true')
    ai_env.setenv('AI_MODERATION_GEMINI_FALLBACK', 'true')
    cfg = ai_config.get_feature_config('moderation')
    assert cfg.gemini_fallback is False
    # ...but a non-sensitive feature honors the flag
    assert ai_config.get_feature_config('roasting').gemini_fallback is True


def test_per_feature_override_does_not_leak(ai_env):
    ai_env.setenv('AI_ENABLED', 'true')
    ai_env.setenv('AI_DEFAULT_MODEL', 'llama3.2')
    ai_env.setenv('AI_CVE_MODEL', 'qwen3:14b')
    ai_env.setenv('AI_CVE_TEMPERATURE', '0.1')
    cve = ai_config.get_feature_config('cve')
    news = ai_config.get_feature_config('news')
    assert cve.model == 'qwen3:14b' and cve.temperature == 0.1
    assert news.model == 'llama3.2' and news.temperature != 0.1


def test_ollama_host_normalization(ai_env):
    ai_env.setenv('OLLAMA_HOST', '192.168.1.50')
    ai_env.setenv('OLLAMA_PORT', '11500')
    assert ai_config.default_ollama_host() == 'http://192.168.1.50:11500'
    ai_env.setenv('OLLAMA_HOST', 'https://ollama.lan:9999')
    assert ai_config.default_ollama_host() == 'https://ollama.lan:9999'


# -- manager ----------------------------------------------------------------

class StubProvider:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0
        self.connected = True

    async def generate(self, **kwargs):
        self.calls += 1
        return self.responses.pop(0) if self.responses else None


async def make_manager(monkeypatch, provider):
    manager = AIManager()

    async def fake_provider_for(host):
        return provider

    monkeypatch.setattr(manager, '_provider_for', fake_provider_for)
    return manager


async def test_generate_disabled_returns_none(ai_env):
    manager = await make_manager(ai_env, StubProvider(["hi"]))
    assert await manager.generate('roasting', 'prompt') is None


async def test_generate_happy_path(ai_env):
    ai_env.setenv('AI_ENABLED', 'true')
    ai_env.setenv('AI_ROASTING_ENABLED', 'true')
    provider = StubProvider(["Your kernel has commitment issues 🐧"])
    manager = await make_manager(ai_env, provider)
    result = await manager.generate('roasting', 'roast me')
    assert result == "Your kernel has commitment issues 🐧"


async def test_generate_blocks_denylist_output(ai_env):
    ai_env.setenv('AI_ENABLED', 'true')
    ai_env.setenv('AI_ROASTING_ENABLED', 'true')
    manager = await make_manager(ai_env, StubProvider(["you retard 🐧"]))
    assert await manager.generate('roasting', 'roast me') is None


async def test_generate_retries_then_gives_up(ai_env):
    ai_env.setenv('AI_ENABLED', 'true')
    ai_env.setenv('AI_ROASTING_ENABLED', 'true')
    ai_env.setenv('AI_MAX_RETRIES', '2')
    ai_env.setenv('AI_RETRY_DELAY_BASE', '0')
    provider = StubProvider([None, None, None])
    manager = await make_manager(ai_env, provider)
    assert await manager.generate('roasting', 'roast me') is None
    assert provider.calls == 3


# -- queue ------------------------------------------------------------------

async def test_queue_rejects_when_full():
    queue = BoundedRequestQueue(max_concurrent=1, max_pending=2, min_delay=0)
    release = asyncio.Event()

    async def slow():
        await release.wait()
        return "done"

    t1 = asyncio.create_task(queue.submit(slow))
    t2 = asyncio.create_task(queue.submit(slow))
    await asyncio.sleep(0.01)
    # Third submission exceeds max_pending and is dropped immediately
    assert await queue.submit(slow) is None
    assert queue.rejected_count == 1

    release.set()
    assert await t1 == "done"
    assert await t2 == "done"


async def test_queue_propagates_exceptions():
    queue = BoundedRequestQueue(max_concurrent=1, max_pending=5, min_delay=0)

    async def boom():
        raise ValueError("real bug")

    with pytest.raises(ValueError):
        await queue.submit(boom)
