# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
Configuration management for Boon-Tube-Daemon.

Loads configuration from .env files and environment variables.
Supports multiple secret management backends.
"""

import logging
import os
from pathlib import Path
from typing import Optional, Any

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Global config instance
_config = None

# Track if .env is loaded
_env_loaded = False


def load_config(env_path: str = ".env") -> bool:
    """
    Load configuration from .env file.
    
    Args:
        env_path: Path to .env file
        
    Returns:
        True if loaded successfully
    """
    global _env_loaded
    
    if _env_loaded:
        return True
        
    env_file = Path(env_path)
    if env_file.exists():
        load_dotenv(env_file)
        logger.info(f"✓ Loaded configuration from {env_path}")
        _env_loaded = True
        return True
    else:
        logger.warning(f"⚠ Configuration file not found: {env_path}")
        return False


def get_config(section: str, key: str, default: Any = None) -> Optional[str]:
    """
    Get configuration value from Doppler or environment variables.
    
    Priority order:
    1. Doppler (if DOPPLER_TOKEN is set) - tries both simple and sectioned formats
    2. Environment variable (simple format: KEY)
    3. Environment variable (sectioned format: SECTION_KEY)
    4. Default value
    
    Supports two formats:
    1. Simple: KEY (uppercase) - e.g., CHECK_INTERVAL
    2. Sectioned: SECTION_KEY (uppercase) - e.g., SETTINGS_CHECK_INTERVAL
    
    Args:
        section: Configuration section (e.g., 'TikTok', 'YouTube', 'Settings')
        key: Configuration key (e.g., 'username', 'api_key', 'check_interval')
        default: Default value if not found
        
    Returns:
        Configuration value or default
    """
    # Build key names
    simple_key = key.upper()
    sectioned_key = f"{section}_{key}".upper()
    
    # 1. Try Doppler first (if DOPPLER_TOKEN is set)
    doppler_token = os.getenv('DOPPLER_TOKEN')
    if doppler_token:
        try:
            from dopplersdk import DopplerSDK
            
            sdk = DopplerSDK(access_token=doppler_token)
            secrets_response = sdk.secrets.list(
                project=os.getenv('DOPPLER_PROJECT'),
                config=os.getenv('DOPPLER_CONFIG', 'dev')
            )
            
            if hasattr(secrets_response, 'secrets') and secrets_response.secrets:
                # Try sectioned key first (e.g., BLUESKY_HANDLE)
                if sectioned_key in secrets_response.secrets:
                    value = secrets_response.secrets[sectioned_key].get('computed',
                            secrets_response.secrets[sectioned_key].get('raw', ''))
                    if value and not value.startswith('YOUR_'):
                        logger.debug(f"✓ Retrieved {section}.{key} from Doppler: {sectioned_key}")
                        return value
                
                # Try simple key format (e.g., CHECK_INTERVAL)
                if simple_key in secrets_response.secrets:
                    value = secrets_response.secrets[simple_key].get('computed',
                            secrets_response.secrets[simple_key].get('raw', ''))
                    if value and not value.startswith('YOUR_'):
                        logger.debug(f"✓ Retrieved {section}.{key} from Doppler: {simple_key}")
                        return value
        except ImportError:
            logger.debug("dopplersdk not installed, skipping Doppler lookup")
        except Exception as e:
            logger.debug(f"Failed to query Doppler for config: {e}")
    
    # 2. Try simple key format from env (e.g., CHECK_INTERVAL)
    value = os.getenv(simple_key)
    if value is not None:
        return value
    
    # 3. Fall back to sectioned format from env (e.g., SETTINGS_CHECK_INTERVAL)
    value = os.getenv(sectioned_key, default)
    
    if value is None:
        logger.debug(f"Config not found: {section}.{key} (tried Doppler, {simple_key}, {sectioned_key})")
    
    return value


def get_bool_config(section: str, key: str, default: bool = False) -> bool:
    """
    Get boolean configuration value.
    
    Args:
        section: Configuration section
        key: Configuration key
        default: Default boolean value
        
    Returns:
        Boolean value
    """
    value = get_config(section, key)
    
    if value is None:
        return default
        
    # Handle various boolean representations
    if isinstance(value, bool):
        return value
        
    value_lower = str(value).lower()
    return value_lower in ('true', '1', 'yes', 'on', 'enabled')


def get_int_config(section: str, key: str, default: int = 0) -> int:
    """
    Get integer configuration value.
    
    Args:
        section: Configuration section
        key: Configuration key
        default: Default integer value
        
    Returns:
        Integer value
    """
    value = get_config(section, key)
    
    if value is None:
        return default
        
    try:
        return int(value)
    except (ValueError, TypeError):
        logger.warning(f"Invalid integer value for {section}.{key}: {value}, using default: {default}")
        return default


def get_secret(section: str, key: str, default: Optional[str] = None) -> Optional[str]:
    """
    Get secret value with automatic secret manager detection.
    
    Priority order:
    1. Doppler (if DOPPLER_TOKEN is set)
    2. AWS Secrets Manager (if SECRETS_AWS_ENABLED=true)
    3. HashiCorp Vault (if SECRETS_VAULT_ENABLED=true)
    4. Environment variable (SECTION_KEY)
    5. .env file fallback
    6. Default value
    
    All secret names use the same format: SECTION_KEY (e.g., YOUTUBE_API_KEY)
    
    Args:
        section: Configuration section (e.g., 'YouTube', 'Discord')
        key: Configuration key (e.g., 'api_key', 'webhook_url')
        default: Default value if secret not found
        
    Returns:
        Secret value or default
        
    Example:
        api_key = get_secret('YouTube', 'api_key')
        # Tries: Doppler -> AWS -> Vault -> YOUTUBE_API_KEY env var -> .env -> None
    """
    env_var = f"{section}_{key}".upper()
    
    # 1. Try Doppler first (if DOPPLER_TOKEN is set)
    doppler_token = os.getenv('DOPPLER_TOKEN')
    if doppler_token:
        # First check if it's already injected as an env var (from doppler run)
        value = os.getenv(env_var)
        # Skip placeholder values
        if value and not value.startswith('YOUR_'):
            logger.debug(f"✓ Retrieved {section}.{key} from Doppler (env var)")
            return value
        
        # If not in env, fetch from Doppler API using the SDK
        try:
            from dopplersdk import DopplerSDK
            
            sdk = DopplerSDK(access_token=doppler_token)
            # Get all secrets for this project/config
            secrets_response = sdk.secrets.list(
                project=os.getenv('DOPPLER_PROJECT'),
                config=os.getenv('DOPPLER_CONFIG', 'dev')
            )
            
            # secrets is a dict of {name: {raw: ..., computed: ...}}
            if hasattr(secrets_response, 'secrets') and secrets_response.secrets:
                if env_var in secrets_response.secrets:
                    secret_data = secrets_response.secrets[env_var]
                    # Extract the computed value (or raw if computed not available)
                    value = secret_data.get('computed', secret_data.get('raw'))
                    # Skip placeholder values
                    if value and not value.startswith('YOUR_'):
                        logger.debug(f"✓ Retrieved {section}.{key} from Doppler (SDK)")
                        return value
        except ImportError:
            logger.debug("dopplersdk not installed, skipping Doppler SDK lookup")
        except Exception as e:
            logger.debug(f"Doppler SDK lookup failed: {e}")
    
    # 2. Try AWS Secrets Manager (if enabled)
    if get_bool_config('Secrets', 'aws_enabled', default=False):
        try:
            import boto3
            import json
            
            # Get the secret name for this section (e.g., boon-tube/youtube, boon-tube/discord)
            secret_name = get_config('Secrets', 'aws_secret_name', default='boon-tube')
            
            client = boto3.client('secretsmanager')
            response = client.get_secret_value(SecretId=f"{secret_name}/{section.lower()}")
            
            if 'SecretString' in response:
                secret_dict = json.loads(response['SecretString'])
                # Try exact key match first
                if key in secret_dict:
                    value = secret_dict[key]
                    if value and not value.startswith('YOUR_'):
                        logger.debug(f"✓ Retrieved {section}.{key} from AWS Secrets Manager")
                        return value
                # Try uppercase key (for consistency)
                if key.upper() in secret_dict:
                    value = secret_dict[key.upper()]
                    if value and not value.startswith('YOUR_'):
                        logger.debug(f"✓ Retrieved {section}.{key} from AWS Secrets Manager")
                        return value
                # Try the full env var name
                if env_var in secret_dict:
                    value = secret_dict[env_var]
                    if value and not value.startswith('YOUR_'):
                        logger.debug(f"✓ Retrieved {section}.{key} from AWS Secrets Manager")
                        return value
        except ImportError:
            logger.debug("boto3 not installed, skipping AWS Secrets Manager")
        except Exception as e:
            logger.debug(f"AWS Secrets Manager lookup failed: {e}")
    
    # 3. Try HashiCorp Vault (if enabled)
    if get_bool_config('Secrets', 'vault_enabled', default=False):
        try:
            import hvac
            
            vault_addr = get_config('Secrets', 'vault_url')
            vault_token = get_config('Secrets', 'vault_token')
            vault_path = get_config('Secrets', 'vault_path', default='secret/boon-tube')
            
            if vault_addr and vault_token:
                client = hvac.Client(url=vault_addr, token=vault_token)
                # Read from path like: secret/boon-tube/youtube
                secret = client.secrets.kv.v2.read_secret_version(
                    path=f"{vault_path}/{section.lower()}"
                )
                
                data = secret['data']['data']
                # Try exact key match first
                if key in data:
                    value = data[key]
                    if value and not value.startswith('YOUR_'):
                        logger.debug(f"✓ Retrieved {section}.{key} from HashiCorp Vault")
                        return value
                # Try uppercase key
                if key.upper() in data:
                    value = data[key.upper()]
                    if value and not value.startswith('YOUR_'):
                        logger.debug(f"✓ Retrieved {section}.{key} from HashiCorp Vault")
                        return value
                # Try the full env var name
                if env_var in data:
                    value = data[env_var]
                    if value and not value.startswith('YOUR_'):
                        logger.debug(f"✓ Retrieved {section}.{key} from HashiCorp Vault")
                        return value
        except ImportError:
            logger.debug("hvac not installed, skipping HashiCorp Vault")
        except Exception as e:
            logger.debug(f"Vault lookup failed: {e}")
    
    # 4. Fallback to environment variable or .env file
    value = get_config(section, key, default=default)
    # Skip placeholder values (common in template .env files)
    if value and not value.startswith('YOUR_'):
        logger.debug(f"✓ Retrieved {section}.{key} from environment/.env")
        return value
    
    if value and value.startswith('YOUR_'):
        logger.warning(f"⚠ Found placeholder value for {section}.{key} in .env (starts with 'YOUR_')")
    
    logger.debug(f"Secret not found: {section}.{key}")
    return default
