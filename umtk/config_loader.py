"""
Configuration loading and management for UMTK
"""

import os
import sys
import shutil
import yaml
from pathlib import Path
from copy import deepcopy

from .constants import (
    GREEN, ORANGE, RED, RESET,
    DEFAULT_LOCALIZATION
)


def normalize_instances(config):
    """Convert legacy flat radarr_*/sonarr_* keys into radarr_instances/sonarr_instances lists.

    If the new list keys already exist the config is returned as-is.
    This provides full backward compatibility: users can keep the old flat
    format in their config.yml forever and it will be transparently converted
    at load time without rewriting the file on disk.
    """
    if config is None:
        return config

    # --- Radarr ---
    if 'radarr_instances' not in config and config.get('radarr_url'):
        config['radarr_instances'] = [{
            'name': 'Radarr',
            'url': config.pop('radarr_url'),
            'api_key': config.pop('radarr_api_key', ''),
            'timeout': config.pop('radarr_timeout', 90),
            'exclude_tags': config.pop('exclude_radarr_tags', ''),
        }]

    # --- Sonarr ---
    if 'sonarr_instances' not in config and config.get('sonarr_url'):
        config['sonarr_instances'] = [{
            'name': 'Sonarr',
            'url': config.pop('sonarr_url'),
            'api_key': config.pop('sonarr_api_key', ''),
            'timeout': config.pop('sonarr_timeout', 90),
            'exclude_tags': config.pop('exclude_sonarr_tags', ''),
        }]

    config.setdefault('instance_output_mode', 'combined')
    return config


def load_config(file_path=None):
    """Load configuration from YAML file"""
    if file_path is None:
        # Check if running in Docker
        if os.environ.get('DOCKER') == 'true':
            file_path = Path('/app/config/config.yml')
        else:
            file_path = Path(__file__).parent.parent / 'config' / 'config.yml'

    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            config = yaml.safe_load(file)
            return normalize_instances(config)
    except FileNotFoundError:
        # Try to auto-copy from sample file
        sample_path = Path(str(file_path)).parent / 'config.sample.yml'
        if sample_path.exists():
            print(f"{ORANGE}Config file '{file_path}' not found. Copying from sample...{RESET}")
            shutil.copy2(str(sample_path), str(file_path))
            print(f"{GREEN}Created '{file_path}' from sample. Please edit it with your settings.{RESET}")
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    return normalize_instances(yaml.safe_load(f))
            except Exception as e:
                print(f"Error reading copied config file: {e}")
                sys.exit(1)
        else:
            print(f"Config file '{file_path}' not found and no sample available.")
            sys.exit(1)
    except yaml.YAMLError as e:
        print(f"Error parsing YAML config file: {e}")
        sys.exit(1)


def load_localization(file_path=None):
    """Load localization settings with English defaults"""
    if file_path is None:
        # Check if running in Docker
        if os.environ.get('DOCKER') == 'true':
            file_path = Path('/app/config/localization.yml')
        else:
            file_path = Path(__file__).parent.parent / 'config' / 'localization.yml'
    
    # Start with a deep copy of defaults
    localization = deepcopy(DEFAULT_LOCALIZATION)
    
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            user_localization = yaml.safe_load(file)
            
            if user_localization:
                # Deep merge user localization with defaults
                for key in localization:
                    if key in user_localization:
                        if isinstance(localization[key], dict):
                            localization[key].update(user_localization[key])
                        else:
                            localization[key] = user_localization[key]
                            
    except FileNotFoundError:
        # Silently use defaults if file doesn't exist
        pass
    except yaml.YAMLError as e:
        print(f"{ORANGE}Warning: Error parsing localization file, using English defaults: {e}{RESET}")
    except Exception as e:
        print(f"{ORANGE}Warning: Could not load localization file, using English defaults: {e}{RESET}")
    
    return localization


def get_cookies_path():
    """Get the path to cookies.txt if it exists"""
    if os.environ.get('DOCKER') == 'true':
        cookies_folder = Path('/cookies')
    else:
        cookies_folder = Path(__file__).parent.parent / 'cookies'
    
    cookies_file = cookies_folder / 'cookies.txt'
    
    if cookies_file.exists() and cookies_file.is_file():
        return str(cookies_file)
    
    return None


def get_kometa_folder():
    """Get the path to the kometa output folder"""
    if os.environ.get('DOCKER') == 'true':
        return Path('/app') / "kometa"
    else:
        return Path(__file__).parent.parent / "kometa"


def get_video_folder():
    """Get the path to the video folder"""
    if os.environ.get('DOCKER') == 'true':
        return Path('/video')
    else:
        return Path(__file__).parent.parent / 'video'