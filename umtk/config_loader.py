"""
Configuration loading and management for UMTK
"""

import os
import sys
import yaml
from pathlib import Path
from copy import deepcopy

from .constants import (
    GREEN, ORANGE, RED, RESET,
    DEFAULT_LOCALIZATION
)


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
            return yaml.safe_load(file)
    except FileNotFoundError:
        print(f"Config file '{file_path}' not found.")
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