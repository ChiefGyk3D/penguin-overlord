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
from utils.config import load_config


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


# -- config passed in, not read from the environment -------------------------

def _ai_settings(**env):
    return load_config({'DISCORD_BOT_TOKEN': 'x', **env}).ai


def test_feature_config_comes_from_the_settings_passed_in(ai_env):
    ai_env.setenv('AI_ENABLED', 'false')             # env says off
    settings = _ai_settings(AI_ENABLED='true', AI_CVE_ENABLED='true',
                            AI_CVE_MODEL='qwen3:14b', AI_CVE_TEMPERATURE='0.1',
                            AI_DEFAULT_MODEL='llama3.2')
    cve = ai_config.get_feature_config('cve', settings)
    assert cve.enabled is True and cve.model == 'qwen3:14b'
    assert cve.temperature == 0.1
    news = ai_config.get_feature_config('news', settings)
    assert news.enabled is False and news.model == 'llama3.2'
    assert ai_config.ai_enabled(settings) is True
    assert ai_config.default_ollama_host(settings) == 'http://localhost:11434'


def test_moderation_is_local_only_whatever_the_settings_say():
    settings = _ai_settings(AI_ENABLED='true', AI_MODERATION_ENABLED='true',
                            AI_GEMINI_FALLBACK='true',
                            AI_MODERATION_GEMINI_FALLBACK='true')
    assert ai_config.get_feature_config('moderation', settings).gemini_fallback is False


def test_runtime_config_comes_from_the_settings_passed_in(ai_env):
    ai_env.setenv('AI_MAX_RETRIES', '9')              # env says nine
    settings = _ai_settings(AI_MAX_RETRIES='4', AI_GEMINI_MODEL='gemini-9')
    runtime = ai_config.get_runtime_config(settings)
    assert runtime.max_retries == 4 and runtime.gemini_model == 'gemini-9'


def test_gemini_key_is_revealed_only_where_it_is_used():
    settings = _ai_settings(GEMINI_API_KEY='AIza-fake-key')
    assert ai_config.gemini_api_key(settings) == 'AIza-fake-key'
    # ...and the config object itself will not print it
    assert 'AIza' not in repr(settings)


async def test_manager_uses_the_settings_it_was_built_with(ai_env):
    ai_env.setenv('AI_ENABLED', 'false')
    settings = _ai_settings(AI_ENABLED='true', AI_ROASTING_ENABLED='true',
                            AI_MAX_RETRIES='0', AI_RETRY_DELAY_BASE='0')
    provider = StubProvider(["Your kernel has commitment issues 🐧"])
    manager = AIManager(settings)

    async def fake_provider_for(host):
        return provider

    ai_env.setattr(manager, '_provider_for', fake_provider_for)
    assert manager.ai_settings is settings
    assert manager.status()['enabled'] is True
    assert await manager.generate('roasting', 'roast me') == \
        "Your kernel has commitment issues 🐧"


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


# -- per-feature endpoint, num_ctx and keep_alive ------------------------------

def test_num_ctx_and_keep_alive_unset_by_default():
    cfg = ai_config.get_feature_config('moderation', _ai_settings())
    assert cfg.num_ctx is None and cfg.keep_alive is None


def test_guard_can_have_its_own_endpoint_and_context():
    settings = _ai_settings(
        AI_ENABLED='true', AI_MODERATION_ENABLED='true',
        AI_DEFAULT_OLLAMA_HOST='http://big:11434', AI_DEFAULT_NUM_CTX='65536',
        AI_DEFAULT_KEEP_ALIVE='-1',
        AI_MODERATION_OLLAMA_HOST='http://small:11435',
        AI_MODERATION_NUM_CTX='8192')
    guard = ai_config.get_feature_config('moderation', settings)
    roast = ai_config.get_feature_config('roasting', settings)
    assert (guard.host, guard.num_ctx) == ('http://small:11435', 8192)
    assert (roast.host, roast.num_ctx) == ('http://big:11434', 65536)
    # keep_alive inherits the default when the feature does not override it
    assert guard.keep_alive == roast.keep_alive == '-1'


class RecordingProvider(StubProvider):
    def __init__(self, responses, host):
        super().__init__(responses)
        self.host = host
        self.kwargs = []

    async def generate(self, **kwargs):
        self.kwargs.append(kwargs)
        return await super().generate(**kwargs)


async def test_manager_routes_each_feature_to_its_own_endpoint(ai_env):
    settings = _ai_settings(
        AI_ENABLED='true', AI_MODERATION_ENABLED='true', AI_ROASTING_ENABLED='true',
        AI_MAX_RETRIES='0', AI_DEFAULT_OLLAMA_HOST='http://big:11434',
        AI_DEFAULT_NUM_CTX='65536', AI_MODERATION_OLLAMA_HOST='http://small:11435',
        AI_MODERATION_NUM_CTX='8192', AI_MODERATION_MODEL='llama-guard3:8b')
    manager = AIManager(settings)
    providers = {}

    async def fake_provider_for(host):
        return providers.setdefault(host, RecordingProvider(['safe'] * 4, host))

    ai_env.setattr(manager, '_provider_for', fake_provider_for)
    await manager.generate('moderation', 'hi', raw=True)
    await manager.generate('roasting', 'hi', raw=True)

    assert set(providers) == {'http://small:11435', 'http://big:11434'}
    guard = providers['http://small:11435'].kwargs[0]
    roast = providers['http://big:11434'].kwargs[0]
    assert guard['model'] == 'llama-guard3:8b' and guard['num_ctx'] == 8192
    assert roast['num_ctx'] == 65536


async def test_down_guard_endpoint_never_spills_onto_the_backbone(ai_env):
    """Guard down means model-unavailable (callers fail soft); it must not be
    retried on the default endpoint, where it would evict the backbone."""
    settings = _ai_settings(
        AI_ENABLED='true', AI_MODERATION_ENABLED='true', AI_MAX_RETRIES='0',
        AI_DEFAULT_OLLAMA_HOST='http://big:11434',
        AI_MODERATION_OLLAMA_HOST='http://small:11435')
    manager = AIManager(settings)
    asked = []

    async def fake_provider_for(host):
        asked.append(host)
        provider = StubProvider([])
        provider.connected = False
        return provider

    ai_env.setattr(manager, '_provider_for', fake_provider_for)
    assert await manager.generate('moderation', 'hi', raw=True) is None
    assert asked == ['http://small:11435']


async def test_generate_host_and_num_ctx_override_the_feature(ai_env):
    settings = _ai_settings(
        AI_ENABLED='true', AI_MODERATION_ENABLED='true', AI_MAX_RETRIES='0',
        AI_MODERATION_OLLAMA_HOST='http://small:11435', AI_MODERATION_NUM_CTX='8192')
    manager = AIManager(settings)
    provider = RecordingProvider(['ok'], 'http://big:11434')
    asked = []

    async def fake_provider_for(host):
        asked.append(host)
        return provider

    ai_env.setattr(manager, '_provider_for', fake_provider_for)
    await manager.generate('moderation', 'hi', raw=True, model='gemma4:12b',
                           host='http://big:11434', num_ctx=65536)
    assert asked == ['http://big:11434']
    assert provider.kwargs[0]['num_ctx'] == 65536
