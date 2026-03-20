"""Utility functions for TSSK"""

import requests
from datetime import datetime, timedelta, timezone

from umtk.constants import VERSION
from .constants import GREEN, ORANGE, RESET


def check_for_updates():
    """Check GitHub for newer versions of TSSK"""
    print(f"Checking for updates to TSSK {VERSION}...")
    
    try:
        response = requests.get(
            "https://api.github.com/repos/netplexflix/TV-show-status-for-Kometa/releases/latest",
            timeout=10
        )
        response.raise_for_status()
        
        latest_release = response.json()
        latest_version = latest_release.get("tag_name", "").lstrip("v")
        
        def parse_version(version_str):
            return tuple(map(int, version_str.split('.')))
        
        current_version_tuple = parse_version(VERSION)
        latest_version_tuple = parse_version(latest_version)
        
        if latest_version and latest_version_tuple > current_version_tuple:
            print(f"{ORANGE}A newer version of TSSK is available: {latest_version}{RESET}")
            print(f"{ORANGE}Download: {latest_release.get('html_url', '')}{RESET}")
            print(f"{ORANGE}Release notes: {latest_release.get('body', 'No release notes available')}{RESET}\n")
        else:
            print(f"{GREEN}You are running the latest version of TSSK.{RESET}\n")
    except Exception as e:
        print(f"{ORANGE}Could not check for updates: {str(e)}{RESET}\n")


def convert_utc_to_local(utc_date_str, utc_offset):
    """Convert UTC date string to local datetime with offset"""
    if not utc_date_str:
        return None
        
    # Remove 'Z' if present and parse the datetime
    clean_date_str = utc_date_str.replace('Z', '')
    utc_date = datetime.fromisoformat(clean_date_str).replace(tzinfo=timezone.utc)
    
    # Apply the UTC offset
    local_date = utc_date + timedelta(hours=utc_offset)
    return local_date


def debug_print(message, config):
    """Print debug messages only if debug mode is enabled"""
    if config.get('debug', False):
        print(message)


def sanitize_show_title(title):
    """Remove special characters from show title"""
    # Remove special characters: :,;.'"
    special_chars = ':,;.\'"'
    for char in special_chars:
        title = title.replace(char, '')
    return title.strip()