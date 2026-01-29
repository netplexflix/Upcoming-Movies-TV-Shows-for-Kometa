"""
Utility functions for UMTK
"""

import os
import re
import requests
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .constants import GREEN, ORANGE, RED, BLUE, RESET, VERSION


def get_user_info():
    """Get current user info for debugging permissions"""
    try:
        return f"{os.getuid()}:{os.getgid()}"
    except AttributeError:
        import getpass
        return f"Windows User: {getpass.getuser()}"


def get_file_owner(path):
    """Get file/directory owner info"""
    try:
        stat_info = path.stat()
        return f"{stat_info.st_uid}:{stat_info.st_gid}"
    except AttributeError:
        return "Windows File"


def check_for_updates():
    """Check GitHub for newer versions of UMTK"""
    print(f"Checking for updates to UMTK {VERSION}...")
    
    try:
        response = requests.get(
            "https://api.github.com/repos/netplexflix/Upcoming-Movies-TV-Shows-for-Kometa/releases/latest",
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
            print(f"{ORANGE}A newer version of UMTK is available: {latest_version}{RESET}")
            print(f"{ORANGE}Download: {latest_release.get('html_url', '')}{RESET}")
            print(f"{ORANGE}Release notes: {latest_release.get('body', 'No release notes available')}{RESET}\n")
        else:
            print(f"{GREEN}You are running the latest version of UMTK.{RESET}\n")
    except Exception as e:
        print(f"{ORANGE}Could not check for updates: {str(e)}{RESET}\n")


def convert_utc_to_local(utc_date_str, utc_offset):
    """Convert UTC datetime to local time with offset"""
    if not utc_date_str:
        return None
        
    clean_date_str = utc_date_str.replace('Z', '')
    utc_date = datetime.fromisoformat(clean_date_str).replace(tzinfo=timezone.utc)
    local_date = utc_date + timedelta(hours=utc_offset)
    return local_date


def sanitize_filename(filename):
    """Sanitize filename/folder name for Windows compatibility"""
    replacements = {
        ':': ' -',
        '/': '-',
        '\\': '-',
        '?': '',
        '*': '',
        '"': "'",
        '<': '(',
        '>': ')',
        '|': '-',
    }
    
    sanitized = filename
    for invalid_char, replacement in replacements.items():
        sanitized = sanitized.replace(invalid_char, replacement)
    
    sanitized = sanitized.rstrip('. ')
    return sanitized


def sanitize_sort_title(title):
    """Sanitize title for sort_title by removing special characters"""
    # Remove special characters but keep spaces
    sanitized = re.sub(r'[:\'"()\[\]{}<>|/\\?*]', '', title)
    # Clean up multiple spaces
    sanitized = ' '.join(sanitized.split())
    return sanitized.strip()


def check_yt_dlp_installed():
    """Check if yt-dlp is installed and accessible"""
    try:
        result = subprocess.run(['yt-dlp', '--version'], capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            version = result.stdout.strip()
            print(f"{GREEN}yt-dlp found: {version}{RESET}")
            return True
        else:
            print(f"{RED}yt-dlp command not working properly{RESET}")
            return False
    except FileNotFoundError:
        print(f"{RED}yt-dlp command not found. Please ensure yt-dlp is properly installed.{RESET}")
        print(f"{ORANGE}Install with: pip install yt-dlp{RESET}")
        return False
    except subprocess.TimeoutExpired:
        print(f"{RED}yt-dlp command timed out{RESET}")
        return False
    except Exception as e:
        print(f"{RED}Error checking yt-dlp: {str(e)}{RESET}")
        return False


def check_video_file(video_folder):
    """Check if UMTK video file exists"""
    if not video_folder.exists():
        print(f"{RED}Video folder not found. Please create a 'video' folder.{RESET}")
        return False
    
    source_files = list(video_folder.glob('UMTK.*'))
    if not source_files:
        print(f"{RED}UMTK video file not found in video folder. Please add a video file named 'UMTK' (with any extension).{RESET}")
        return False
    
    source_file = source_files[0]
    size_mb = source_file.stat().st_size / (1024 * 1024)
    print(f"{GREEN}Found video file: {source_file.name} ({size_mb:.1f} MB){RESET}")
    return True


def get_tag_ids_from_names(api_url, api_key, tag_names, timeout=90, debug=False):
    """Convert tag names to tag IDs"""
    if not tag_names:
        return []
    
    try:
        url = f"{api_url}/tag"
        headers = {"X-Api-Key": api_key}
        response = requests.get(url, headers=headers, timeout=timeout)
        response.raise_for_status()
        
        all_tags = response.json()
        tag_name_to_id = {tag['label'].lower(): tag['id'] for tag in all_tags}
        
        tag_ids = []
        for tag_name in tag_names:
            tag_name_lower = tag_name.strip().lower()
            if tag_name_lower in tag_name_to_id:
                tag_ids.append(tag_name_to_id[tag_name_lower])
                if debug:
                    print(f"{BLUE}[DEBUG] Found tag '{tag_name}' with ID {tag_name_to_id[tag_name_lower]}{RESET}")
            elif debug:
                print(f"{ORANGE}[DEBUG] Tag '{tag_name}' not found{RESET}")
        
        return tag_ids
    except requests.exceptions.RequestException as e:
        if debug:
            print(f"{ORANGE}[DEBUG] Error fetching tags: {str(e)}{RESET}")
        return []


def get_next_sort_by(output_file):
    """Get the next sort_by value in rotation"""
    import yaml
    
    sort_options = ["rank.desc", "usort.desc", "rank.asc", "usort.asc"]
    current_sort = None
    
    try:
        with open(output_file, 'r', encoding='utf-8') as f:
            existing_data = yaml.safe_load(f)
            if existing_data and 'collections' in existing_data:
                for collection_name, collection_data in existing_data['collections'].items():
                    if 'mdblist_list' in collection_data:
                        current_sort = collection_data['mdblist_list'].get('sort_by')
                        break
    except FileNotFoundError:
        pass
    except Exception:
        pass
    
    if current_sort in sort_options:
        current_index = sort_options.index(current_sort)
        next_index = (current_index + 1) % len(sort_options)
        return sort_options[next_index]
    else:
        return sort_options[0]