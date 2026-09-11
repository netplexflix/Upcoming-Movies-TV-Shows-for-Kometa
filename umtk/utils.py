"""
Utility functions for UMTK
"""

import os
import re
import time
import requests
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path, PureWindowsPath

from .constants import GREEN, ORANGE, RED, BLUE, RESET, VERSION


def request_with_retry(method, url, *, retries=2, backoff=2.0, **kwargs):
    """requests.request() with retry on transient ConnectionError/Timeout.

    HTTP 4xx/5xx responses are NOT retried — only network-level failures.
    Default: 2 retries (3 total attempts) with linear backoff (2s, 4s).
    """
    for attempt in range(retries + 1):
        try:
            return requests.request(method, url, **kwargs)
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            if attempt < retries:
                wait = backoff * (attempt + 1)
                print(f"{ORANGE}Connection issue ({type(e).__name__}), retrying in {wait:.0f}s (attempt {attempt + 2}/{retries + 1})...{RESET}", flush=True)
                time.sleep(wait)
            else:
                raise


def dedupe_by_key(items_lists, key):
    """Merge multiple lists, keeping first occurrence per key value.

    Args:
        items_lists: iterable of lists to merge
        key: dict key to deduplicate on (e.g. 'tvdbId', 'tmdbId')

    Returns:
        Single merged list with duplicates removed.
    """
    seen = set()
    result = []
    for items in items_lists:
        for item in items:
            id_val = item.get(key)
            if id_val and id_val not in seen:
                seen.add(id_val)
                result.append(item)
            elif not id_val:
                result.append(item)
    return result


def sanitize_instance_name(name):
    """Convert an instance name to a safe filename suffix.

    Replaces spaces with underscores and strips everything else
    that isn't alphanumeric or underscore.
    """
    return re.sub(r'[^a-zA-Z0-9_]', '', name.replace(' ', '_'))


def audit_overlay_block_keys(kometa_folder):
    """Warn about overlay block keys that appear in more than one generated file.

    Kometa merges every overlay file applied to a library into one namespace, so a
    duplicated block key means one definition silently overwrites the other and those
    items lose their overlay. Advisory only: files mapped to different libraries can
    legitimately share a key, so this reports rather than fails.
    """
    import yaml

    key_to_files = {}
    for path in sorted(Path(kometa_folder).glob("*OVERLAYS*.yml")):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        overlays = data.get("overlays")
        if not isinstance(overlays, dict):
            continue
        for key in overlays:
            key_to_files.setdefault(key, []).append(path.name)

    duplicates = {k: v for k, v in key_to_files.items() if len(v) > 1}
    if not duplicates:
        return duplicates

    print(f"\n{ORANGE}Overlay block keys appearing in more than one file:{RESET}")
    for key, files in sorted(duplicates.items()):
        print(f"{ORANGE}  - '{key}' appears in {len(files)} files: {', '.join(files)}{RESET}")
    print(f"{ORANGE}  If these files are applied to the same Plex library, Kometa will "
          f"use only one definition and the rest will be ignored.{RESET}")
    return duplicates


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


# Plex's TV Series agent reads an ID hint from the show folder name:
# "Show (2020) {tvdb-123456}" (also tmdb-/imdb-). Sonarr's own folder naming can
# produce the same tags, so detection has to cover all three.
FOLDER_ID_RE = re.compile(r'\s*\{(tvdb|tmdb|imdb)-([^}]+)\}', re.IGNORECASE)


def legacy_show_folder_name(show):
    """Folder name for a show's content as UMTK named it before the ID tag.

    Sonarr's own folder name wins when the show is in a library; otherwise the
    name is derived from the title and year. Existing installs still have
    folders with these names, so content creation reuses them and cleanup
    recognizes them (see resolve_show_dir).
    """
    show_path = show.get('path')
    if show_path:
        return PureWindowsPath(show_path).name

    show_title = show.get('title', 'Unknown')
    show_year = show.get('year', '')
    # Some titles already carry a disambiguating year ("Little House on the
    # Prairie (2026)") - appending it again would produce "... (2026) (2026)".
    if show_year and not re.search(r'\(\d{4}\)\s*$', show_title):
        return sanitize_filename(f"{show_title} ({show_year})")
    return sanitize_filename(show_title)


def show_id_tag(show):
    """'{tvdb-123}' style folder tag for a show, or '' when it has no ID.

    TVDB first: it's Sonarr's native ID and every show UMTK handles has been
    resolved to one, so the tag stays consistent across folders.
    """
    for key, prefix in (('tvdbId', 'tvdb'), ('tmdbId', 'tmdb'), ('imdbId', 'imdb')):
        if show.get(key):
            return f"{{{prefix}-{show[key]}}}"
    return ''


def show_folder_name(show):
    """Folder name for a show's placeholder/trailer content.

    The legacy name plus an ID tag so Plex matches the right show, e.g.
    "Show (2025) {tvdb-123456}". Single source of truth so content creation
    and cleanup can never disagree about which folder belongs to a show (a
    mismatch used to leave stale duplicates behind when a year changed).
    A Sonarr folder that already carries a tag is used as is.
    """
    base = legacy_show_folder_name(show)
    if FOLDER_ID_RE.search(base):
        return base
    tag = show_id_tag(show)
    return f"{base} {tag}" if tag else base


def parse_folder_ids(folder_name):
    """IDs tagged in a folder name: "Show (2025) {tvdb-123}" -> {'tvdb': '123'}."""
    return {m.group(1).lower(): m.group(2) for m in FOLDER_ID_RE.finditer(folder_name)}


def strip_folder_ids(folder_name):
    """Folder name without its ID tags, for deriving the title from it."""
    return ' '.join(FOLDER_ID_RE.sub(' ', folder_name).split())


def resolve_show_dir(umtk_root_tv, show):
    """Folder under umtk_root_tv that holds (or will hold) a show's content.

    New folders get the ID-tagged name. A folder created by a release before
    the tag existed is reused as is, so updating never leaves a show with two
    folders; cleanup retires the legacy folder once the show stops qualifying.
    """
    root = Path(umtk_root_tv)
    new_dir = root / show_folder_name(show)
    legacy_dir = root / legacy_show_folder_name(show)
    if legacy_dir != new_dir and legacy_dir.exists() and not new_dir.exists():
        return legacy_dir
    return new_dir


def movie_folder_name(movie, edition_tag):
    """Folder name for a movie's placeholder/trailer content."""
    movie_title = movie.get('title', 'Unknown')
    movie_year = movie.get('year', '')
    return sanitize_filename(f"{movie_title} ({movie_year}) {{edition-{edition_tag}}}")


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
