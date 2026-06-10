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

    # --- Legacy root-path inheritance ---
    # Historically umtk_root_movies / umtk_root_tv were top-level keys. They
    # now live per-instance and as dedicated trending_root_* keys. When a
    # legacy value is present and a destination is unset, copy it in memory
    # so deployed configs keep working without rewriting the YAML file.
    legacy_root_movies = config.get('umtk_root_movies')
    legacy_root_tv = config.get('umtk_root_tv')

    if legacy_root_movies:
        for inst in config.get('radarr_instances', []) or []:
            if not inst.get('umtk_root'):
                inst['umtk_root'] = legacy_root_movies
        if not config.get('trending_root_movies'):
            config['trending_root_movies'] = legacy_root_movies

    if legacy_root_tv:
        for inst in config.get('sonarr_instances', []) or []:
            if not inst.get('umtk_root'):
                inst['umtk_root'] = legacy_root_tv
        if not config.get('trending_root_tv'):
            config['trending_root_tv'] = legacy_root_tv

    config.setdefault('instance_output_mode', 'combined')
    return config


# Backwards-compatible "REQUESTED" trending overlay blocks.
TRENDING_REQUESTED_SOURCES = {
    'backdrop_trending_movies_requested': 'backdrop_upcoming_movies_released',
    'text_trending_movies_requested': 'text_upcoming_movies_released',
    'backdrop_trending_shows_requested': 'backdrop_upcoming_shows_aired',
    'text_trending_shows_requested': 'text_upcoming_shows_aired',
}

TRENDING_REQUESTED_HEADERS = {
    'backdrop_trending_movies_requested':
        '################################################################################\n'
        '##########              TRENDING MOVIES OVERLAY REQUESTED:            ##########\n'
        '################################################################################',
    'backdrop_trending_shows_requested':
        '################################################################################\n'
        '##########              TRENDING SHOWS OVERLAY REQUESTED:             ##########\n'
        '################################################################################',
}


def ensure_trending_requested_blocks(config):
    if config is None:
        return []

    added = []
    for new_key, source_key in TRENDING_REQUESTED_SOURCES.items():
        if new_key in config and config.get(new_key):
            continue
        source = config.get(source_key)
        if isinstance(source, dict) and source:
            config[new_key] = deepcopy(source)
            added.append(new_key)
    return added


def _append_blocks_to_config(file_path, config, keys):
    """Append the given top-level blocks to config.yml as YAML text, preserving
    all existing comments/formatting. Best-effort: never raises."""
    try:
        lines = ['']
        for key in keys:
            header = TRENDING_REQUESTED_HEADERS.get(key)
            if header:
                lines.append(header)
            block_yaml = yaml.safe_dump(
                {key: config[key]}, default_flow_style=False, sort_keys=False, allow_unicode=True
            )
            lines.append(block_yaml.rstrip('\n'))
            lines.append('')
        with open(file_path, 'a', encoding='utf-8') as f:
            f.write('\n'.join(lines) + '\n')
    except Exception as e:
        print(f"{ORANGE}Warning: could not persist new trending overlay blocks to config: {e}{RESET}")


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
        config = normalize_instances(config)
        added = ensure_trending_requested_blocks(config)
        if added:
            _append_blocks_to_config(file_path, config, added)
        return config
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