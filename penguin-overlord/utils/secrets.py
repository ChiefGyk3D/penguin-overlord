# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Secrets management for Doppler, AWS Secrets Manager, and HashiCorp Vault.

Lookup priority in get_secret():
    1. Doppler (auto-detected via DOPPLER_TOKEN)
    2. AWS Secrets Manager / Vault (via SECRETS_MANAGER=aws|vault)
    3. Plain environment variables / .env

Backend SDKs (dopplersdk, boto3, hvac) are imported lazily so only the
backend actually in use needs to be installed.

Doppler responses are cached in-process with a TTL (DOPPLER_CACHE_TTL
seconds, default 300) — previously every get_secret() call constructed a
fresh SDK client and downloaded the full secret list, one API round-trip
per lookup.
"""

import os
import json
import logging
import threading
import time

logger = logging.getLogger(__name__)

DEFAULT_DOPPLER_PROJECT = 'penguin-overlord'
DEFAULT_DOPPLER_CONFIG = 'prd'

# ---------------------------------------------------------------------------
# Doppler cache
# ---------------------------------------------------------------------------

_doppler_cache_lock = threading.Lock()
_doppler_cache = {}  # (project, config) -> (fetched_at, {KEY: value})


def _doppler_cache_ttl() -> float:
    try:
        return float(os.getenv('DOPPLER_CACHE_TTL', '300'))
    except ValueError:
        return 300.0


def _fetch_doppler_secrets(project: str, config: str):
    """Fetch and flatten all secrets for a Doppler project/config, cached with a TTL.

    Returns a dict of {KEY: value} or None when Doppler is unavailable.
    """
    doppler_token = os.getenv('DOPPLER_TOKEN')
    if not doppler_token:
        return None

    now = time.monotonic()
    cache_key = (project, config)
    with _doppler_cache_lock:
        cached = _doppler_cache.get(cache_key)
        if cached and now - cached[0] < _doppler_cache_ttl():
            return cached[1]

    try:
        from dopplersdk import DopplerSDK
    except ImportError:
        logger.error("DOPPLER_TOKEN is set but the dopplersdk package is not installed")
        return None

    try:
        sdk = DopplerSDK()
        sdk.set_access_token(doppler_token)
        response = sdk.secrets.list(project=project, config=config)
        secrets = {}
        if hasattr(response, 'secrets'):
            for key, value in response.secrets.items():
                secrets[key] = value.get('computed', value.get('raw', ''))
        logger.debug(f"Doppler fetch ok: {len(secrets)} secrets ({project}/{config})")
        with _doppler_cache_lock:
            _doppler_cache[cache_key] = (now, secrets)
        return secrets
    except Exception as e:
        logger.error(f"Failed to fetch Doppler secrets: {type(e).__name__}")
        return None


def clear_doppler_cache():
    """Drop the in-process Doppler cache (mainly for tests and admin reloads)."""
    with _doppler_cache_lock:
        _doppler_cache.clear()


# ---------------------------------------------------------------------------
# Backend loaders (public API preserved)
# ---------------------------------------------------------------------------

def load_secrets_from_aws(secret_name):
    """
    Load secrets from AWS Secrets Manager.

    Args:
        secret_name: Name of the secret in AWS Secrets Manager

    Returns:
        Dict of secrets or empty dict on error
    """
    try:
        import boto3
    except ImportError:
        logger.error("SECRETS_MANAGER=aws but the boto3 package is not installed")
        return {}
    try:
        client = boto3.client('secretsmanager')
        response = client.get_secret_value(SecretId=secret_name)
        secrets = json.loads(response['SecretString'])
        logger.debug("Successfully loaded AWS secret")
        return secrets
    except Exception as e:
        logger.error(f"Failed to load AWS secret: {type(e).__name__}")
        return {}


def load_secrets_from_vault(secret_path):
    """
    Load secrets from HashiCorp Vault.

    Args:
        secret_path: Path to the secret in Vault

    Returns:
        Dict of secrets or empty dict on error
    """
    try:
        import hvac
    except ImportError:
        logger.error("SECRETS_MANAGER=vault but the hvac package is not installed")
        return {}
    try:
        vault_url = os.getenv('SECRETS_VAULT_URL')
        vault_token = os.getenv('SECRETS_VAULT_TOKEN')

        if not vault_url or not vault_token:
            logger.error("Vault URL or token not configured")
            return {}

        client = hvac.Client(url=vault_url, token=vault_token)
        if not client.is_authenticated():
            logger.error("Vault authentication failed")
            return {}

        response = client.secrets.kv.v2.read_secret_version(path=secret_path)
        secrets = response['data']['data']
        logger.debug("Successfully loaded Vault secret")
        return secrets
    except Exception as e:
        logger.error(f"Failed to load Vault secret: {type(e).__name__}")
        return {}


def load_secrets_from_doppler(secret_name):
    """
    Load secrets from Doppler by name prefix.

    Args:
        secret_name: Name prefix for secrets in Doppler (e.g., 'discord')

    Returns:
        Dict of {suffix: value} (e.g., {'bot_token': ...} for DISCORD_BOT_TOKEN)
        or empty dict on error
    """
    project = os.getenv('DOPPLER_PROJECT', DEFAULT_DOPPLER_PROJECT)
    config = os.getenv('DOPPLER_CONFIG', DEFAULT_DOPPLER_CONFIG)
    secrets = _fetch_doppler_secrets(project, config)
    if not secrets:
        return {}

    prefix = secret_name.upper() + '_'
    return {
        key[len(prefix):].lower(): value
        for key, value in secrets.items()
        if key.upper().startswith(prefix)
    }


def get_secret(platform, key, secret_name_env=None, secret_path_env=None, doppler_secret_env=None):
    """
    Get a secret value with priority:
    1. Secrets manager (Doppler/AWS/Vault) - HIGHEST PRIORITY if credentials exist
    2. Environment variable (.env file) - FALLBACK
    3. None if not found

    This ensures production secrets in secrets managers override .env defaults.

    Args:
        platform: Platform/section name (e.g., 'DISCORD', 'NEWS')
        key: Secret key (e.g., 'BOT_TOKEN', 'OWNER_ID')
        secret_name_env: AWS Secrets Manager env var name
        secret_path_env: HashiCorp Vault env var name
        doppler_secret_env: unused, kept for call-site compatibility

    Returns:
        Secret value or None if not found
    """
    try:
        env_key = f"{platform.upper()}_{key.upper()}"

        # Priority 1: Doppler (auto-detected via DOPPLER_TOKEN, cached)
        doppler_secrets = _fetch_doppler_secrets(
            os.getenv('DOPPLER_PROJECT', DEFAULT_DOPPLER_PROJECT),
            os.getenv('DOPPLER_CONFIG', DEFAULT_DOPPLER_CONFIG),
        )
        if doppler_secrets:
            # Platform-prefixed key first (e.g., DISCORD_BOT_TOKEN), then bare key
            for candidate in (env_key, key.upper()):
                value = doppler_secrets.get(candidate)
                if value:
                    logger.debug(f"Found secret in Doppler: {candidate}")
                    return value

        # AWS / Vault via SECRETS_MANAGER
        secret_manager = os.getenv('SECRETS_MANAGER', 'none').lower()

        if secret_manager == 'aws' and secret_name_env:
            secret_name = os.getenv(secret_name_env)
            if secret_name:
                secret_value = load_secrets_from_aws(secret_name).get(key)
                if secret_value:
                    return secret_value

        elif secret_manager == 'vault' and secret_path_env:
            secret_path = os.getenv(secret_path_env)
            if secret_path:
                secret_value = load_secrets_from_vault(secret_path).get(key)
                if secret_value:
                    return secret_value

        # Priority 2: Fallback to environment variable (.env file)
        env_value = os.getenv(env_key)
        if env_value:
            return env_value

        return None

    except Exception as e:
        logger.error(f"Error getting secret for {platform}.{key}: {type(e).__name__}")
        return None
