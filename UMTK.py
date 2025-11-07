import os
import yt_dlp
import requests
import re
import json
import yaml
import sys
import subprocess
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from collections import defaultdict, OrderedDict
from copy import deepcopy
from yaml.representer import SafeRepresenter
from pathlib import Path, PureWindowsPath

VERSION = "2025.11.07"

# ANSI color codes
GREEN = '\033[32m'
ORANGE = '\033[33m'
BLUE = '\033[34m'
RED = '\033[31m'
RESET = '\033[0m'
BOLD = '\033[1m'

def get_user_info():
    try:
        return f"{os.getuid()}:{os.getgid()}"
    except AttributeError:
        import getpass
        return f"Windows User: {getpass.getuser()}"

def get_file_owner(path):
    try:
        stat_info = path.stat()
        return f"{stat_info.st_uid}:{stat_info.st_gid}"
    except AttributeError:
        return "Windows File"
	
def check_for_updates():
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

def load_config(file_path=None):
    """Load configuration from YAML file"""
    if file_path is None:
        # Check if running in Docker
        if os.environ.get('DOCKER') == 'true':
            file_path = Path('/app/config/config.yml')
        else:
            file_path = Path(__file__).parent / 'config' / 'config.yml'
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            return yaml.safe_load(file)
    except FileNotFoundError:
        print(f"Config file '{file_path}' not found.")
        sys.exit(1)
    except yaml.YAMLError as e:
        print(f"Error parsing YAML config file: {e}")
        sys.exit(1)

def get_cookies_path():
    if os.environ.get('DOCKER') == 'true':
        cookies_folder = Path('/cookies')
    else:
        cookies_folder = Path(__file__).parent / 'cookies'
    
    cookies_file = cookies_folder / 'cookies.txt'
    
    if cookies_file.exists() and cookies_file.is_file():
        return str(cookies_file)
    
    return None

def process_sonarr_url(base_url, api_key, timeout=90):
    """Process and validate Sonarr URL"""
    base_url = base_url.rstrip('/')
    
    if base_url.startswith('http'):
        protocol_end = base_url.find('://') + 3
        next_slash = base_url.find('/', protocol_end)
        if next_slash != -1:
            base_url = base_url[:next_slash]
    
    api_paths = [
        '/api/v3',
        '/sonarr/api/v3'
    ]
    
    for path in api_paths:
        test_url = f"{base_url}{path}"
        try:
            headers = {"X-Api-Key": api_key}
            response = requests.get(f"{test_url}/health", headers=headers, timeout=timeout)
            if response.status_code == 200:
                print(f"Successfully connected to Sonarr at: {test_url}")
                return test_url
        except requests.exceptions.RequestException as e:
            print(f"{ORANGE}Testing URL {test_url} - Failed: {str(e)}{RESET}")
            continue
    
    raise ConnectionError(f"{RED}Unable to establish connection to Sonarr. Tried the following URLs:\n" + 
                        "\n".join([f"- {base_url}{path}" for path in api_paths]) + 
                        f"\nPlease verify your URL and API key and ensure Sonarr is running.{RESET}")

def process_radarr_url(base_url, api_key, timeout=90):
    """Process and validate Radarr URL"""
    base_url = base_url.rstrip('/')
    
    if base_url.startswith('http'):
        protocol_end = base_url.find('://') + 3
        next_slash = base_url.find('/', protocol_end)
        if next_slash != -1:
            base_url = base_url[:next_slash]
    
    api_paths = [
        '/api/v3',
        '/radarr/api/v3'
    ]
    
    for path in api_paths:
        test_url = f"{base_url}{path}"
        try:
            headers = {"X-Api-Key": api_key}
            response = requests.get(f"{test_url}/health", headers=headers, timeout=timeout)
            if response.status_code == 200:
                print(f"Successfully connected to Radarr at: {test_url}")
                return test_url
        except requests.exceptions.RequestException as e:
            print(f"{ORANGE}Testing URL {test_url} - Failed: {str(e)}{RESET}")
            continue
    
    raise ConnectionError(f"{RED}Unable to establish connection to Radarr. Tried the following URLs:\n" + 
                        "\n".join([f"- {base_url}{path}" for path in api_paths]) + 
                        f"\nPlease verify your URL and API key and ensure Radarr is running.{RESET}")

def get_sonarr_series(sonarr_url, api_key, timeout=90):
    """Get all series from Sonarr"""
    try:
        print(f"{BLUE}Fetching series from Sonarr...{RESET}", flush=True)
        url = f"{sonarr_url}/series"
        headers = {"X-Api-Key": api_key}
        response = requests.get(url, headers=headers, timeout=timeout)
        response.raise_for_status()
        series_data = response.json()
        print(f"{GREEN}Done ✓ ({len(series_data)} series){RESET}")
        return series_data
    except requests.exceptions.RequestException as e:
        print(f" {RED}✗{RESET}")
        print(f"{RED}Error connecting to Sonarr: {str(e)}{RESET}")
        sys.exit(1)

def get_sonarr_episodes(sonarr_url, api_key, series_id, timeout=90):
    """Get episodes for a specific series"""
    try:
        url = f"{sonarr_url}/episode?seriesId={series_id}"
        headers = {"X-Api-Key": api_key}
        response = requests.get(url, headers=headers, timeout=timeout)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"{RED}Error fetching episodes from Sonarr: {str(e)}{RESET}")
        sys.exit(1)

def get_radarr_movies(radarr_url, api_key, timeout=90):
    """Get all movies from Radarr"""
    try:
        print(f"{BLUE}Fetching movies from Radarr...{RESET}", flush=True)
        url = f"{radarr_url}/movie"
        headers = {"X-Api-Key": api_key}
        response = requests.get(url, headers=headers, timeout=timeout)
        response.raise_for_status()
        movies_data = response.json()
        print(f"{GREEN}Done ✓ ({len(movies_data)} movies){RESET}")
        return movies_data
    except requests.exceptions.RequestException as e:
        print(f" {RED}✗{RESET}")
        print(f"{RED}Error connecting to Radarr: {str(e)}{RESET}")
        sys.exit(1)

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

def fetch_mdblist_items(mdblist_url, api_key, limit=None, debug=False):
    """Fetch items from MDBList API"""
    try:
        # Extract list ID and username from URL
        # URL format: https://mdblist.com/lists/username/listname
        parts = mdblist_url.rstrip('/').split('/')
        list_id = parts[-1]
        username = parts[-2]
        
        api_url = f"https://api.mdblist.com/lists/{username}/{list_id}/items"

        params = {
            "apikey": api_key
        }
        if limit:
            params["limit"] = limit
        
        if debug:
            print(f"{BLUE}[DEBUG] Fetching from MDBList API: {api_url}{RESET}")
            print(f"{BLUE}[DEBUG] Params: {params}{RESET}")
        
        response = requests.get(api_url, params=params, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        
        if debug:
            print(f"{BLUE}[DEBUG] Raw API response type: {type(data)}{RESET}")
            print(f"{BLUE}[DEBUG] Raw API response keys: {data.keys() if isinstance(data, dict) else 'N/A'}{RESET}")
        
        items = []
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            if 'movies' in data and isinstance(data['movies'], list):
                items.extend(data['movies'])
            if 'shows' in data and isinstance(data['shows'], list):
                items.extend(data['shows'])
            
            if not items:
                if 'items' in data:
                    items = data['items']
                elif 'results' in data:
                    items = data['results']
                elif 'data' in data:
                    items = data['data']
                else:
                    print(f"{RED}Error: MDBList API returned dict but no recognizable items key{RESET}")
                    if debug:
                        print(f"{BLUE}[DEBUG] Available keys: {list(data.keys())}{RESET}")
                    return []
        else:
            print(f"{RED}Error: MDBList API returned unexpected format: {type(data).__name__}{RESET}")
            return []
        
        if not isinstance(items, list):
            print(f"{RED}Error: Items from MDBList API is not a list (got {type(items).__name__}){RESET}")
            return []
        
        if debug:
            print(f"{BLUE}[DEBUG] Found {len(items)} items{RESET}")
            if items:
                print(f"{BLUE}[DEBUG] First item type: {type(items[0])}{RESET}")
                print(f"{BLUE}[DEBUG] First item content: {items[0]}{RESET}")
        
        # Validate and normalize items
        validated_items = []
        for item in items:
            if isinstance(item, dict):
                # Normalize the item to match expected format
                normalized_item = {
                    'title': item.get('title', 'Unknown'),
                    'year': item.get('release_year'),
                    'imdb_id': item.get('imdb_id'),
                    'mediatype': item.get('mediatype'),
                    'rank': item.get('rank')  # ADD THIS LINE - preserve rank
                }
                
                # MDBList uses 'id' for TMDB ID for movies, 'tvdb_id' for TV shows
                if item.get('mediatype') == 'movie':
                    normalized_item['tmdb_id'] = item.get('id')
                elif item.get('mediatype') == 'show':
                    normalized_item['tvdb_id'] = item.get('tvdb_id')
                    # Some shows might have TMDB ID in 'id' field
                    if not normalized_item['tvdb_id'] and item.get('id'):
                        normalized_item['tvdb_id'] = item.get('id')
                
                validated_items.append(normalized_item)
            else:
                if debug:
                    print(f"{ORANGE}[DEBUG] Skipping non-dictionary item: {item} (type: {type(item).__name__}){RESET}")
        
        if debug:
            print(f"{BLUE}[DEBUG] Validated {len(validated_items)} items from MDBList{RESET}")
        
        return validated_items

    except requests.exceptions.RequestException as e:
        print(f"{RED}Error fetching from MDBList: {str(e)}{RESET}")
        if debug and 'response' in locals():
            print(f"{RED}Response text: {response.text}{RESET}")
        return []
    except Exception as e:
        print(f"{RED}Unexpected error fetching from MDBList: {str(e)}{RESET}")
        if debug:
            import traceback
            traceback.print_exc()
        return []

def check_video_file():
    """Check if UMTK video file exists"""
    # Check if running in Docker
    if os.environ.get('DOCKER') == 'true':
        video_folder = Path('/video')
    else:
        video_folder = Path(__file__).parent / 'video'
    
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

# TV Show specific functions
def find_upcoming_shows(all_series, sonarr_url, api_key, future_days_upcoming_shows, utc_offset=0, debug=False, exclude_tags=None, future_only_tv=False):
    """Find shows with upcoming episodes that have their first episode airing within specified days"""
    future_shows = []
    aired_shows = []
    
    cutoff_date = datetime.now(timezone.utc) + timedelta(days=future_days_upcoming_shows)
    now_local = datetime.now(timezone.utc) + timedelta(hours=utc_offset)
    
    if debug:
        print(f"{BLUE}[DEBUG] Cutoff date: {cutoff_date}, Now local: {now_local}{RESET}")
        print(f"{BLUE}[DEBUG] Future only TV: {future_only_tv}{RESET}")
        print(f"{BLUE}[DEBUG] Found {len(all_series)} total series in Sonarr{RESET}")
   
    for series in all_series:
        if debug:
            print(f"{BLUE}[DEBUG] Processing show: {series['title']} (status: {series.get('status')}, monitored: {series.get('monitored', True)}){RESET}")
        
        # Always skip unmonitored shows
        if not series.get('monitored', True):
            if debug:
                print(f"{ORANGE}[DEBUG] Skipping unmonitored show: {series['title']}{RESET}")
            continue
        
        # Check for excluded tags
        if exclude_tags:
            series_tags = series.get('tags', [])
            if any(tag in series_tags for tag in exclude_tags):
                if debug:
                    print(f"{ORANGE}[DEBUG] Skipping show with excluded tags: {series['title']}{RESET}")
                continue
        
        episodes = get_sonarr_episodes(sonarr_url, api_key, series['id'])
        
        if debug:
            print(f"{BLUE}[DEBUG] Found {len(episodes)} episodes for {series['title']}{RESET}")
        
        # Find S01E01 specifically
        first_episode = None
        
        for ep in episodes:
            if ep.get('seasonNumber') == 1 and ep.get('episodeNumber') == 1:
                first_episode = ep
                break
        
        if not first_episode:
            if debug:
                print(f"{ORANGE}[DEBUG] No Season 1 Episode 1 found for {series['title']}{RESET}")
            continue
        
        # Skip if S01E01 is not monitored
        if not first_episode.get('monitored', False):
            if debug:
                print(f"{ORANGE}[DEBUG] S01E01 not monitored for {series['title']}{RESET}")
            continue
        
        # Skip if S01E01 is already downloaded
        if first_episode.get('hasFile', False):
            if debug:
                print(f"{ORANGE}[DEBUG] S01E01 already downloaded for {series['title']} - skipping{RESET}")
            continue
        
        air_date_str = first_episode.get('airDateUtc')
        if not air_date_str:
            if debug:
                print(f"{ORANGE}[DEBUG] No air date found for {series['title']} S01E01{RESET}")
            continue
        
        air_date = convert_utc_to_local(air_date_str, utc_offset)
        
        if debug:
            print(f"{BLUE}[DEBUG] {series['title']} air date: {air_date}, within range: {air_date <= cutoff_date}{RESET}")
        
        # Check if air date is within our range
        if air_date <= cutoff_date:
            tvdb_id = series.get('tvdbId')
            air_date_str_yyyy_mm_dd = air_date.date().isoformat()
            
            show_dict = {
                'title': series['title'],
                'tvdbId': tvdb_id,
                'path': series.get('path', ''),
                'imdbId': series.get('imdbId', ''),
                'year': series.get('year', None),
                'airDate': air_date_str_yyyy_mm_dd
            }
            
            # Categorize based on whether it has aired or not
            if air_date >= now_local:
                future_shows.append(show_dict)
                if debug:
                    print(f"{GREEN}[DEBUG] Added to future shows: {series['title']}{RESET}")
            elif not future_only_tv:  # Only add aired shows if future_only_tv is false
                aired_shows.append(show_dict)
                if debug:
                    print(f"{GREEN}[DEBUG] Added to aired shows: {series['title']}{RESET}")
            elif debug:
                print(f"{ORANGE}[DEBUG] Skipping aired show due to future_only_tv=True: {series['title']}{RESET}")
    
    return future_shows, aired_shows

def find_new_shows(all_series, sonarr_url, api_key, recent_days_new_show, utc_offset=0, debug=False):
    """Find shows where S01E01 has been downloaded and aired within specified past days"""
    new_shows = []
    
    now_local = datetime.now(timezone.utc) + timedelta(hours=utc_offset)
    cutoff_date = now_local - timedelta(days=recent_days_new_show)
    
    if debug:
        print(f"{BLUE}[DEBUG] Looking for shows with S01E01 aired between {cutoff_date} and {now_local}{RESET}")
        print(f"{BLUE}[DEBUG] Found {len(all_series)} total series in Sonarr{RESET}")
    
    for series in all_series:
        if debug:
            print(f"{BLUE}[DEBUG] Checking series: {series['title']} (monitored: {series.get('monitored', True)}){RESET}")
        
        # Always skip unmonitored shows
        if not series.get('monitored', True):
            if debug:
                print(f"{ORANGE}[DEBUG] Skipping unmonitored show: {series['title']}{RESET}")
            continue
        
        episodes = get_sonarr_episodes(sonarr_url, api_key, series['id'])
        
        s01e01 = None
        for ep in episodes:
            if ep.get('seasonNumber') == 1 and ep.get('episodeNumber') == 1:
                s01e01 = ep
                break
        
        if not s01e01:
            if debug:
                print(f"{ORANGE}[DEBUG] No S01E01 found for {series['title']}{RESET}")
            continue
        
        if not s01e01.get('hasFile', False):
            if debug:
                print(f"{ORANGE}[DEBUG] S01E01 not downloaded for {series['title']}{RESET}")
            continue
        
        air_date_str = s01e01.get('airDateUtc')
        if not air_date_str:
            if debug:
                print(f"{ORANGE}[DEBUG] No air date for {series['title']} S01E01{RESET}")
            continue
        
        air_date = convert_utc_to_local(air_date_str, utc_offset)
        
        if debug:
            print(f"{BLUE}[DEBUG] {series['title']} S01E01 aired: {air_date}, within range: {cutoff_date <= air_date <= now_local}{RESET}")
        
        if cutoff_date <= air_date <= now_local:
            tvdb_id = series.get('tvdbId')
            air_date_str_yyyy_mm_dd = air_date.date().isoformat()
            
            show_dict = {
                'title': series['title'],
                'tvdbId': tvdb_id,
                'path': series.get('path', ''),
                'imdbId': series.get('imdbId', ''),
                'year': series.get('year', None),
                'airDate': air_date_str_yyyy_mm_dd
            }
            
            new_shows.append(show_dict)
            
            if debug:
                print(f"{GREEN}[DEBUG] Added to new shows: {series['title']}{RESET}")
    
    return new_shows

# Movie specific functions
def find_upcoming_movies(all_movies, radarr_url, api_key, future_days_upcoming_movies, utc_offset=0, future_only=False, include_inCinemas=False, debug=False, exclude_tags=None):
    """Find movies that are monitored and meet release date criteria"""
    future_movies = []
    released_movies = []
    
    cutoff_date = datetime.now(timezone.utc) + timedelta(days=future_days_upcoming_movies)
    now_local = datetime.now(timezone.utc) + timedelta(hours=utc_offset)
    
    if debug:
        print(f"{BLUE}[DEBUG] Cutoff date: {cutoff_date}, Now local: {now_local}{RESET}")
        print(f"{BLUE}[DEBUG] Future only mode: {future_only}{RESET}")
        print(f"{BLUE}[DEBUG] Include inCinemas: {include_inCinemas}{RESET}")
        print(f"{BLUE}[DEBUG] Found {len(all_movies)} total movies in Radarr{RESET}")
    
    for movie in all_movies:
        if not movie.get('monitored', False):
            if debug:
                print(f"{ORANGE}[DEBUG] Skipping unmonitored movie: {movie['title']}{RESET}")
            continue
        
        if movie.get('hasFile', False):
            if debug:
                print(f"{ORANGE}[DEBUG] Skipping downloaded movie: {movie['title']}{RESET}")
            continue
        
        # Check for excluded tags
        if exclude_tags:
            movie_tags = movie.get('tags', [])
            if any(tag in movie_tags for tag in exclude_tags):
                if debug:
                    print(f"{ORANGE}[DEBUG] Skipping movie with excluded tags: {movie['title']}{RESET}")
                continue
        
        release_date_str = None
        release_type = None
        
        if include_inCinemas:
            dates_to_check = [
                (movie.get('digitalRelease'), 'Digital'),
                (movie.get('physicalRelease'), 'Physical'),
                (movie.get('inCinemas'), 'Cinema')
            ]
            
            valid_dates = [(date_str, rel_type) for date_str, rel_type in dates_to_check if date_str]
            
            if valid_dates:
                valid_dates.sort(key=lambda x: x[0])
                release_date_str, release_type = valid_dates[0]
        else:
            if movie.get('digitalRelease'):
                release_date_str = movie['digitalRelease']
                release_type = 'Digital'
            elif movie.get('physicalRelease'):
                release_date_str = movie['physicalRelease']
                release_type = 'Physical'
        
        if not release_date_str:
            if debug:
                print(f"{ORANGE}[DEBUG] No suitable release date found for {movie['title']}{RESET}")
            continue
        
        release_date = convert_utc_to_local(release_date_str, utc_offset)
        release_date_str_yyyy_mm_dd = release_date.date().isoformat()
        
        if debug:
            print(f"{BLUE}[DEBUG] {movie['title']} release date: {release_date} ({release_type}){RESET}")
        
        movie_dict = {
            'title': movie['title'],
            'tmdbId': movie.get('tmdbId'),
            'imdbId': movie.get('imdbId'),
            'path': movie.get('path', ''),
            'folderName': movie.get('folderName', ''),
            'year': movie.get('year', None),
            'releaseDate': release_date_str_yyyy_mm_dd,
            'releaseType': release_type
        }
        
        if release_date >= now_local and release_date <= cutoff_date:
            future_movies.append(movie_dict)
            if debug:
                print(f"{GREEN}[DEBUG] Added to future movies: {movie['title']}{RESET}")
        elif release_date < now_local and not future_only:
            released_movies.append(movie_dict)
            if debug:
                print(f"{GREEN}[DEBUG] Added to released movies: {movie['title']}{RESET}")
    
    return future_movies, released_movies

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

def process_trending_movies(mdblist_items, all_movies, radarr_url, api_key, debug=False):
    """
    Process trending movies from MDBList
    Returns: (monitored_not_available, not_found_or_unmonitored)
    """
    monitored_not_available = []
    not_found_or_unmonitored = []
    
    if debug:
        print(f"{BLUE}[DEBUG] Processing {len(mdblist_items)} trending movies{RESET}")
    
    # Create lookup dictionaries for Radarr movies
    radarr_by_tmdb = {}
    radarr_by_imdb = {}
    
    for movie in all_movies:
        if movie.get('tmdbId'):
            radarr_by_tmdb[str(movie['tmdbId'])] = movie
        if movie.get('imdbId'):
            radarr_by_imdb[movie['imdbId']] = movie
    
    for item in mdblist_items:
        # MDBList items have tmdb_id, imdb_id, title, year
        tmdb_id = str(item.get('tmdb_id', ''))
        imdb_id = item.get('imdb_id', '')
        title = item.get('title', 'Unknown')
        year = item.get('year')
        
        if debug:
            print(f"{BLUE}[DEBUG] Processing trending movie: {title} ({year}) - TMDB: {tmdb_id}, IMDB: {imdb_id}{RESET}")
        
        # Try to find in Radarr
        radarr_movie = None
        if tmdb_id and tmdb_id in radarr_by_tmdb:
            radarr_movie = radarr_by_tmdb[tmdb_id]
        elif imdb_id and imdb_id in radarr_by_imdb:
            radarr_movie = radarr_by_imdb[imdb_id]
        
        if radarr_movie:
            if debug:
                print(f"{BLUE}[DEBUG] Found in Radarr: {radarr_movie['title']}{RESET}")
            
            # Check if downloaded
            if radarr_movie.get('hasFile', False):
                if debug:
                    print(f"{BLUE}[DEBUG] Already downloaded, skipping{RESET}")
                continue
            
            # Check if monitored
            if radarr_movie.get('monitored', False):
                if debug:
                    print(f"{BLUE}[DEBUG] Monitored but not available - adding to monitored_not_available{RESET}")
                
                movie_dict = {
                    'title': radarr_movie['title'],
                    'tmdbId': radarr_movie.get('tmdbId'),
                    'imdbId': radarr_movie.get('imdbId'),
                    'path': radarr_movie.get('path', ''),
                    'folderName': radarr_movie.get('folderName', ''),
                    'year': radarr_movie.get('year', None),
                    'releaseDate': None,  # Not needed for trending
                    'releaseType': 'Trending'
                }
                monitored_not_available.append(movie_dict)
            else:
                if debug:
                    print(f"{BLUE}[DEBUG] Not monitored - adding to not_found_or_unmonitored{RESET}")
                
                movie_dict = {
                    'title': radarr_movie['title'],
                    'tmdbId': radarr_movie.get('tmdbId'),
                    'imdbId': radarr_movie.get('imdbId'),
                    'path': radarr_movie.get('path', ''),
                    'folderName': radarr_movie.get('folderName', ''),
                    'year': radarr_movie.get('year', None),
                    'releaseDate': None,
                    'releaseType': 'Trending'
                }
                not_found_or_unmonitored.append(movie_dict)
        else:
            if debug:
                print(f"{BLUE}[DEBUG] Not found in Radarr - adding to not_found_or_unmonitored{RESET}")
            
            # Create movie dict from MDBList data
            movie_dict = {
                'title': title,
                'tmdbId': int(tmdb_id) if tmdb_id and tmdb_id.isdigit() else None,
                'imdbId': imdb_id,
                'path': None,
                'folderName': None,
                'year': year,
                'releaseDate': None,
                'releaseType': 'Trending'
            }
            not_found_or_unmonitored.append(movie_dict)
    
    return monitored_not_available, not_found_or_unmonitored

def process_trending_tv(mdblist_items, all_series, sonarr_url, api_key, debug=False):
    """
    Process trending TV shows from MDBList
    Returns: (monitored_not_available, not_found_or_unmonitored)
    """
    monitored_not_available = []
    not_found_or_unmonitored = []
    
    if debug:
        print(f"{BLUE}[DEBUG] Processing {len(mdblist_items)} trending TV shows{RESET}")
    
    # Create lookup dictionaries for Sonarr series
    sonarr_by_tvdb = {}
    sonarr_by_imdb = {}
    
    for series in all_series:
        if series.get('tvdbId'):
            sonarr_by_tvdb[str(series['tvdbId'])] = series
        if series.get('imdbId'):
            sonarr_by_imdb[series['imdbId']] = series
    
    for item in mdblist_items:
        # MDBList items have tvdb_id, imdb_id, title, year
        tvdb_id = str(item.get('tvdb_id', ''))
        imdb_id = item.get('imdb_id', '')
        title = item.get('title', 'Unknown')
        year = item.get('year')
        
        if debug:
            print(f"{BLUE}[DEBUG] Processing trending show: {title} ({year}) - TVDB: {tvdb_id}, IMDB: {imdb_id}{RESET}")
        
        # Try to find in Sonarr
        sonarr_series = None
        if tvdb_id and tvdb_id in sonarr_by_tvdb:
            sonarr_series = sonarr_by_tvdb[tvdb_id]
        elif imdb_id and imdb_id in sonarr_by_imdb:
            sonarr_series = sonarr_by_imdb[imdb_id]
        
        if sonarr_series:
            if debug:
                print(f"{BLUE}[DEBUG] Found in Sonarr: {sonarr_series['title']}{RESET}")
            
            # Check if monitored
            if not sonarr_series.get('monitored', False):
                if debug:
                    print(f"{BLUE}[DEBUG] Not monitored - adding to not_found_or_unmonitored{RESET}")
                
                show_dict = {
                    'title': sonarr_series['title'],
                    'tvdbId': sonarr_series.get('tvdbId'),
                    'path': sonarr_series.get('path', ''),
                    'imdbId': sonarr_series.get('imdbId', ''),
                    'year': sonarr_series.get('year', None),
                    'airDate': None
                }
                not_found_or_unmonitored.append(show_dict)
                continue
            
            # Get episodes to check if any are downloaded
            episodes = get_sonarr_episodes(sonarr_url, api_key, sonarr_series['id'])
            
            # Check if any episodes are downloaded
            has_downloaded_episodes = any(ep.get('hasFile', False) for ep in episodes)
            
            if has_downloaded_episodes:
                if debug:
                    print(f"{BLUE}[DEBUG] Has downloaded episodes, skipping{RESET}")
                continue
            else:
                if debug:
                    print(f"{BLUE}[DEBUG] Monitored but no episodes available - adding to monitored_not_available{RESET}")
                
                show_dict = {
                    'title': sonarr_series['title'],
                    'tvdbId': sonarr_series.get('tvdbId'),
                    'path': sonarr_series.get('path', ''),
                    'imdbId': sonarr_series.get('imdbId', ''),
                    'year': sonarr_series.get('year', None),
                    'airDate': None
                }
                monitored_not_available.append(show_dict)
        else:
            if debug:
                print(f"{BLUE}[DEBUG] Not found in Sonarr - adding to not_found_or_unmonitored{RESET}")
            
            # Create show dict from MDBList data
            show_dict = {
                'title': title,
                'tvdbId': int(tvdb_id) if tvdb_id and tvdb_id.isdigit() else None,
                'path': None,
                'imdbId': imdb_id,
                'year': year,
                'airDate': None
            }
            not_found_or_unmonitored.append(show_dict)
    
    return monitored_not_available, not_found_or_unmonitored

# Trailer search function (shared)
def _normalize(s: str) -> str:
    return re.sub(r'[^a-z0-9]+', ' ', (s or '').lower()).strip()

def _base_title(title: str) -> str:
    return re.sub(r'\s*[\(\[]\d{4}[\)\]]\s*', ' ', title or '').strip()

def _title_matches(video_title: str, content_title: str) -> bool:
    base = _normalize(_base_title(content_title))
    vt = _normalize(video_title)
    return base and base in vt

def search_trailer_on_youtube(content_title, year=None, imdb_id=None, debug=False, skip_channels=None):
    """Return the best matching trailer info from YouTube (dict) or None."""
    search_terms = [
        f"{content_title} {year} trailer" if year else None,
        f"{content_title} {year} official trailer" if year else None,
        f"{content_title} {year} teaser" if year else None,
        f"{content_title} trailer",
        f"{content_title} official trailer",
        f"{content_title} teaser",
        f"{content_title} official teaser",
        f"{content_title} first look",
    ]
    search_terms = [t for t in search_terms if t]

    avoid_keywords = [
        'reaction','review','breakdown','analysis','explained','easter eggs','theory',
        'predictions','recap','commentary','first time watching','blind reaction',
        'behind the scenes','fan made','concept','music video','news','interview'
    ]

    preferred_channels = {
        "Netflix", "Prime Video", "HBO Max", "Max", "Apple TV", "Apple TV+",
        "Marvel Entertainment", "Star Wars", "Lucasfilm", "Disney Plus",
        "Disney", "Pixar", "Paramount Pictures", "Sony Pictures Entertainment",
        "Warner Bros. Pictures", "Universal Pictures", "20th Century Studios",
        "Lionsgate Movies", "BBC", "Peacock", "AMC", "Showtime", "Starz",
        "netflix","hbo","max","amazon","prime video","disney","marvel","lucasfilm",
        "apple tv","paramount","showtime","starz","fx","amc","peacock","universal",
        "sony pictures","warner bros","20th century","lionsgate","bbc","itv","channel 4","hulu"
    }

    if debug:
        print(f"{BLUE}[DEBUG] Searching for trailers with these terms: {search_terms}{RESET}")
        if skip_channels:
            print(f"{BLUE}[DEBUG] Skip channels: {skip_channels}{RESET}")

    best = None
    best_score = -1

    for term in search_terms:
        try:
            if debug:
                print(f"{BLUE}[DEBUG] Trying search term: '{term}'{RESET}")

            cmd = ['yt-dlp','--dump-json','--no-warnings','--flat-playlist', f'ytsearch15:{term}']
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

            if res.returncode != 0 or not res.stdout.strip():
                if debug:
                    print(f"{ORANGE}[DEBUG] No results for '{term}'{RESET}")
                continue

            for line in res.stdout.strip().splitlines():
                try:
                    info = json.loads(line)
                except json.JSONDecodeError:
                    continue

                title = info.get('title') or ''
                vid   = info.get('id') or ''
                up    = info.get('uploader') or 'Unknown'
                dur   = info.get('duration')

                if not title or not vid:
                    continue

                if skip_channels and any(ch.lower() in up.lower() for ch in skip_channels):
                    continue

                tl = title.lower()
                if any(k in tl for k in avoid_keywords):
                    continue

                if dur and not (10 <= float(dur) <= 900):
                    continue

                if not _title_matches(title, content_title):
                    if debug:
                        print(f"{ORANGE}[DEBUG] Skipping '{title}' - does not match '{content_title}'{RESET}")
                    continue

                score = 0
                if 'official' in tl: score += 3
                if 'trailer'  in tl: score += 2
                if 'teaser'   in tl: score += 1

                if up.strip() in preferred_channels:
                    score += 20
                elif any(ch in up.lower() for ch in preferred_channels):
                    score += 5

                if year and str(year) in tl: score += 2

                if score > best_score:
                    d = int(dur) if isinstance(dur, (int, float)) else 0
                    duration_str = f"{d//60}:{d%60:02d}" if d else "Unknown"
                    best_score = score
                    best = {
                        'video_id': vid,
                        'video_title': title,
                        'duration': duration_str,
                        'uploader': up,
                        'url': f'https://www.youtube.com/watch?v={vid}',
                        'is_official': True
                    }

        except subprocess.TimeoutExpired:
            if debug:
                print(f"{ORANGE}[DEBUG] Search timeout for '{term}'{RESET}")
            continue
        except Exception as e:
            if debug:
                print(f"{ORANGE}[DEBUG] Search error: {e}{RESET}")
            continue

    if debug and best:
        print(f"{GREEN}[DEBUG] Best match: {best}{RESET}")

    return best

# Video handling functions
def download_trailer_tv(show, trailer_info, debug=False, umtk_root_tv=None):
    """Download trailer for TV show"""
    show_path = show.get('path')
    
    # Determine the target directory
    if umtk_root_tv:
        # Extract just the show folder name from the Sonarr path
        if show_path:
            # Use PureWindowsPath to handle Windows paths from Sonarr even in Docker/Linux
            show_name = PureWindowsPath(show_path).name
        else:
            # For trending shows without a path, create folder name
            show_title = show.get('title', 'Unknown')
            show_year = show.get('year', '')
            if show_year:
                show_name = sanitize_filename(f"{show_title} ({show_year})")
            else:
                show_name = sanitize_filename(show_title)
        
        parent_dir = Path(umtk_root_tv) / show_name
        season_00_path = parent_dir / "Season 00"
    else:
        # Use original Sonarr path
        if not show_path:
            print(f"{RED}No path found for show: {show.get('title')} and umtk_root_tv not configured{RESET}")
            return False
        parent_dir = Path(show_path)
        season_00_path = parent_dir / "Season 00"
    
    if debug:
        print(f"{BLUE}[DEBUG] Show path from Sonarr: {show_path}{RESET}")
        print(f"{BLUE}[DEBUG] Parent directory: {parent_dir}{RESET}")
        print(f"{BLUE}[DEBUG] Season 00 path: {season_00_path}{RESET}")
        if umtk_root_tv:
            print(f"{BLUE}[DEBUG] Using custom umtk_root_tv: {umtk_root_tv}{RESET}")
        
    # Create parent directory if it doesn't exist
    if not parent_dir.exists():
        try:
            parent_dir.mkdir(parents=True, exist_ok=True)
            # Set proper permissions on created directory
            try:
                os.chmod(parent_dir, 0o755)
                if debug:
                    print(f"{BLUE}[DEBUG] Created parent directory: {parent_dir}{RESET}")
                    print(f"{BLUE}[DEBUG] Set permissions 755 on {parent_dir}{RESET}")
            except Exception as perm_error:
                if debug:
                    print(f"{ORANGE}[DEBUG] Could not set directory permissions: {perm_error}{RESET}")
        except Exception as e:
            print(f"{RED}Error creating parent directory {parent_dir}: {e}{RESET}")
            return False
    
    # Check if parent directory is writable
    if not os.access(parent_dir, os.W_OK):
        print(f"{RED}Error: No write permission for directory: {parent_dir}{RESET}")
        print(f"{RED}Directory owner: {get_file_owner(parent_dir)}{RESET}")
        print(f"{RED}Current user: {get_user_info()}{RESET}")
        return False
    
    try:
        season_00_path.mkdir(parents=True, exist_ok=True)
        
        # Set proper permissions on created directory
        try:
            os.chmod(season_00_path, 0o755)
            if debug:
                print(f"{BLUE}[DEBUG] Set permissions 755 on {season_00_path}{RESET}")
        except Exception as perm_error:
            if debug:
                print(f"{ORANGE}[DEBUG] Could not set directory permissions: {perm_error}{RESET}")
        
    except PermissionError as e:
        print(f"{RED}Permission error creating directory {season_00_path}: {e}{RESET}")
        print(f"{RED}Parent directory permissions: {oct(parent_dir.stat().st_mode)[-3:]}{RESET}")
        return False
    except Exception as e:
        print(f"{RED}Error creating directory {season_00_path}: {e}{RESET}")
        return False

    clean_title = "".join(c for c in show['title'] if c.isalnum() or c in (' ', '-', '_')).rstrip()

    filename = f"{clean_title}.S00E00.Trailer.%(ext)s"
    output_path = season_00_path / filename

    # Get cookies path if available
    cookies_path = get_cookies_path()
    
    try:
        def _run(format_string):
            ydl_opts = {
                'format': format_string,
                'outtmpl': str(output_path),
                'noplaylist': True,
                'postprocessors': [{
                    'key': 'FFmpegVideoConvertor',
                    'preferedformat': 'mkv'
                }],
                'ignoreerrors': False,
                'quiet': not debug,
                'no_warnings': not debug,
                'extractor_args': {'youtube': {'player_js_version': ['actual']}}
            }
            
            # Add cookies if available
            if cookies_path:
                ydl_opts['cookiefile'] = cookies_path
                if debug:
                    print(f"{BLUE}[DEBUG] Using cookies file: {cookies_path}{RESET}")
            
            if debug:
                print(f"{BLUE}[DEBUG] yt-dlp opts (format): {format_string}{RESET}")
                print(f"{BLUE}[DEBUG] URL: {trailer_info['url']}{RESET}")
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([trailer_info['url']])

        print(f"Downloading trailer for {show['title']} (prefer 1080p MKV/MP4)...")

        try:
            _run('(bv*[ext=mkv][height=1080]+ba/b[ext=mkv][height=1080]) / (bv*[ext=mp4][height=1080]+ba[ext=m4a]/b[ext=mp4][height=1080]) / (bv*[height=1080]+ba/b[height=1080])')
        except Exception as e1:
            if debug:
                print(f"{ORANGE}[DEBUG] 1080p exact failed ({e1}); trying best <=1080p{RESET}")
            _run('(bv*[ext=mkv][height<=1080]+ba/b[ext=mkv][height<=1080]) / (bv*[ext=mp4][height<=1080]+ba[ext=m4a]/b[ext=mp4][height<=1080]) / (bv*[height<=1080]+ba/b[height<=1080])')

        downloaded_files = list(season_00_path.glob(f"{clean_title}.S00E00.Trailer.*"))
        if downloaded_files:
            downloaded_file = downloaded_files[0]
            
            # Set proper permissions on downloaded file
            try:
                os.chmod(downloaded_file, 0o644)
                if debug:
                    print(f"{BLUE}[DEBUG] Set permissions 644 on {downloaded_file}{RESET}")
            except Exception as perm_error:
                if debug:
                    print(f"{ORANGE}[DEBUG] Could not set file permissions: {perm_error}{RESET}")
            
            size_mb = downloaded_file.stat().st_size / (1024 * 1024)
            print(f"{GREEN}Successfully downloaded trailer for {show['title']}: {downloaded_file.name} ({size_mb:.1f} MB){RESET}")
            
            # Mark as trending if this is a trending show
            if show.get('is_trending', False):
                marker_file = season_00_path / ".trending"
                try:
                    marker_file.touch()
                    if debug:
                        print(f"{BLUE}[DEBUG] Created trending marker file: {marker_file}{RESET}")
                except Exception as e:
                    if debug:
                        print(f"{ORANGE}[DEBUG] Could not create trending marker: {e}{RESET}")
            
            # Mark as actual trailer (not placeholder)
            show['used_trailer'] = True
            
            return True

        print(f"{RED}Trailer file not found after download for {show['title']}{RESET}")
        return False

    except Exception as e:
        print(f"{RED}Download error for {show['title']}: {e}{RESET}")
        return False

def download_trailer_movie(movie, trailer_info, debug=False, umtk_root_movies=None, is_trending=False):
    """Download trailer for movie"""
    movie_path = movie.get('path')
    
    movie_title = movie.get('title', 'Unknown')
    movie_year = movie.get('year', '')
    tmdb_id = movie.get('tmdbId', '')
    
    # Use different edition tag for trending
    edition_tag = "Trending" if is_trending else "Coming Soon"
    
    folder_name = sanitize_filename(f"{movie_title} ({movie_year}) {{edition-{edition_tag}}}")
    file_name = sanitize_filename(f"{movie_title} ({movie_year}) {{tmdb-{tmdb_id}}} {{edition-{edition_tag}}}")
    
    # For trending movies without a path, use umtk_root_movies
    if not movie_path:
        if not umtk_root_movies:
            print(f"{RED}No path found for movie: {movie.get('title')} and umtk_root_movies not configured{RESET}")
            return False
        
        parent_dir = Path(umtk_root_movies)
        target_path = parent_dir / folder_name
        if debug:
            print(f"{BLUE}[DEBUG] Created path for trending movie: {target_path}{RESET}")
    elif umtk_root_movies:
        # Use custom root path
        parent_dir = Path(umtk_root_movies)
        target_path = parent_dir / folder_name
    else:
        # Use original logic
        base_path = Path(movie_path)
        parent_dir = base_path.parent
        target_path = parent_dir / folder_name
    
    if debug:
        print(f"{BLUE}[DEBUG] Movie path from Radarr: {movie_path}{RESET}")
        print(f"{BLUE}[DEBUG] Parent directory: {parent_dir}{RESET}")
        print(f"{BLUE}[DEBUG] Target path: {target_path}{RESET}")
        print(f"{BLUE}[DEBUG] Edition tag: {edition_tag}{RESET}")
        if umtk_root_movies:
            print(f"{BLUE}[DEBUG] Using custom umtk_root_movies: {umtk_root_movies}{RESET}")

    # Create parent directory if it doesn't exist
    if not parent_dir.exists():
        try:
            parent_dir.mkdir(parents=True, exist_ok=True)
            try:
                os.chmod(parent_dir, 0o755)
                if debug:
                    print(f"{BLUE}[DEBUG] Created parent directory: {parent_dir}{RESET}")
                    print(f"{BLUE}[DEBUG] Set permissions 755 on {parent_dir}{RESET}")
            except Exception as perm_error:
                if debug:
                    print(f"{ORANGE}[DEBUG] Could not set directory permissions: {perm_error}{RESET}")
        except Exception as e:
            print(f"{RED}Error creating parent directory {parent_dir}: {e}{RESET}")
            return False
    
    # Check if parent directory is writable
    if not os.access(parent_dir, os.W_OK):
        print(f"{RED}Error: No write permission for directory: {parent_dir}{RESET}")
        print(f"{RED}Directory owner: {get_file_owner(parent_dir)}{RESET}")
        print(f"{RED}Current user: {get_user_info()}{RESET}")
        return False
    
    try:
        target_path.mkdir(parents=True, exist_ok=True)
        
        try:
            os.chmod(target_path, 0o755)
            if debug:
                print(f"{BLUE}[DEBUG] Set permissions 755 on {target_path}{RESET}")
        except Exception as perm_error:
            if debug:
                print(f"{ORANGE}[DEBUG] Could not set directory permissions: {perm_error}{RESET}")
        
    except PermissionError as e:
        print(f"{RED}Permission error creating directory {target_path}: {e}{RESET}")
        print(f"{RED}Parent directory permissions: {oct(parent_dir.stat().st_mode)[-3:]}{RESET}")
        return False
    except Exception as e:
        print(f"{RED}Error creating directory {target_path}: {e}{RESET}")
        return False

    filename = f"{file_name}.%(ext)s"
    output_path = target_path / filename

    # Get cookies path if available
    cookies_path = get_cookies_path()

    try:
        def _run(format_string):
            ydl_opts = {
                'format': format_string,
                'outtmpl': str(output_path),
                'noplaylist': True,
                'postprocessors': [{
                    'key': 'FFmpegVideoConvertor',
                    'preferedformat': 'mkv'
                }],
                'ignoreerrors': False,
                'quiet': not debug,
                'no_warnings': not debug,
                'extractor_args': {'youtube': {'player_js_version': ['actual']}}
            }
            
            if cookies_path:
                ydl_opts['cookiefile'] = cookies_path
                if debug:
                    print(f"{BLUE}[DEBUG] Using cookies file: {cookies_path}{RESET}")
            
            if debug:
                print(f"{BLUE}[DEBUG] yt-dlp opts (format): {format_string}{RESET}")
                print(f"{BLUE}[DEBUG] URL: {trailer_info['url']}{RESET}")
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([trailer_info['url']])

        print(f"Downloading trailer for {movie['title']} (prefer 1080p MKV/MP4)...")

        try:
            _run('(bv*[ext=mkv][height=1080]+ba/b[ext=mkv][height=1080]) / (bv*[ext=mp4][height=1080]+ba[ext=m4a]/b[ext=mp4][height=1080]) / (bv*[height=1080]+ba/b[height=1080])')
        except Exception as e1:
            if debug:
                print(f"{ORANGE}[DEBUG] 1080p exact failed ({e1}); trying best <=1080p{RESET}")
            _run('(bv*[ext=mkv][height<=1080]+ba/b[ext=mkv][height<=1080]) / (bv*[ext=mp4][height<=1080]+ba[ext=m4a]/b[ext=mp4][height<=1080]) / (bv*[height<=1080]+ba/b[height<=1080])')

        downloaded_files = list(target_path.glob(f"{file_name}.*"))
        if downloaded_files:
            downloaded_file = downloaded_files[0]
            
            try:
                os.chmod(downloaded_file, 0o644)
                if debug:
                    print(f"{BLUE}[DEBUG] Set permissions 644 on {downloaded_file}{RESET}")
            except Exception as perm_error:
                if debug:
                    print(f"{ORANGE}[DEBUG] Could not set file permissions: {perm_error}{RESET}")
            
            size_mb = downloaded_file.stat().st_size / (1024 * 1024)
            print(f"{GREEN}Successfully downloaded trailer for {movie['title']}: {downloaded_file.name} ({size_mb:.1f} MB){RESET}")
            return True

        print(f"{RED}Trailer file not found after download for {movie['title']}{RESET}")
        return False

    except Exception as e:
        print(f"{RED}Download error for {movie['title']}: {e}{RESET}")
        return False

def create_placeholder_tv(show, debug=False, umtk_root_tv=None):
    """Create placeholder video for TV show"""
    # Check if running in Docker
    if os.environ.get('DOCKER') == 'true':
        video_folder = Path('/video')
    else:
        video_folder = Path(__file__).parent / 'video'
    
    source_files = list(video_folder.glob('UMTK.*'))
    
    if not source_files:
        print(f"{RED}No UMTK video file found in video folder{RESET}")
        return False
    
    source_file = source_files[0]
    video_extension = source_file.suffix
    
    show_path = show.get('path')
    
    # Determine the target directory
    if umtk_root_tv:
        # Extract just the show folder name from the Sonarr path
        if show_path:
            # Use PureWindowsPath to handle Windows paths from Sonarr even in Docker/Linux
            show_name = PureWindowsPath(show_path).name
        else:
            # For trending shows without a path, create folder name
            show_title = show.get('title', 'Unknown')
            show_year = show.get('year', '')
            if show_year:
                show_name = sanitize_filename(f"{show_title} ({show_year})")
            else:
                show_name = sanitize_filename(show_title)
        
        parent_dir = Path(umtk_root_tv) / show_name
        season_00_path = parent_dir / "Season 00"
    else:
        # Use original Sonarr path
        if not show_path:
            print(f"{RED}No path found for show: {show.get('title')} and umtk_root_tv not configured{RESET}")
            return False
        parent_dir = Path(show_path)
        season_00_path = parent_dir / "Season 00"
        
    clean_title = "".join(c for c in show['title'] if c.isalnum() or c in (' ', '-', '_')).rstrip()
    dest_file = season_00_path / f"{clean_title}.S00E00.Coming.Soon{video_extension}"
    
    if debug:
        print(f"{BLUE}[DEBUG] Show path from Sonarr: {show_path}{RESET}")
        print(f"{BLUE}[DEBUG] Parent directory: {parent_dir}{RESET}")
        print(f"{BLUE}[DEBUG] Season 00 path: {season_00_path}{RESET}")
        print(f"{BLUE}[DEBUG] Destination file: {dest_file}{RESET}")
        if umtk_root_tv:
            print(f"{BLUE}[DEBUG] Using custom umtk_root_tv: {umtk_root_tv}{RESET}")
    
    # Check if file already exists BEFORE creating directories
    if dest_file.exists():
        if debug:
            print(f"{ORANGE}[DEBUG] Placeholder file already exists for {show['title']}: {dest_file}{RESET}")
        show['used_trailer'] = False
        return True
    
    # Create parent directory if it doesn't exist
    if not parent_dir.exists():
        try:
            parent_dir.mkdir(parents=True, exist_ok=True)
            # Set proper permissions on created directory
            try:
                os.chmod(parent_dir, 0o755)
                if debug:
                    print(f"{BLUE}[DEBUG] Created parent directory: {parent_dir}{RESET}")
                    print(f"{BLUE}[DEBUG] Set permissions 755 on {parent_dir}{RESET}")
            except Exception as perm_error:
                if debug:
                    print(f"{ORANGE}[DEBUG] Could not set directory permissions: {perm_error}{RESET}")
        except Exception as e:
            print(f"{RED}Error creating parent directory {parent_dir}: {e}{RESET}")
            return False
    
    # Check if parent directory is writable
    if not os.access(parent_dir, os.W_OK):
        print(f"{RED}Error: No write permission for directory: {parent_dir}{RESET}")
        print(f"{RED}Directory owner: {get_file_owner(parent_dir)}{RESET}")
        print(f"{RED}Current user: {get_user_info()}{RESET}")
        return False
        
    try:
        season_00_path.mkdir(parents=True, exist_ok=True)
        
        # Set proper permissions on created directory
        try:
            os.chmod(season_00_path, 0o755)
            if debug:
                print(f"{BLUE}[DEBUG] Set permissions 755 on {season_00_path}{RESET}")
        except Exception as perm_error:
            if debug:
                print(f"{ORANGE}[DEBUG] Could not set directory permissions: {perm_error}{RESET}")
        
    except PermissionError as e:
        print(f"{RED}Permission error creating directory {season_00_path}: {e}{RESET}")
        print(f"{RED}Parent directory permissions: {oct(parent_dir.stat().st_mode)[-3:]}{RESET}")
        return False
    except Exception as e:
        print(f"{RED}Error creating directory {season_00_path}: {e}{RESET}")
        return False
    
    try:
        shutil.copy2(source_file, dest_file)
        
        # Set proper permissions on created file
        try:
            os.chmod(dest_file, 0o644)
            if debug:
                print(f"{BLUE}[DEBUG] Set permissions 644 on {dest_file}{RESET}")
        except Exception as perm_error:
            if debug:
                print(f"{ORANGE}[DEBUG] Could not set file permissions: {perm_error}{RESET}")
        
        size_mb = dest_file.stat().st_size / (1024 * 1024)
        print(f"{GREEN}Created placeholder for {show['title']}: {dest_file.name} ({size_mb:.1f} MB){RESET}")
        
        # Mark as trending if this is a trending show
        if show.get('is_trending', False):
            marker_file = season_00_path / ".trending"
            try:
                marker_file.touch()
                if debug:
                    print(f"{BLUE}[DEBUG] Created trending marker file: {marker_file}{RESET}")
            except Exception as e:
                if debug:
                    print(f"{ORANGE}[DEBUG] Could not create trending marker: {e}{RESET}")
        
        # Mark as placeholder (not trailer)
        show['used_trailer'] = False
        
        return True
    except Exception as e:
        print(f"{RED}Error creating placeholder for {show['title']}: {e}{RESET}")
        return False

def create_placeholder_movie(movie, debug=False, umtk_root_movies=None, is_trending=False):
    """Create placeholder video for movie"""
    if os.environ.get('DOCKER') == 'true':
        video_folder = Path('/video')
    else:
        video_folder = Path(__file__).parent / 'video'
    
    source_files = list(video_folder.glob('UMTK.*'))
    
    if not source_files:
        print(f"{RED}No UMTK video file found in video folder{RESET}")
        return False
    
    source_file = source_files[0]
    video_extension = source_file.suffix
    
    movie_path = movie.get('path')
    
    movie_title = movie.get('title', 'Unknown')
    movie_year = movie.get('year', '')
    tmdb_id = movie.get('tmdbId', '')
    
    # Use different edition tag for trending
    edition_tag = "Trending" if is_trending else "Coming Soon"
    
    folder_name = sanitize_filename(f"{movie_title} ({movie_year}) {{edition-{edition_tag}}}")
    file_name = sanitize_filename(f"{movie_title} ({movie_year}) {{tmdb-{tmdb_id}}} {{edition-{edition_tag}}}")
    
    # For trending movies without a path, use umtk_root_movies
    if not movie_path:
        if not umtk_root_movies:
            print(f"{RED}No path found for movie: {movie.get('title')} and umtk_root_movies not configured{RESET}")
            return False
        
        parent_dir = Path(umtk_root_movies)
        target_path = parent_dir / folder_name
        if debug:
            print(f"{BLUE}[DEBUG] Created path for trending movie: {target_path}{RESET}")
    elif umtk_root_movies:
        parent_dir = Path(umtk_root_movies)
        target_path = parent_dir / folder_name
    else:
        base_path = Path(movie_path)
        parent_dir = base_path.parent
        target_path = parent_dir / folder_name
    
    dest_file = target_path / f"{file_name}{video_extension}"
    
    if debug:
        print(f"{BLUE}[DEBUG] Movie path from Radarr: {movie_path}{RESET}")
        print(f"{BLUE}[DEBUG] Parent directory: {parent_dir}{RESET}")
        print(f"{BLUE}[DEBUG] Target path: {target_path}{RESET}")
        print(f"{BLUE}[DEBUG] Destination file: {dest_file}{RESET}")
        print(f"{BLUE}[DEBUG] Edition tag: {edition_tag}{RESET}")
        if umtk_root_movies:
            print(f"{BLUE}[DEBUG] Using custom umtk_root_movies: {umtk_root_movies}{RESET}")

    if not parent_dir.exists():
        try:
            parent_dir.mkdir(parents=True, exist_ok=True)
            try:
                os.chmod(parent_dir, 0o755)
                if debug:
                    print(f"{BLUE}[DEBUG] Created parent directory: {parent_dir}{RESET}")
                    print(f"{BLUE}[DEBUG] Set permissions 755 on {parent_dir}{RESET}")
            except Exception as perm_error:
                if debug:
                    print(f"{ORANGE}[DEBUG] Could not set directory permissions: {perm_error}{RESET}")
        except Exception as e:
            print(f"{RED}Error creating parent directory {parent_dir}: {e}{RESET}")
            return False
    
    if not os.access(parent_dir, os.W_OK):
        print(f"{RED}Error: No write permission for directory: {parent_dir}{RESET}")
        print(f"{RED}Directory owner: {get_file_owner(parent_dir)}{RESET}")
        print(f"{RED}Current user: {get_user_info()}{RESET}")
        return False

    if dest_file.exists():
        if debug:
            print(f"{ORANGE}[DEBUG] Placeholder file already exists for {movie['title']}{RESET}")
        return True
    
    try:
        target_path.mkdir(parents=True, exist_ok=True)
        
        try:
            os.chmod(target_path, 0o755)
            if debug:
                print(f"{BLUE}[DEBUG] Set permissions 755 on {target_path}{RESET}")
        except Exception as perm_error:
            if debug:
                print(f"{ORANGE}[DEBUG] Could not set directory permissions: {perm_error}{RESET}")
        
    except PermissionError as e:
        print(f"{RED}Permission error creating directory {target_path}: {e}{RESET}")
        print(f"{RED}Parent directory permissions: {oct(parent_dir.stat().st_mode)[-3:]}{RESET}")
        return False
    except Exception as e:
        print(f"{RED}Error creating directory {target_path}: {e}{RESET}")
        return False
    
    try:
        shutil.copy2(source_file, dest_file)
        
        try:
            os.chmod(dest_file, 0o644)
            if debug:
                print(f"{BLUE}[DEBUG] Set permissions 644 on {dest_file}{RESET}")
        except Exception as perm_error:
            if debug:
                print(f"{ORANGE}[DEBUG] Could not set file permissions: {perm_error}{RESET}")
        
        size_mb = dest_file.stat().st_size / (1024 * 1024)
        print(f"{GREEN}Created placeholder for {movie['title']}: {dest_file.name} ({size_mb:.1f} MB){RESET}")
        return True
        
    except Exception as e:
        print(f"{RED}Error creating placeholder for {movie['title']}: {e}{RESET}")
        return False

# Cleanup functions
def cleanup_tv_content(all_series, sonarr_url, api_key, tv_method, debug=False, exclude_tags=None, future_days_upcoming_shows=30, utc_offset=0, future_only_tv=False, umtk_root_tv=None, trending_monitored=None, trending_request_needed=None):
    """Cleanup TV show trailers or placeholders"""
    if debug:
        print(f"{BLUE}[DEBUG] Starting TV content cleanup process (method: {tv_method}){RESET}")
        if umtk_root_tv:
            print(f"{BLUE}[DEBUG] Using custom umtk_root_tv for cleanup: {umtk_root_tv}{RESET}")
    
    removed_count = 0
    checked_count = 0
    
    # Get current upcoming shows to compare against
    current_future_shows, current_aired_shows = find_upcoming_shows(all_series, sonarr_url, api_key, future_days_upcoming_shows, utc_offset, debug, exclude_tags, future_only_tv)
    
    # Create sets for quick lookup
    current_upcoming_titles = {show['title'] for show in current_future_shows + current_aired_shows}
    
    # Create set of trending show titles and normalized versions
    current_trending_shows = []
    if trending_monitored:
        current_trending_shows.extend(trending_monitored)
    if trending_request_needed:
        current_trending_shows.extend(trending_request_needed)
    
    current_trending_titles = {show['title'] for show in current_trending_shows}
    
    # Normalize titles for fuzzy matching
    def normalize_title(title):
        """Normalize title for comparison"""
        # Remove year in parentheses, extra spaces, and convert to lowercase
        normalized = re.sub(r'\s*\(\d{4}\)\s*', '', title)
        normalized = re.sub(r'[^\w\s]', '', normalized)  # Remove special chars
        normalized = ' '.join(normalized.lower().split())  # Normalize whitespace
        return normalized
    
    current_trending_normalized = {normalize_title(show['title']): show['title'] for show in current_trending_shows}
    
    if debug:
        print(f"{BLUE}[DEBUG] Current upcoming shows: {len(current_upcoming_titles)}{RESET}")
        print(f"{BLUE}[DEBUG] Current trending shows: {len(current_trending_titles)}{RESET}")
        if current_trending_titles:
            print(f"{BLUE}[DEBUG] Trending titles: {current_trending_titles}{RESET}")
    
    # Build a map of show folder names to series for quick lookup when using umtk_root_tv
    series_by_folder_name = {}
    if umtk_root_tv:
        for series in all_series:
            show_path = series.get('path')
            if show_path:
                # Extract folder name the same way we do when creating content
                folder_name = PureWindowsPath(show_path).name
                series_by_folder_name[folder_name] = series
                if debug:
                    print(f"{BLUE}[DEBUG] Mapped folder '{folder_name}' to series '{series['title']}'{RESET}")
    
    # Build a map of show paths to series for quick lookup (for non-custom root)
    series_by_path = {}
    for series in all_series:
        show_path = series.get('path')
        if show_path:
            series_by_path[show_path] = series
    
    # Determine directories to scan
    dirs_to_scan = []
    
    if umtk_root_tv:
        # Scan the custom root directory
        root_path = Path(umtk_root_tv)
        if root_path.exists():
            dirs_to_scan = [d for d in root_path.iterdir() if d.is_dir()]
        if debug:
            print(f"{BLUE}[DEBUG] Scanning custom root directory: {umtk_root_tv} ({len(dirs_to_scan)} show folders){RESET}")
    else:
        # Scan all series paths from Sonarr
        for series in all_series:
            show_path = series.get('path')
            if show_path:
                path_obj = Path(show_path)
                if path_obj.exists():
                    dirs_to_scan.append(path_obj)
        if debug:
            print(f"{BLUE}[DEBUG] Scanning {len(dirs_to_scan)} show directories from Sonarr{RESET}")
    
    for show_dir in dirs_to_scan:
        season_00_path = show_dir / "Season 00"
        
        # Skip if Season 00 doesn't exist
        if not season_00_path.exists():
            continue
        
        # Check if this is trending content
        is_trending = (season_00_path / ".trending").exists()
        
        # Get the show title from the folder name
        show_folder_name = show_dir.name
        
        # Try to extract title without year
        title_match = re.match(r'^(.+?)\s*\((\d{4})\)', show_folder_name)
        if title_match:
            show_title_from_folder = title_match.group(1).strip()
        else:
            show_title_from_folder = show_folder_name
        
        # Try to find the series in Sonarr
        series = None
        if umtk_root_tv:
            # For custom root, match by folder name using our lookup dictionary
            series = series_by_folder_name.get(show_folder_name)
            if debug:
                if series:
                    print(f"{BLUE}[DEBUG] Found series for folder '{show_folder_name}': {series['title']}{RESET}")
                else:
                    print(f"{BLUE}[DEBUG] No series found for folder '{show_folder_name}'{RESET}")
        else:
            # For regular paths, direct lookup
            series = series_by_path.get(str(show_dir))
        
        if debug:
            print(f"{BLUE}[DEBUG] Checking show folder: {show_folder_name} (trending: {is_trending}, in Sonarr: {series is not None}){RESET}")
        
        # Look for both trailer and coming soon files
        trailer_files = list(season_00_path.glob("*.S00E00.Trailer.*")) + list(season_00_path.glob("*.S00E00.Coming.Soon.*"))
        
        for trailer_file in trailer_files:
            checked_count += 1
            if debug:
                print(f"{BLUE}[DEBUG] Checking file: {trailer_file.name} (trending: {is_trending}){RESET}")
            
            should_remove = False
            removal_reason = ""
            display_title = series['title'] if series else show_title_from_folder
            
            # Different logic for trending vs regular content
            if is_trending:
                # For trending content, check if still in trending list
                found_in_trending = False
                
                # If we have the series from Sonarr, use its title
                if series:
                    check_title = series['title']
                else:
                    check_title = show_title_from_folder
                
                # Try exact match first
                if check_title in current_trending_titles:
                    found_in_trending = True
                    if debug:
                        print(f"{BLUE}[DEBUG] Exact match found: '{check_title}'{RESET}")
                else:
                    # Try normalized match
                    normalized_check = normalize_title(check_title)
                    
                    for trending_show in current_trending_shows:
                        normalized_trending = normalize_title(trending_show['title'])
                        
                        if normalized_check == normalized_trending:
                            found_in_trending = True
                            if debug:
                                print(f"{BLUE}[DEBUG] Normalized match found: '{normalized_check}' == '{normalized_trending}'{RESET}")
                            break
                
                if not found_in_trending:
                    should_remove = True
                    removal_reason = "no longer in trending list"
                    if debug:
                        print(f"{BLUE}[DEBUG] Not found in trending list. Check title: '{check_title}'{RESET}")
                        print(f"{BLUE}[DEBUG] Current trending titles: {current_trending_titles}{RESET}")
                elif debug:
                    print(f"{BLUE}[DEBUG] Keeping trending content for {check_title} - still in trending list{RESET}")
            else:
                # For regular content, use existing logic
                # But we need a series entry for this
                if not series:
                    # If no series found and not trending, it shouldn't exist
                    should_remove = True
                    removal_reason = "show no longer exists in Sonarr"
                    if debug:
                        print(f"{BLUE}[DEBUG] No series found in Sonarr for {show_title_from_folder}{RESET}")
                        print(f"{BLUE}[DEBUG] Folder name: {show_folder_name}{RESET}")
                        print(f"{BLUE}[DEBUG] Available folder mappings: {list(series_by_folder_name.keys())}{RESET}")
                else:
                    # Check if still in upcoming list
                    if series['title'] not in current_upcoming_titles:
                        episodes = get_sonarr_episodes(sonarr_url, api_key, series['id'])
                        
                        # Find S01E01 specifically
                        s01e01 = None
                        for ep in episodes:
                            if ep.get('seasonNumber') == 1 and ep.get('episodeNumber') == 1:
                                s01e01 = ep
                                break
                        
                        if s01e01 and s01e01.get('hasFile', False):
                            should_remove = True
                            removal_reason = "S01E01 now available"
                        elif not series.get('monitored', True):
                            should_remove = True
                            removal_reason = "show is no longer monitored"
                        elif s01e01 and not s01e01.get('monitored', False):
                            should_remove = True
                            removal_reason = "S01E01 is no longer monitored"
                        elif exclude_tags and any(tag in series.get('tags', []) for tag in exclude_tags):
                            should_remove = True
                            removal_reason = "show has excluded tags"
                        else:
                            # Check if the air date is outside the range
                            if s01e01 and s01e01.get('airDateUtc'):
                                air_date = convert_utc_to_local(s01e01.get('airDateUtc'), utc_offset)
                                cutoff_date = datetime.now(timezone.utc) + timedelta(hours=utc_offset) + timedelta(days=future_days_upcoming_shows)
                                now_local = datetime.now(timezone.utc) + timedelta(hours=utc_offset)
                                
                                if air_date > cutoff_date:
                                    should_remove = True
                                    removal_reason = f"first episode is beyond {future_days_upcoming_shows} day range"
                                elif future_only_tv and air_date < now_local:
                                    should_remove = True
                                    removal_reason = "aired show excluded due to future_only_tv=True"
                            else:
                                should_remove = True
                                removal_reason = "no valid S01E01 or air date found"
                    elif debug:
                        print(f"{BLUE}[DEBUG] Keeping content for {series['title']} - still in valid shows list{RESET}")
            
            if should_remove:
                # If using umtk_root_tv, delete the entire show folder
                if umtk_root_tv:
                    # Check write permission before attempting deletion
                    if not os.access(show_dir, os.W_OK):
                        print(f"{RED}Permission denied: Cannot remove show folder {show_dir.name} for {display_title}{RESET}")
                        print(f"{RED}Directory owner: {get_file_owner(show_dir)}{RESET}")
                        print(f"{RED}Current user: {get_user_info()}{RESET}")
                        print(f"{RED}Directory permissions: {oct(show_dir.stat().st_mode)[-3:]}{RESET}")
                        continue
                    
                    # Check parent directory write permission
                    parent_dir = show_dir.parent
                    if not os.access(parent_dir, os.W_OK):
                        print(f"{RED}Permission denied: No write access to parent directory {parent_dir}{RESET}")
                        print(f"{RED}Directory owner: {get_file_owner(parent_dir)}{RESET}")
                        print(f"{RED}Current user: {get_user_info()}{RESET}")
                        print(f"{RED}Directory permissions: {oct(parent_dir.stat().st_mode)[-3:]}{RESET}")
                        continue
                    
                    try:
                        # Ensure directory has write permission before deletion
                        try:
                            os.chmod(show_dir, 0o755)
                            if debug:
                                print(f"{BLUE}[DEBUG] Set permissions 755 on {show_dir}{RESET}")
                        except Exception as perm_err:
                            if debug:
                                print(f"{ORANGE}[DEBUG] Could not set directory permissions: {perm_err}{RESET}")
                        
                        # Calculate total size
                        total_size = sum(f.stat().st_size for f in show_dir.rglob('*') if f.is_file())
                        size_mb = total_size / (1024 * 1024)
                        
                        shutil.rmtree(show_dir)
                        
                        removed_count += 1
                        content_type = "trending content" if is_trending else "content"
                        print(f"{GREEN}Removed show folder for {display_title} - {removal_reason} ({size_mb:.1f} MB freed){RESET}")
                        if debug:
                            print(f"{BLUE}[DEBUG] Deleted entire folder: {show_dir}{RESET}")
                        
                        # Break after deleting folder since all files are gone
                        break
                        
                    except PermissionError as e:
                        print(f"{RED}Permission error removing show folder for {display_title}: {e}{RESET}")
                        print(f"{RED}Directory owner: {get_file_owner(show_dir)}{RESET}")
                        print(f"{RED}Current user: {get_user_info()}{RESET}")
                        print(f"{RED}Directory permissions: {oct(show_dir.stat().st_mode)[-3:]}{RESET}")
                    except Exception as e:
                        error_msg = str(e)
                        print(f"{RED}Error removing show folder for {display_title}: {e}{RESET}")
                        # If it's a permission error caught as generic exception, show details
                        if "Permission denied" in error_msg or "Errno 13" in error_msg:
                            print(f"{RED}Directory owner: {get_file_owner(show_dir)}{RESET}")
                            print(f"{RED}Current user: {get_user_info()}{RESET}")
                            if show_dir.exists():
                                print(f"{RED}Directory permissions: {oct(show_dir.stat().st_mode)[-3:]}{RESET}")
                else:
                    # Original behavior: just delete the file
                    # Check write permission before attempting deletion
                    if not os.access(trailer_file, os.W_OK):
                        print(f"{RED}Permission denied: Cannot remove {trailer_file.name} for {display_title}{RESET}")
                        print(f"{RED}File owner: {get_file_owner(trailer_file)}{RESET}")
                        print(f"{RED}Current user: {get_user_info()}{RESET}")
                        print(f"{RED}File permissions: {oct(trailer_file.stat().st_mode)[-3:]}{RESET}")
                        continue
                    
                    # Check parent directory write permission
                    if not os.access(season_00_path, os.W_OK):
                        print(f"{RED}Permission denied: No write access to directory {season_00_path}{RESET}")
                        print(f"{RED}Directory owner: {get_file_owner(season_00_path)}{RESET}")
                        print(f"{RED}Current user: {get_user_info()}{RESET}")
                        print(f"{RED}Directory permissions: {oct(season_00_path.stat().st_mode)[-3:]}{RESET}")
                        continue
                    
                    try:
                        # Ensure directory has write permission before deletion
                        try:
                            os.chmod(season_00_path, 0o755)
                            if debug:
                                print(f"{BLUE}[DEBUG] Set permissions 755 on {season_00_path}{RESET}")
                        except Exception as perm_err:
                            if debug:
                                print(f"{ORANGE}[DEBUG] Could not set directory permissions: {perm_err}{RESET}")
                        
                        file_size_mb = trailer_file.stat().st_size / (1024 * 1024)
                        trailer_file.unlink()
                        
                        # Also remove trending marker if it exists
                        marker_file = season_00_path / ".trending"
                        if marker_file.exists():
                            marker_file.unlink()
                            if debug:
                                print(f"{BLUE}[DEBUG] Removed trending marker{RESET}")
                        
                        removed_count += 1
                        content_type = "trending content" if is_trending else "content"
                        print(f"{GREEN}Removed {content_type} for {display_title} - {removal_reason} ({file_size_mb:.1f} MB freed){RESET}")
                        if debug:
                            print(f"{BLUE}[DEBUG] Deleted: {trailer_file}{RESET}")
                    except PermissionError as e:
                        print(f"{RED}Permission error removing content for {display_title}: {e}{RESET}")
                        print(f"{RED}File owner: {get_file_owner(trailer_file)}{RESET}")
                        print(f"{RED}Current user: {get_user_info()}{RESET}")
                        print(f"{RED}File permissions: {oct(trailer_file.stat().st_mode)[-3:]}{RESET}")
                    except Exception as e:
                        error_msg = str(e)
                        print(f"{RED}Error removing content for {display_title}: {e}{RESET}")
                        # If it's a permission error caught as generic exception, show details
                        if "Permission denied" in error_msg or "Errno 13" in error_msg:
                            print(f"{RED}File owner: {get_file_owner(trailer_file)}{RESET}")
                            print(f"{RED}Current user: {get_user_info()}{RESET}")
                            if trailer_file.exists():
                                print(f"{RED}File permissions: {oct(trailer_file.stat().st_mode)[-3:]}{RESET}")
    
    if removed_count > 0:
        print(f"{GREEN}TV cleanup complete: Removed {removed_count} item(s) from {checked_count} checked{RESET}")
    elif checked_count > 0:
        print(f"{GREEN}TV cleanup complete: No items needed removal ({checked_count} checked){RESET}")
    elif debug:
        print(f"{BLUE}[DEBUG] No TV content found to check{RESET}")

def cleanup_movie_content(all_movies, radarr_url, api_key, future_movies, released_movies, trending_monitored, trending_request_needed, movie_method, debug=False, exclude_tags=None, umtk_root_movies=None):
    """Cleanup movie trailers or placeholders"""
    if debug:
        print(f"{BLUE}[DEBUG] Starting movie content cleanup process (method: {movie_method}){RESET}")
        if umtk_root_movies:
            print(f"{BLUE}[DEBUG] Using custom umtk_root_movies for cleanup: {umtk_root_movies}{RESET}")
    
    removed_count = 0
    checked_count = 0
    
    # Create sets of current valid movie titles
    current_upcoming_titles = {movie['title'] for movie in future_movies + released_movies}
    
    # For trending, we need to be more careful with title matching
    # Store both the full movie dict and normalized titles
    current_trending_movies = trending_monitored + trending_request_needed
    current_trending_titles = {movie['title'] for movie in current_trending_movies}
    
    # Also create a normalized version for fuzzy matching
    def normalize_title(title):
        """Normalize title for comparison"""
        # Remove year in parentheses, extra spaces, and convert to lowercase
        normalized = re.sub(r'\s*\(\d{4}\)\s*', '', title)
        normalized = re.sub(r'[^\w\s]', '', normalized)  # Remove special chars
        normalized = ' '.join(normalized.lower().split())  # Normalize whitespace
        return normalized
    
    current_trending_normalized = {normalize_title(movie['title']): movie['title'] for movie in current_trending_movies}
    
    # Create a set of trending monitored titles (these use "Coming Soon" edition)
    current_trending_monitored_titles = {movie['title'] for movie in trending_monitored}
    current_trending_monitored_normalized = {normalize_title(movie['title']): movie['title'] for movie in trending_monitored}
    
    if debug:
        print(f"{BLUE}[DEBUG] Current upcoming movies: {len(current_upcoming_titles)}{RESET}")
        print(f"{BLUE}[DEBUG] Current trending movies: {len(current_trending_titles)}{RESET}")
        print(f"{BLUE}[DEBUG] Current trending monitored movies: {len(current_trending_monitored_titles)}{RESET}")
        if current_trending_titles:
            print(f"{BLUE}[DEBUG] Trending titles: {current_trending_titles}{RESET}")
    
    # Create lookup dictionaries for both edition types
    radarr_movie_lookup_coming_soon = {}
    radarr_movie_lookup_trending = {}
    
    for movie in all_movies:
        movie_path = movie.get('path')
        if not movie_path:
            continue
        
        movie_title = movie.get('title', 'Unknown')
        movie_year = movie.get('year', '')
        
        # Coming Soon edition
        folder_name_coming = sanitize_filename(f"{movie_title} ({movie_year}) {{edition-Coming Soon}}")
        if umtk_root_movies:
            folder_path_coming = Path(umtk_root_movies) / folder_name_coming
        else:
            base_path = Path(movie_path)
            parent_dir = base_path.parent
            folder_path_coming = parent_dir / folder_name_coming
        radarr_movie_lookup_coming_soon[str(folder_path_coming)] = movie
        
        # Trending edition
        folder_name_trending = sanitize_filename(f"{movie_title} ({movie_year}) {{edition-Trending}}")
        if umtk_root_movies:
            folder_path_trending = Path(umtk_root_movies) / folder_name_trending
        else:
            base_path = Path(movie_path)
            parent_dir = base_path.parent
            folder_path_trending = parent_dir / folder_name_trending
        radarr_movie_lookup_trending[str(folder_path_trending)] = movie
    
    # Determine directories to scan
    parent_dirs_to_scan = set()
    
    if umtk_root_movies:
        parent_dirs_to_scan.add(Path(umtk_root_movies))
        if debug:
            print(f"{BLUE}[DEBUG] Scanning custom root directory: {umtk_root_movies}{RESET}")
    else:
        for movie in all_movies:
            movie_path = movie.get('path')
            if movie_path:
                base_path = Path(movie_path)
                parent_dirs_to_scan.add(base_path.parent)
        
        if debug:
            print(f"{BLUE}[DEBUG] Scanning {len(parent_dirs_to_scan)} parent directories for edition folders{RESET}")
    
    for parent_dir in parent_dirs_to_scan:
        if not parent_dir.exists():
            if debug:
                print(f"{ORANGE}[DEBUG] Directory does not exist: {parent_dir}{RESET}")
            continue
            
        try:
            for folder in parent_dir.iterdir():
                if not folder.is_dir():
                    continue
                
                # Determine if this is trending or coming soon content
                is_trending = "{edition-Trending}" in folder.name
                is_coming_soon = "{edition-Coming Soon}" in folder.name
                
                if not (is_trending or is_coming_soon):
                    continue
                
                checked_count += 1
                folder_path_str = str(folder)
                
                if debug:
                    edition_type = "Trending" if is_trending else "Coming Soon"
                    print(f"{BLUE}[DEBUG] Found {edition_type} edition folder: {folder.name}{RESET}")
                
                should_remove = False
                reason = ""
                movie_title = "Unknown Movie"
                
                # Extract movie title from folder name
                try:
                    if is_trending:
                        # Remove the edition tag to get the movie title
                        movie_title = folder.name.replace(" {edition-Trending}", "")
                    else:
                        movie_title = folder.name.replace(" {edition-Coming Soon}", "")
                    
                    # Extract title without year for comparison
                    title_match = re.match(r'^(.+?)\s*\((\d{4})\)', movie_title)
                    if title_match:
                        title_without_year = title_match.group(1).strip()
                        year = title_match.group(2)
                    else:
                        title_without_year = movie_title
                        year = None
                    
                    if debug:
                        print(f"{BLUE}[DEBUG] Extracted title: '{title_without_year}', year: {year}{RESET}")
                except Exception as e:
                    if debug:
                        print(f"{ORANGE}[DEBUG] Error extracting title from folder name: {e}{RESET}")
                    title_without_year = folder.name
                
                # Use appropriate lookup based on edition type
                if is_trending:
                    lookup_dict = radarr_movie_lookup_trending
                    
                    # Check if this movie is in the current trending list
                    # First try exact match
                    found_in_trending = False
                    
                    for trending_movie in current_trending_movies:
                        trending_title = trending_movie['title']
                        
                        # Try exact match first
                        if title_without_year == trending_title:
                            found_in_trending = True
                            if debug:
                                print(f"{BLUE}[DEBUG] Exact match found: '{title_without_year}' == '{trending_title}'{RESET}")
                            break
                        
                        # Try normalized match
                        normalized_folder = normalize_title(title_without_year)
                        normalized_trending = normalize_title(trending_title)
                        
                        if normalized_folder == normalized_trending:
                            found_in_trending = True
                            if debug:
                                print(f"{BLUE}[DEBUG] Normalized match found: '{normalized_folder}' == '{normalized_trending}'{RESET}")
                            break
                    
                    if not found_in_trending:
                        should_remove = True
                        reason = "no longer in trending list"
                        if debug:
                            print(f"{BLUE}[DEBUG] Not found in trending list. Folder title: '{title_without_year}'{RESET}")
                            print(f"{BLUE}[DEBUG] Current trending titles: {current_trending_titles}{RESET}")
                    else:
                        if debug:
                            print(f"{BLUE}[DEBUG] Keeping trending content for {title_without_year} - still in trending list{RESET}")
                    
                    # Also check in Radarr lookup
                    if folder_path_str in lookup_dict:
                        movie = lookup_dict[folder_path_str]
                        movie_title = movie.get('title', movie_title)
                else:
                    # For coming soon content, check BOTH regular upcoming AND trending monitored
                    lookup_dict = radarr_movie_lookup_coming_soon
                    
                    if folder_path_str in lookup_dict:
                        movie = lookup_dict[folder_path_str]
                        movie_title = movie.get('title', 'Unknown Movie')
                        
                        # Check if it's in regular upcoming list OR trending monitored list
                        in_upcoming = movie_title in current_upcoming_titles
                        
                        # Check if it's in trending monitored (exact or normalized match)
                        in_trending_monitored = False
                        if movie_title in current_trending_monitored_titles:
                            in_trending_monitored = True
                        else:
                            # Try normalized match
                            normalized_movie = normalize_title(movie_title)
                            for trending_monitored_movie in trending_monitored:
                                if normalized_movie == normalize_title(trending_monitored_movie['title']):
                                    in_trending_monitored = True
                                    break
                        
                        if debug:
                            print(f"{BLUE}[DEBUG] Movie '{movie_title}' - in_upcoming: {in_upcoming}, in_trending_monitored: {in_trending_monitored}{RESET}")
                        
                        # Only remove if it's not in either list
                        if not in_upcoming and not in_trending_monitored:
                            if movie.get('hasFile', False):
                                should_remove = True
                                reason = "movie has been downloaded"
                            elif not movie.get('monitored', False):
                                should_remove = True
                                reason = "movie is no longer monitored"
                            elif exclude_tags and any(tag in movie.get('tags', []) for tag in exclude_tags):
                                should_remove = True
                                reason = "movie has excluded tags"
                            else:
                                should_remove = True
                                reason = "movie no longer meets criteria"
                        elif debug:
                            print(f"{BLUE}[DEBUG] Keeping content for {movie_title} - still valid (upcoming or trending monitored){RESET}")
                    else:
                        should_remove = True
                        reason = "movie no longer exists in Radarr"
                
                if should_remove:
                    # Check write permission before attempting deletion
                    if not os.access(folder, os.W_OK):
                        print(f"{RED}Permission denied: Cannot remove folder {folder.name} for {movie_title}{RESET}")
                        print(f"{RED}Directory owner: {get_file_owner(folder)}{RESET}")
                        print(f"{RED}Current user: {get_user_info()}{RESET}")
                        print(f"{RED}Directory permissions: {oct(folder.stat().st_mode)[-3:]}{RESET}")
                        continue
                    
                    # Check parent directory write permission
                    if not os.access(parent_dir, os.W_OK):
                        print(f"{RED}Permission denied: No write access to parent directory {parent_dir}{RESET}")
                        print(f"{RED}Directory owner: {get_file_owner(parent_dir)}{RESET}")
                        print(f"{RED}Current user: {get_user_info()}{RESET}")
                        print(f"{RED}Directory permissions: {oct(parent_dir.stat().st_mode)[-3:]}{RESET}")
                        continue
                    
                    try:
                        # Ensure directory has write permission before deletion
                        try:
                            os.chmod(folder, 0o755)
                            # Also ensure parent directory is writable
                            os.chmod(parent_dir, 0o755)
                            if debug:
                                print(f"{BLUE}[DEBUG] Set permissions 755 on {folder} and {parent_dir}{RESET}")
                        except Exception as perm_err:
                            if debug:
                                print(f"{ORANGE}[DEBUG] Could not set directory permissions: {perm_err}{RESET}")
                        
                        total_size = sum(f.stat().st_size for f in folder.rglob('*') if f.is_file())
                        size_mb = total_size / (1024 * 1024)
                        
                        shutil.rmtree(folder)
                        removed_count += 1
                        content_type = "trending content" if is_trending else "content"
                        print(f"{GREEN}Removed {content_type} for {movie_title} - {reason} ({size_mb:.1f} MB freed){RESET}")
                        if debug:
                            print(f"{BLUE}[DEBUG] Deleted: {folder}{RESET}")
                    except PermissionError as e:
                        print(f"{RED}Permission error removing content for {movie_title}: {e}{RESET}")
                        print(f"{RED}Directory owner: {get_file_owner(folder)}{RESET}")
                        print(f"{RED}Current user: {get_user_info()}{RESET}")
                        print(f"{RED}Directory permissions: {oct(folder.stat().st_mode)[-3:]}{RESET}")
                    except Exception as e:
                        error_msg = str(e)
                        print(f"{RED}Error removing content for {movie_title}: {e}{RESET}")
                        # If it's a permission error caught as generic exception, show details
                        if "Permission denied" in error_msg or "Errno 13" in error_msg:
                            print(f"{RED}Directory owner: {get_file_owner(folder)}{RESET}")
                            print(f"{RED}Current user: {get_user_info()}{RESET}")
                            print(f"{RED}Directory permissions: {oct(folder.stat().st_mode)[-3:]}{RESET}")
        except Exception as e:
            if debug:
                print(f"{ORANGE}[DEBUG] Error scanning directory {parent_dir}: {e}{RESET}")
            continue
    
    if removed_count > 0:
        print(f"{GREEN}Movie cleanup complete: Removed {removed_count} folder(s) from {checked_count} checked{RESET}")
    elif checked_count > 0:
        print(f"{GREEN}Movie cleanup complete: No folders needed removal ({checked_count} checked){RESET}")
    elif debug:
        print(f"{BLUE}[DEBUG] No edition folders found to check{RESET}")

# YAML creation functions
def format_date(yyyy_mm_dd, date_format, capitalize=False):
    """Format date according to specified format"""
    dt_obj = datetime.strptime(yyyy_mm_dd, "%Y-%m-%d")
    
    format_mapping = {
        'mmm': '%b',
        'mmmm': '%B',
        'mm': '%m',
        'm': '%-m',
        'dddd': '%A',
        'ddd': '%a',
        'dd': '%d',
        'd': str(dt_obj.day),
        'yyyy': '%Y',
        'yyy': '%Y',
        'yy': '%y',
        'y': '%y'
    }
    
    patterns = sorted(format_mapping.keys(), key=len, reverse=True)
    
    temp_format = date_format
    replacements = {}
    for i, pattern in enumerate(patterns):
        marker = f"@@{i}@@"
        if pattern in temp_format:
            replacements[marker] = format_mapping[pattern]
            temp_format = temp_format.replace(pattern, marker)
    
    strftime_format = temp_format
    for marker, replacement in replacements.items():
        strftime_format = strftime_format.replace(marker, replacement)
    
    try:
        result = dt_obj.strftime(strftime_format)
        if capitalize:
            result = result.upper()
        return result
    except ValueError as e:
        print(f"{RED}Error: Invalid date format '{date_format}'. Using default format.{RESET}")
        return yyyy_mm_dd

def create_overlay_yaml_tv(output_file, future_shows, aired_shows, trending_monitored, trending_request_needed, config_sections):
    """Create overlay YAML file for TV shows"""

    if not future_shows and not aired_shows and not trending_monitored and not trending_request_needed:
        with open(output_file, "w", encoding="utf-8") as f:
            f.write("#No matching shows found")
        return
    
    overlays_dict = {}
    
    # Process future shows (haven't aired yet)
    if future_shows:
        date_to_tvdb_ids = defaultdict(list)
        all_future_tvdb_ids = set()
        
        for s in future_shows:
            if s.get("tvdbId"):
                all_future_tvdb_ids.add(s['tvdbId'])
            
            if s.get("airDate"):
                date_to_tvdb_ids[s['airDate']].append(s.get('tvdbId'))
        
        backdrop_config = deepcopy(config_sections.get("backdrop", {}))
        enable_backdrop = backdrop_config.pop("enable", True)

        if enable_backdrop and all_future_tvdb_ids:
            if "name" not in backdrop_config:
                backdrop_config["name"] = "backdrop"
            all_tvdb_ids_str = ", ".join(str(i) for i in sorted(all_future_tvdb_ids) if i)
            
            overlays_dict["backdrop_future"] = {
                "overlay": backdrop_config,
                "tvdb_show": all_tvdb_ids_str
            }
        
        text_config = deepcopy(config_sections.get("text", {}))
        enable_text = text_config.pop("enable", True)
        
        if enable_text and all_future_tvdb_ids:
            date_format = text_config.pop("date_format", "yyyy-mm-dd")
            use_text = text_config.pop("use_text", "Coming Soon")
            capitalize_dates = text_config.pop("capitalize_dates", True)
            
            if date_to_tvdb_ids:
                for date_str in sorted(date_to_tvdb_ids):
                    formatted_date = format_date(date_str, date_format, capitalize_dates)
                    sub_overlay_config = deepcopy(text_config)
                    if "name" not in sub_overlay_config:
                        sub_overlay_config["name"] = f"text({use_text} {formatted_date})"
                    
                    tvdb_ids_for_date = sorted(tvdb_id for tvdb_id in date_to_tvdb_ids[date_str] if tvdb_id)
                    tvdb_ids_str = ", ".join(str(i) for i in tvdb_ids_for_date)
                    
                    block_key = f"UMTK_future_{formatted_date}"
                    overlays_dict[block_key] = {
                        "overlay": sub_overlay_config,
                        "tvdb_show": tvdb_ids_str
                    }
            else:
                sub_overlay_config = deepcopy(text_config)
                if "name" not in sub_overlay_config:
                    sub_overlay_config["name"] = f"text({use_text})"
                
                tvdb_ids_str = ", ".join(str(i) for i in sorted(all_future_tvdb_ids) if i)
                
                overlays_dict["UMTK_upcoming_shows_future"] = {
                    "overlay": sub_overlay_config,
                    "tvdb_show": tvdb_ids_str
                }
    
    # Process aired shows (have aired but not downloaded)
    if aired_shows:
        all_aired_tvdb_ids = set()
        
        for s in aired_shows:
            if s.get("tvdbId"):
                all_aired_tvdb_ids.add(s['tvdbId'])
        
        backdrop_config = deepcopy(config_sections.get("backdrop_aired", {}))
        enable_backdrop = backdrop_config.pop("enable", True)
        
        if enable_backdrop and all_aired_tvdb_ids:
            if "name" not in backdrop_config:
                backdrop_config["name"] = "backdrop"
            
            all_tvdb_ids_str = ", ".join(str(i) for i in sorted(all_aired_tvdb_ids) if i)
            
            overlays_dict["backdrop_aired"] = {
                "overlay": backdrop_config,
                "tvdb_show": all_tvdb_ids_str
            }
        
        text_config = deepcopy(config_sections.get("text_aired", {}))
        enable_text = text_config.pop("enable", True)
        
        if enable_text and all_aired_tvdb_ids:
            use_text = text_config.pop("use_text", "Available Now")
            text_config.pop("date_format", None)
            text_config.pop("capitalize_dates", None)
            
            sub_overlay_config = deepcopy(text_config)
            
            if "name" not in sub_overlay_config:
                sub_overlay_config["name"] = f"text({use_text})"
            
            tvdb_ids_str = ", ".join(str(i) for i in sorted(all_aired_tvdb_ids) if i)
            
            overlays_dict["UMTK_aired"] = {
                "overlay": sub_overlay_config,
                "tvdb_show": tvdb_ids_str
            }
    
    # Process trending monitored shows (in Sonarr, monitored, not available)
    if trending_monitored:
        all_trending_monitored_tvdb_ids = set()
        
        for s in trending_monitored:
            if s.get("tvdbId"):
                all_trending_monitored_tvdb_ids.add(s['tvdbId'])
        
        # Use the same backdrop/text config as aired shows for trending monitored
        backdrop_config = deepcopy(config_sections.get("backdrop_aired", {}))
        enable_backdrop = backdrop_config.pop("enable", True)
        
        if enable_backdrop and all_trending_monitored_tvdb_ids:
            if "name" not in backdrop_config:
                backdrop_config["name"] = "backdrop"
            
            all_tvdb_ids_str = ", ".join(str(i) for i in sorted(all_trending_monitored_tvdb_ids) if i)
            
            overlays_dict["backdrop_trending_monitored"] = {
                "overlay": backdrop_config,
                "tvdb_show": all_tvdb_ids_str
            }
        
        text_config = deepcopy(config_sections.get("text_aired", {}))
        enable_text = text_config.pop("enable", True)
        
        if enable_text and all_trending_monitored_tvdb_ids:
            use_text = text_config.pop("use_text", "Available Now")
            text_config.pop("date_format", None)
            text_config.pop("capitalize_dates", None)
            
            sub_overlay_config = deepcopy(text_config)
            
            if "name" not in sub_overlay_config:
                sub_overlay_config["name"] = f"text({use_text})"
            
            tvdb_ids_str = ", ".join(str(i) for i in sorted(all_trending_monitored_tvdb_ids) if i)
            
            overlays_dict["UMTK_trending_monitored"] = {
                "overlay": sub_overlay_config,
                "tvdb_show": tvdb_ids_str
            }
    
    # Process trending request needed shows (not in Sonarr or unmonitored)
    if trending_request_needed:
        all_trending_request_tvdb_ids = set()
        
        for s in trending_request_needed:
            if s.get("tvdbId"):
                all_trending_request_tvdb_ids.add(s['tvdbId'])
        
        backdrop_config = deepcopy(config_sections.get("backdrop_trending_request_needed", {}))
        enable_backdrop = backdrop_config.pop("enable", True)
        
        if enable_backdrop and all_trending_request_tvdb_ids:
            if "name" not in backdrop_config:
                backdrop_config["name"] = "backdrop"
            
            all_tvdb_ids_str = ", ".join(str(i) for i in sorted(all_trending_request_tvdb_ids) if i)
            
            overlays_dict["backdrop_trending_request"] = {
                "overlay": backdrop_config,
                "tvdb_show": all_tvdb_ids_str
            }
        
        text_config = deepcopy(config_sections.get("text_trending_request_needed", {}))
        enable_text = text_config.pop("enable", True)
        
        if enable_text and all_trending_request_tvdb_ids:
            use_text = text_config.pop("use_text", "Request Needed")
            text_config.pop("date_format", None)
            text_config.pop("capitalize_dates", None)
            
            sub_overlay_config = deepcopy(text_config)
            
            if "name" not in sub_overlay_config:
                sub_overlay_config["name"] = f"text({use_text})"
            
            tvdb_ids_str = ", ".join(str(i) for i in sorted(all_trending_request_tvdb_ids) if i)
            
            overlays_dict["UMTK_trending_request"] = {
                "overlay": sub_overlay_config,
                "tvdb_show": tvdb_ids_str
            }
    
    final_output = {"overlays": overlays_dict}
    
    with open(output_file, "w", encoding="utf-8") as f:
        yaml.dump(final_output, f, sort_keys=False)

def create_new_shows_overlay_yaml(output_file, shows, config_sections):
    """Create overlay YAML file for new shows"""

    if not shows:
        with open(output_file, "w", encoding="utf-8") as f:
            f.write("#No new shows found")
        return
    
    all_tvdb_ids = set()
    for s in shows:
        if s.get("tvdbId"):
            all_tvdb_ids.add(s['tvdbId'])
    
    overlays_dict = {}
    
    backdrop_config = deepcopy(config_sections.get("backdrop", {}))
    enable_backdrop = backdrop_config.pop("enable", True)

    if enable_backdrop and all_tvdb_ids:
        if "name" not in backdrop_config:
            backdrop_config["name"] = "backdrop"
        all_tvdb_ids_str = ", ".join(str(i) for i in sorted(all_tvdb_ids) if i)
        
        overlays_dict["backdrop"] = {
            "overlay": backdrop_config,
            "tvdb_show": all_tvdb_ids_str
        }
    
    text_config = deepcopy(config_sections.get("text", {}))
    enable_text = text_config.pop("enable", True)
    
    if enable_text and all_tvdb_ids:
        use_text = text_config.pop("use_text", "New Show")
        
        text_config.pop("date_format", None)
        text_config.pop("capitalize_dates", None)
        
        sub_overlay_config = deepcopy(text_config)
        if "name" not in sub_overlay_config:
            sub_overlay_config["name"] = f"text({use_text})"
        
        tvdb_ids_str = ", ".join(str(i) for i in sorted(all_tvdb_ids) if i)
        
        overlays_dict["UMTK_new_shows"] = {
            "overlay": sub_overlay_config,
            "tvdb_show": tvdb_ids_str
        }
    
    final_output = {"overlays": overlays_dict}
    
    with open(output_file, "w", encoding="utf-8") as f:
        yaml.dump(final_output, f, sort_keys=False)

def create_collection_yaml_tv(output_file, future_shows, aired_shows, config):
    """Create collection YAML file for TV shows"""
    def represent_ordereddict(dumper, data):
        return dumper.represent_mapping('tag:yaml.org,2002:map', data.items())
    
    yaml.add_representer(OrderedDict, represent_ordereddict, Dumper=yaml.SafeDumper)

    config_key = "collection_upcoming_shows"
    collection_config = {}
    collection_name = "Upcoming Shows"
    
    if config_key in config:
        collection_config = deepcopy(config[config_key])
        collection_name = collection_config.pop("collection_name", "Upcoming Shows")
    
    future_days = config.get('future_days_upcoming_shows', 30)
    if "summary" not in collection_config:
        summary = f"Shows with their first episode premiering within {future_days} days or already aired but not yet available"
    else:
        summary = collection_config.pop("summary")
    
    class QuotedString(str):
        pass

    def quoted_str_presenter(dumper, data):
        return dumper.represent_scalar('tag:yaml.org,2002:str', data, style='"')

    yaml.add_representer(QuotedString, quoted_str_presenter, Dumper=yaml.SafeDumper)

    all_shows = future_shows + aired_shows

    if not all_shows:
        plex_search_config = {
            "all": {
                "label": collection_name
            }
        }
        
        data = {
            "collections": {
                collection_name: {
                    "plex_search": plex_search_config,
                    "item_label.remove": collection_name,
                    "smart_label": collection_config.get("smart_label", "random"),
                    "build_collection": collection_config.get("build_collection", False)
                }
            }
        }
        
        with open(output_file, "w", encoding="utf-8") as f:
            yaml.dump(data, f, Dumper=yaml.SafeDumper, sort_keys=False)
        return
    
    tvdb_ids = [s['tvdbId'] for s in all_shows if s.get('tvdbId')]
    if not tvdb_ids:
        plex_search_config = {
            "all": {
                "label": collection_name
            }
        }
        
        data = {
            "collections": {
                collection_name: {
                    "plex_search": plex_search_config,
                    "non_item_remove_label": collection_name,
                    "build_collection": collection_config.get("build_collection", False)
                }
            }
        }
        
        with open(output_file, "w", encoding="utf-8") as f:
            yaml.dump(data, f, Dumper=yaml.SafeDumper, sort_keys=False)
        return

    tvdb_ids_str = ", ".join(str(i) for i in sorted(tvdb_ids))

    collection_data = {}
    collection_data["summary"] = summary
    
    for key, value in collection_config.items():
        if key == "sort_title":
            collection_data[key] = QuotedString(value)
        else:
            collection_data[key] = value
    
    if "sync_mode" not in collection_data:
        collection_data["sync_mode"] = "sync"
    
    collection_data["tvdb_show"] = tvdb_ids_str

    ordered_collection = OrderedDict()
    
    ordered_collection["summary"] = collection_data["summary"]
    if "sort_title" in collection_data:
        ordered_collection["sort_title"] = collection_data["sort_title"]
    
    for key, value in collection_data.items():
        if key not in ["summary", "sort_title", "sync_mode", "tvdb_show"]:
            ordered_collection[key] = value
    
    ordered_collection["sync_mode"] = collection_data["sync_mode"]
    ordered_collection["tvdb_show"] = collection_data["tvdb_show"]

    data = {
        "collections": {
            collection_name: ordered_collection
        }
    }

    with open(output_file, "w", encoding="utf-8") as f:
        yaml.dump(data, f, Dumper=yaml.SafeDumper, sort_keys=False)

def create_overlay_yaml_movies(output_file, future_movies, released_movies, trending_monitored, trending_request_needed, config_sections):
    """Create overlay YAML file for movies"""

    if not future_movies and not released_movies and not trending_monitored and not trending_request_needed:
        with open(output_file, "w", encoding="utf-8") as f:
            f.write("#No matching movies found")
        return
    
    overlays_dict = {}
    
    # Process future movies (upcoming releases)
    if future_movies:
        date_to_tmdb_ids = defaultdict(list)
        all_future_tmdb_ids = set()
        
        for m in future_movies:
            if m.get("tmdbId"):
                all_future_tmdb_ids.add(m['tmdbId'])
                if m.get("releaseDate"):
                    date_to_tmdb_ids[m['releaseDate']].append(m.get('tmdbId'))
        
        backdrop_config = deepcopy(config_sections.get("backdrop_future", {}))
        enable_backdrop = backdrop_config.pop("enable", True)
        
        if enable_backdrop and all_future_tmdb_ids:
            if "name" not in backdrop_config:
                backdrop_config["name"] = "backdrop"
            
            all_tmdb_ids_str = ", ".join(str(i) for i in sorted(all_future_tmdb_ids) if i)
            
            overlays_dict["backdrop_future"] = {
                "overlay": backdrop_config,
                "tmdb_movie": all_tmdb_ids_str
            }
        
        text_config = deepcopy(config_sections.get("text_future", {}))
        enable_text = text_config.pop("enable", True)
        
        if enable_text and all_future_tmdb_ids:
            date_format = text_config.pop("date_format", "yyyy-mm-dd")
            use_text = text_config.pop("use_text", "Coming Soon")
            capitalize_dates = text_config.pop("capitalize_dates", True)
            
            for date_str in sorted(date_to_tmdb_ids):
                formatted_date = format_date(date_str, date_format, capitalize_dates)
                sub_overlay_config = deepcopy(text_config)
                
                if "name" not in sub_overlay_config:
                    sub_overlay_config["name"] = f"text({use_text} {formatted_date})"
                else:
                    base_name = sub_overlay_config["name"]
                    sub_overlay_config["name"] = f"{base_name}({use_text} {formatted_date})"
                
                tmdb_ids_for_date = sorted(tmdb_id for tmdb_id in date_to_tmdb_ids[date_str] if tmdb_id)
                tmdb_ids_str = ", ".join(str(i) for i in tmdb_ids_for_date)
                
                block_key = f"UMTK_future_{formatted_date}"
                overlays_dict[block_key] = {
                    "overlay": sub_overlay_config,
                    "tmdb_movie": tmdb_ids_str
                }
    
    # Process released movies (released but not available)
    if released_movies:
        all_released_tmdb_ids = set()
        
        for m in released_movies:
            if m.get("tmdbId"):
                all_released_tmdb_ids.add(m['tmdbId'])
        
        backdrop_config = deepcopy(config_sections.get("backdrop_released", {}))
        enable_backdrop = backdrop_config.pop("enable", True)
        
        if enable_backdrop and all_released_tmdb_ids:
            if "name" not in backdrop_config:
                backdrop_config["name"] = "backdrop"
            
            all_tmdb_ids_str = ", ".join(str(i) for i in sorted(all_released_tmdb_ids) if i)
            
            overlays_dict["backdrop_released"] = {
                "overlay": backdrop_config,
                "tmdb_movie": all_tmdb_ids_str
            }
        
        text_config = deepcopy(config_sections.get("text_released", {}))
        enable_text = text_config.pop("enable", True)
        
        if enable_text and all_released_tmdb_ids:
            use_text = text_config.pop("use_text", "Available Now")
            text_config.pop("date_format", None)
            text_config.pop("capitalize_dates", None)
            
            sub_overlay_config = deepcopy(text_config)
            
            if "name" not in sub_overlay_config:
                sub_overlay_config["name"] = f"text({use_text})"
            else:
                base_name = sub_overlay_config["name"]
                sub_overlay_config["name"] = f"{base_name}({use_text})"
            
            tmdb_ids_str = ", ".join(str(i) for i in sorted(all_released_tmdb_ids) if i)
            
            overlays_dict["UMTK_released"] = {
                "overlay": sub_overlay_config,
                "tmdb_movie": tmdb_ids_str
            }
    
    # Process trending monitored movies (in Radarr, monitored, not available)
    if trending_monitored:
        all_trending_monitored_tmdb_ids = set()
        
        for m in trending_monitored:
            if m.get("tmdbId"):
                all_trending_monitored_tmdb_ids.add(m['tmdbId'])
        
        # Use the same backdrop/text config as released movies for trending monitored
        backdrop_config = deepcopy(config_sections.get("backdrop_released", {}))
        enable_backdrop = backdrop_config.pop("enable", True)
        
        if enable_backdrop and all_trending_monitored_tmdb_ids:
            if "name" not in backdrop_config:
                backdrop_config["name"] = "backdrop"
            
            all_tmdb_ids_str = ", ".join(str(i) for i in sorted(all_trending_monitored_tmdb_ids) if i)
            
            overlays_dict["backdrop_trending_monitored"] = {
                "overlay": backdrop_config,
                "tmdb_movie": all_tmdb_ids_str
            }
        
        text_config = deepcopy(config_sections.get("text_released", {}))
        enable_text = text_config.pop("enable", True)
        
        if enable_text and all_trending_monitored_tmdb_ids:
            use_text = text_config.pop("use_text", "Available Now")
            text_config.pop("date_format", None)
            text_config.pop("capitalize_dates", None)
            
            sub_overlay_config = deepcopy(text_config)
            
            if "name" not in sub_overlay_config:
                sub_overlay_config["name"] = f"text({use_text})"
            else:
                base_name = sub_overlay_config["name"]
                sub_overlay_config["name"] = f"{base_name}({use_text})"
            
            tmdb_ids_str = ", ".join(str(i) for i in sorted(all_trending_monitored_tmdb_ids) if i)
            
            overlays_dict["UMTK_trending_monitored"] = {
                "overlay": sub_overlay_config,
                "tmdb_movie": tmdb_ids_str
            }
    
    # Process trending request needed movies (not in Radarr or unmonitored)
    if trending_request_needed:
        all_trending_request_tmdb_ids = set()
        
        for m in trending_request_needed:
            if m.get("tmdbId"):
                all_trending_request_tmdb_ids.add(m['tmdbId'])
        
        backdrop_config = deepcopy(config_sections.get("backdrop_trending_request_needed", {}))
        enable_backdrop = backdrop_config.pop("enable", True)
        
        if enable_backdrop and all_trending_request_tmdb_ids:
            if "name" not in backdrop_config:
                backdrop_config["name"] = "backdrop"
            
            all_tmdb_ids_str = ", ".join(str(i) for i in sorted(all_trending_request_tmdb_ids) if i)
            
            overlays_dict["backdrop_trending_request"] = {
                "overlay": backdrop_config,
                "tmdb_movie": all_tmdb_ids_str
            }
        
        text_config = deepcopy(config_sections.get("text_trending_request_needed", {}))
        enable_text = text_config.pop("enable", True)
        
        if enable_text and all_trending_request_tmdb_ids:
            use_text = text_config.pop("use_text", "Request Needed")
            text_config.pop("date_format", None)
            text_config.pop("capitalize_dates", None)
            
            sub_overlay_config = deepcopy(text_config)
            
            if "name" not in sub_overlay_config:
                sub_overlay_config["name"] = f"text({use_text})"
            else:
                base_name = sub_overlay_config["name"]
                sub_overlay_config["name"] = f"{base_name}({use_text})"
            
            tmdb_ids_str = ", ".join(str(i) for i in sorted(all_trending_request_tmdb_ids) if i)
            
            overlays_dict["UMTK_trending_request"] = {
                "overlay": sub_overlay_config,
                "tmdb_movie": tmdb_ids_str
            }
    
    final_output = {"overlays": overlays_dict}
    
    with open(output_file, "w", encoding="utf-8") as f:
        yaml.dump(final_output, f, sort_keys=False)

def create_collection_yaml_movies(output_file, future_movies, released_movies, config):
    """Create collection YAML file for movies"""
    def represent_ordereddict(dumper, data):
        return dumper.represent_mapping('tag:yaml.org,2002:map', data.items())
    
    yaml.add_representer(OrderedDict, represent_ordereddict, Dumper=yaml.SafeDumper)

    config_key = "collection_upcoming_movies"
    collection_config = {}
    collection_name = "Upcoming Movies"
    
    if config_key in config:
        collection_config = deepcopy(config[config_key])
        collection_name = collection_config.pop("collection_name", "Upcoming Movies")
    
    if "summary" not in collection_config:
        future_days = config.get('future_days_upcoming_movies', 30)
        summary = f"Movies releasing within {future_days} days or already released but not yet available"
        collection_config["summary"] = summary
    
    class QuotedString(str):
        pass

    def quoted_str_presenter(dumper, data):
        return dumper.represent_scalar('tag:yaml.org,2002:str', data, style='"')

    yaml.add_representer(QuotedString, quoted_str_presenter, Dumper=yaml.SafeDumper)

    all_movies = future_movies + released_movies
    
    if not all_movies:
        fallback_config = {
            "plex_search": {
                "all": {
                    "label": collection_name
                }
            },
            "item_label.remove": collection_name,
            "smart_label": "random",
            "build_collection": False
        }
        
        fallback_config.update(collection_config)
        
        data = {
            "collections": {
                collection_name: fallback_config
            }
        }
        
        with open(output_file, "w", encoding="utf-8") as f:
            yaml.dump(data, f, Dumper=yaml.SafeDumper, sort_keys=False)
        return
    
    tmdb_ids = [m['tmdbId'] for m in all_movies if m.get('tmdbId')]
    if not tmdb_ids:
        fallback_config = {
            "plex_search": {
                "all": {
                    "label": collection_name
                }
            },
            "non_item_remove_label": collection_name,
            "build_collection": False
        }
        
        fallback_config.update(collection_config)
        
        data = {
            "collections": {
                collection_name: fallback_config
            }
        }
        
        with open(output_file, "w", encoding="utf-8") as f:
            yaml.dump(data, f, Dumper=yaml.SafeDumper, sort_keys=False)
        return

    tmdb_ids_str = ", ".join(str(i) for i in sorted(tmdb_ids))

    collection_data = deepcopy(collection_config)
    
    if "sync_mode" not in collection_data:
        collection_data["sync_mode"] = "sync"
    
    collection_data["tmdb_movie"] = tmdb_ids_str

    ordered_collection = OrderedDict()
    
    if "summary" in collection_data:
        ordered_collection["summary"] = collection_data["summary"]
    
    if "sort_title" in collection_data:
        if isinstance(collection_data["sort_title"], str):
            ordered_collection["sort_title"] = QuotedString(collection_data["sort_title"])
        else:
            ordered_collection["sort_title"] = collection_data["sort_title"]
    
    for key, value in collection_data.items():
        if key not in ["summary", "sort_title", "sync_mode", "tmdb_movie"]:
            ordered_collection[key] = value
    
    ordered_collection["sync_mode"] = collection_data["sync_mode"]
    ordered_collection["tmdb_movie"] = collection_data["tmdb_movie"]

    data = {
        "collections": {
            collection_name: ordered_collection
        }
    }

    with open(output_file, "w", encoding="utf-8") as f:
        yaml.dump(data, f, Dumper=yaml.SafeDumper, sort_keys=False)

def create_trending_collection_yaml_movies(output_file, mdblist_url, mdblist_limit, config):
    """Create trending collection YAML file for movies"""


    def represent_ordereddict(dumper, data):
        return dumper.represent_mapping('tag:yaml.org,2002:map', data.items())
    
    yaml.add_representer(OrderedDict, represent_ordereddict, Dumper=yaml.SafeDumper)

    config_key = "collection_trending_movies"
    collection_config = {}
    collection_name = "Trending Movies"
    
    if config_key in config:
        collection_config = deepcopy(config[config_key])
        collection_name = collection_config.pop("collection_name", "Trending Movies")
    
    class QuotedString(str):
        pass

    def quoted_str_presenter(dumper, data):
        return dumper.represent_scalar('tag:yaml.org,2002:str', data, style='"')

    yaml.add_representer(QuotedString, quoted_str_presenter, Dumper=yaml.SafeDumper)

    collection_data = deepcopy(collection_config)
    
    # Add mdblist_list configuration
    collection_data["mdblist_list"] = {
        "url": mdblist_url,
        "limit": mdblist_limit
    }
    
    if "sync_mode" not in collection_data:
        collection_data["sync_mode"] = "sync"

    ordered_collection = OrderedDict()
    
    # Add mdblist_list first
    ordered_collection["mdblist_list"] = collection_data["mdblist_list"]
    
    # Add other configuration items
    for key, value in collection_data.items():
        if key not in ["mdblist_list", "sync_mode"]:
            if key == "sort_title" and isinstance(value, str):
                ordered_collection[key] = QuotedString(value)
            else:
                ordered_collection[key] = value
    
    # Add sync_mode last
    ordered_collection["sync_mode"] = collection_data["sync_mode"]

    data = {
        "collections": {
            collection_name: ordered_collection
        }
    }

    with open(output_file, "w", encoding="utf-8") as f:
        yaml.dump(data, f, Dumper=yaml.SafeDumper, sort_keys=False)


def create_trending_collection_yaml_tv(output_file, mdblist_url, mdblist_limit, config):
    """Create trending collection YAML file for TV shows"""
    def represent_ordereddict(dumper, data):
        return dumper.represent_mapping('tag:yaml.org,2002:map', data.items())
    
    yaml.add_representer(OrderedDict, represent_ordereddict, Dumper=yaml.SafeDumper)

    config_key = "collection_trending_shows"
    collection_config = {}
    collection_name = "Trending Shows"
    
    if config_key in config:
        collection_config = deepcopy(config[config_key])
        collection_name = collection_config.pop("collection_name", "Trending Shows")
    
    class QuotedString(str):
        pass

    def quoted_str_presenter(dumper, data):
        return dumper.represent_scalar('tag:yaml.org,2002:str', data, style='"')

    yaml.add_representer(QuotedString, quoted_str_presenter, Dumper=yaml.SafeDumper)

    collection_data = deepcopy(collection_config)
    
    # Add mdblist_list configuration
    collection_data["mdblist_list"] = {
        "url": mdblist_url,
        "limit": mdblist_limit
    }
    
    if "sync_mode" not in collection_data:
        collection_data["sync_mode"] = "sync"

    ordered_collection = OrderedDict()
    
    # Add mdblist_list first
    ordered_collection["mdblist_list"] = collection_data["mdblist_list"]
    
    # Add other configuration items
    for key, value in collection_data.items():
        if key not in ["mdblist_list", "sync_mode"]:
            if key == "sort_title" and isinstance(value, str):
                ordered_collection[key] = QuotedString(value)
            else:
                ordered_collection[key] = value
    
    # Add sync_mode last
    ordered_collection["sync_mode"] = collection_data["sync_mode"]

    data = {
        "collections": {
            collection_name: ordered_collection
        }
    }

    with open(output_file, "w", encoding="utf-8") as f:
        yaml.dump(data, f, Dumper=yaml.SafeDumper, sort_keys=False)

def create_top10_overlay_yaml_movies(output_file, mdblist_items, config_sections):
    """Create Top 10 overlay YAML file for movies based on MDBList ranking"""
    if not mdblist_items:
        with open(output_file, "w", encoding="utf-8") as f:
            f.write("#No trending movies found for Top 10")
        return
    
    # Limit to top 10 items
    top_items = mdblist_items[:10]
    
    overlays_dict = {}
    
    # Get all TMDB IDs for the backdrop overlay
    all_tmdb_ids = []
    for item in top_items:
        tmdb_id = item.get('id') or item.get('tmdb_id')
        if tmdb_id:
            all_tmdb_ids.append(str(tmdb_id))
    
    # Create backdrop overlay
    backdrop_config = deepcopy(config_sections.get("backdrop", {}))
    enable_backdrop = backdrop_config.pop("enable", True)
    
    if enable_backdrop and all_tmdb_ids:
        if "name" not in backdrop_config:
            backdrop_config["name"] = "backdrop"
        
        tmdb_ids_str = ", ".join(all_tmdb_ids)
        
        overlays_dict["backdrop_trending_top_10"] = {
            "overlay": backdrop_config,
            "tmdb_movie": tmdb_ids_str
        }
    
    # Create individual text overlays for each ranked item
    text_config = deepcopy(config_sections.get("text", {}))
    enable_text = text_config.pop("enable", True)
    
    # Remove use_text if it exists (we don't use it for Top 10)
    text_config.pop("use_text", None)
    text_config.pop("date_format", None)
    text_config.pop("capitalize_dates", None)
    
    if enable_text:
        for item in top_items:
            rank = item.get('rank')
            tmdb_id = item.get('id') or item.get('tmdb_id')
            
            if not rank or not tmdb_id:
                continue
            
            # Create a copy of text config for this rank
            rank_text_config = deepcopy(text_config)
            rank_text_config["name"] = f"text({rank})"
            
            block_key = f"trending_top10_{rank}"
            overlays_dict[block_key] = {
                "overlay": rank_text_config,
                "tmdb_movie": str(tmdb_id)
            }
    
    final_output = {"overlays": overlays_dict}
    
    with open(output_file, "w", encoding="utf-8") as f:
        yaml.dump(final_output, f, sort_keys=False)


def create_top10_overlay_yaml_tv(output_file, mdblist_items, config_sections):
    """Create Top 10 overlay YAML file for TV shows based on MDBList ranking"""
    if not mdblist_items:
        with open(output_file, "w", encoding="utf-8") as f:
            f.write("#No trending shows found for Top 10")
        return
    
    # Limit to top 10 items
    top_items = mdblist_items[:10]
    
    overlays_dict = {}
    
    # Get all TVDB IDs for the backdrop overlay
    all_tvdb_ids = []
    for item in top_items:
        tvdb_id = item.get('tvdb_id')
        if tvdb_id:
            all_tvdb_ids.append(str(tvdb_id))
    
    # Create backdrop overlay
    backdrop_config = deepcopy(config_sections.get("backdrop", {}))
    enable_backdrop = backdrop_config.pop("enable", True)
    
    if enable_backdrop and all_tvdb_ids:
        if "name" not in backdrop_config:
            backdrop_config["name"] = "backdrop"
        
        tvdb_ids_str = ", ".join(all_tvdb_ids)
        
        overlays_dict["backdrop_trending_top_10"] = {
            "overlay": backdrop_config,
            "tvdb_show": tvdb_ids_str
        }
    
    # Create individual text overlays for each ranked item
    text_config = deepcopy(config_sections.get("text", {}))
    enable_text = text_config.pop("enable", True)
    
    # Remove use_text if it exists (we don't use it for Top 10)
    text_config.pop("use_text", None)
    text_config.pop("date_format", None)
    text_config.pop("capitalize_dates", None)
    
    if enable_text:
        for item in top_items:
            rank = item.get('rank')
            tvdb_id = item.get('tvdb_id')
            
            if not rank or not tvdb_id:
                continue
            
            # Create a copy of text config for this rank
            rank_text_config = deepcopy(text_config)
            rank_text_config["name"] = f"text({rank})"
            
            block_key = f"trending_top10_{rank}"
            overlays_dict[block_key] = {
                "overlay": rank_text_config,
                "tvdb_show": str(tvdb_id)
            }
    
    final_output = {"overlays": overlays_dict}
    
    with open(output_file, "w", encoding="utf-8") as f:
        yaml.dump(final_output, f, sort_keys=False)

def sanitize_sort_title(title):
    """Sanitize title for sort_title by removing special characters"""
    # Remove special characters but keep spaces
    sanitized = re.sub(r'[:\'"()\[\]{}<>|/\\?*]', '', title)
    # Clean up multiple spaces
    sanitized = ' '.join(sanitized.split())
    return sanitized.strip()

def create_tv_metadata_yaml(output_file, all_shows_with_content, config, debug=False, sonarr_url=None, api_key=None, all_series=None, sonarr_timeout=90):
    """Create metadata YAML file for TV shows"""
    # Read existing metadata file to track previously modified shows
    previously_modified_tvdb_ids = set()
    try:
        with open(output_file, 'r', encoding='utf-8') as f:
            existing_data = yaml.safe_load(f)
            if existing_data and 'metadata' in existing_data:
                # Only include shows that have sort_title starting with !yyyymmdd
                for tvdb_id, metadata in existing_data['metadata'].items():
                    sort_title = metadata.get('sort_title', '')
                    # Check if sort_title starts with ! followed by 8 digits
                    if sort_title and sort_title.startswith('!') and len(sort_title) > 9:
                        date_part = sort_title[1:9]  # Extract the 8 characters after !
                        if date_part.isdigit():
                            previously_modified_tvdb_ids.add(tvdb_id)
    except FileNotFoundError:
        pass  # First run, no existing file
    except Exception as e:
        if debug:
            print(f"{ORANGE}[DEBUG] Warning: Could not read existing metadata file: {str(e)}{RESET}")
    
    append_dates = str(config.get("append_dates_to_sort_titles", "true")).lower() == "true"
    
    metadata_dict = {}
    current_tvdb_ids = set()
    
    for show in all_shows_with_content:
        tvdb_id = show.get('tvdbId')
        if not tvdb_id:
            continue
        
        current_tvdb_ids.add(tvdb_id)
        
        # Determine if this show used a trailer or placeholder
        used_trailer = show.get('used_trailer', False)
        episode_title = "Trailer" if used_trailer else "Coming Soon"
        
        show_metadata = {
            "episodes": {
                "S00E00": {
                    "title": episode_title
                }
            }
        }
        
        # Add sort_title if append_dates is enabled
        if append_dates:
            air_date = show.get('airDate')
            show_title = show.get('title', 'Unknown')
            
            if air_date:
                # Convert YYYY-MM-DD to YYYYMMDD
                date_str = air_date.replace('-', '')
                sanitized_title = sanitize_sort_title(show_title)
                sort_title = f"!{date_str} {sanitized_title}"
                show_metadata["sort_title"] = sort_title
                
                if debug:
                    print(f"{BLUE}[DEBUG] TV metadata for {show_title}: sort_title = {sort_title}, episode_title = {episode_title}{RESET}")
        
        metadata_dict[tvdb_id] = show_metadata
    
    # Find shows that were previously modified but are no longer in current matches
    # These need to have their sort_title reverted to original title
    shows_to_revert = previously_modified_tvdb_ids - current_tvdb_ids
    
    if shows_to_revert and all_series:
        # Create a mapping of tvdb_id to series title from all_series
        tvdb_to_title = {series.get('tvdbId'): series.get('title', '') 
                       for series in all_series if series.get('tvdbId')}
        
        for tvdb_id in shows_to_revert:
            # Get the original title from Sonarr data
            original_title = tvdb_to_title.get(tvdb_id)
            if original_title:
                # Sanitize the title to match what we did for the prefixed version
                clean_title = sanitize_sort_title(original_title)
                
                # If we don't have existing metadata for this show, create it
                if tvdb_id not in metadata_dict:
                    metadata_dict[tvdb_id] = {}
                
                # Add the reverted sort_title
                metadata_dict[tvdb_id]["sort_title"] = clean_title
                
                if debug:
                    print(f"{BLUE}[DEBUG] Reverting sort_title for tvdb_id {tvdb_id}: {clean_title}{RESET}")
    
    if not metadata_dict:
        with open(output_file, "w", encoding="utf-8") as f:
            f.write("#No TV shows with content found")
        return
    
    if shows_to_revert:
        print(f"{GREEN}Reverting sort_title for {len(shows_to_revert)} TV shows no longer in upcoming category{RESET}")
    
    final_output = {"metadata": metadata_dict}
    
    with open(output_file, "w", encoding="utf-8") as f:
        yaml.dump(final_output, f, sort_keys=False, default_flow_style=False)

def create_movies_metadata_yaml(output_file, all_movies_with_content, config, debug=False):
    """Create metadata YAML file for movies"""
    if not all_movies_with_content:
        with open(output_file, "w", encoding="utf-8") as f:
            f.write("#No movies with content found")
        return
    
    append_dates = str(config.get("append_dates_to_sort_titles", "true")).lower() == "true"
    
    if not append_dates:
        with open(output_file, "w", encoding="utf-8") as f:
            f.write("#append_dates_to_sort_titles is disabled")
        return
    
    metadata_dict = {}
    
    for movie in all_movies_with_content:
        tmdb_id = movie.get('tmdbId')
        if not tmdb_id:
            continue
        
        release_date = movie.get('releaseDate')
        movie_title = movie.get('title', 'Unknown')
        
        if release_date:
            # Convert YYYY-MM-DD to YYYYMMDD
            date_str = release_date.replace('-', '')
            sanitized_title = sanitize_sort_title(movie_title)
            sort_title = f"!{date_str} {sanitized_title}"
            
            metadata_dict[tmdb_id] = {
                "sort_title": sort_title
            }
            
            if debug:
                print(f"{BLUE}[DEBUG] Movie metadata for {movie_title}: sort_title = {sort_title}{RESET}")
    
    final_output = {"metadata": metadata_dict}
    
    with open(output_file, "w", encoding="utf-8") as f:
        yaml.dump(final_output, f, sort_keys=False, default_flow_style=False)

def main():
    start_time = datetime.now()
    print(f"{BLUE}{'*' * 50}\n{'*' * 1}Upcoming Movies & TV Shows for Kometa {VERSION}{'*' * 1}\n{'*' * 50}{RESET}")
    
    # Add Docker detection message
    if os.environ.get('DOCKER') == 'true':
        print(f"{GREEN}Running in Docker container{RESET}")
    
    check_for_updates()
    
    config = load_config()
    radarr_timeout = config.get('radarr_timeout', 90)
    sonarr_timeout = config.get('sonarr_timeout', 90)
    
    # Get umtk root paths - handle None values properly
    umtk_root_movies = config.get('umtk_root_movies')
    umtk_root_tv = config.get('umtk_root_tv')
    
    # Convert None or empty strings to None, strip whitespace from valid strings
    if umtk_root_movies:
        umtk_root_movies = str(umtk_root_movies).strip()
        umtk_root_movies = umtk_root_movies if umtk_root_movies else None
    else:
        umtk_root_movies = None
        
    if umtk_root_tv:
        umtk_root_tv = str(umtk_root_tv).strip()
        umtk_root_tv = umtk_root_tv if umtk_root_tv else None
    else:
        umtk_root_tv = None
    
    if umtk_root_movies:
        print(f"{GREEN}Using custom movie root: {umtk_root_movies}{RESET}")
    if umtk_root_tv:
        print(f"{GREEN}Using custom TV root: {umtk_root_tv}{RESET}")
    
    # Get processing methods
    tv_method = config.get('tv', 1)
    movie_method = config.get('movies', 2)
    trending_tv_method = config.get('trending_tv', 0)
    trending_movies_method = config.get('trending_movies', 0)
    method_fallback = str(config.get("method_fallback", "false")).lower() == "true"
    
    print(f"TV processing method: {tv_method} ({'Disabled' if tv_method == 0 else 'Trailer' if tv_method == 1 else 'Placeholder'})")
    print(f"Movie processing method: {movie_method} ({'Disabled' if movie_method == 0 else 'Trailer' if movie_method == 1 else 'Placeholder'})")
    print(f"Trending TV method: {trending_tv_method} ({'Disabled' if trending_tv_method == 0 else 'Trailer' if trending_tv_method == 1 else 'Placeholder'})")
    print(f"Trending Movies method: {trending_movies_method} ({'Disabled' if trending_movies_method == 0 else 'Trailer' if trending_movies_method == 1 else 'Placeholder'})")
    print(f"Method fallback: {method_fallback}")
    print()
    
    # Check requirements based on methods
    if tv_method == 1 or movie_method == 1 or trending_tv_method == 1 or trending_movies_method == 1:
        if not check_yt_dlp_installed():
            print(f"{RED}yt-dlp is required for trailer downloading but not installed.{RESET}")
            sys.exit(1)
    
    # Check for placeholder requirements (both original methods and fallback)
    if tv_method == 2 or movie_method == 2 or trending_tv_method == 2 or trending_movies_method == 2 or \
       (method_fallback and (tv_method == 1 or movie_method == 1 or trending_tv_method == 1 or trending_movies_method == 1)):
        if not check_video_file():
            print(f"{RED}UMTK video file is required for placeholder method but not found.{RESET}")
            sys.exit(1)
    
    # Check for cookies file
    cookies_path = get_cookies_path()
    if cookies_path:
        print(f"{GREEN}Found cookies file: {cookies_path}{RESET}")
    
    # Get common configuration values
    utc_offset = float(config.get('utc_offset', 0))
    debug = str(config.get("debug", "false")).lower() == "true"
    cleanup = str(config.get("cleanup", "true")).lower() == "true"
    skip_channels = config.get("skip_channels", [])
    
    if isinstance(skip_channels, str):
        skip_channels = [ch.strip() for ch in skip_channels.split(',') if ch.strip()]
    
    print(f"UTC offset: {utc_offset} hours")
    print(f"cleanup: {cleanup}")
    print(f"debug: {debug}")
    if skip_channels:
        print(f"skip_channels: {skip_channels}")
    print()
    
    # Check if running in Docker and adjust output path
    if os.environ.get('DOCKER') == 'true':
        kometa_folder = Path('/app') / "kometa"
    else:
        kometa_folder = Path(__file__).parent / "kometa"
    
    kometa_folder.mkdir(exist_ok=True)
    
    try:
        # Initialize variables for trending
        trending_tv_monitored = []
        trending_tv_request_needed = []
        trending_movies_monitored = []
        trending_movies_request_needed = []
        
        # Determine if we need to process TV at all (either regular or trending)
        process_tv = (tv_method > 0 or trending_tv_method > 0)
        
        # Process TV Shows
        if process_tv:
            print(f"{BLUE}{'=' * 50}{RESET}")
            print(f"{BLUE}Processing TV Shows...{RESET}")
            print(f"{BLUE}{'=' * 50}{RESET}\n")
            
            sonarr_url = process_sonarr_url(config['sonarr_url'], config['sonarr_api_key'], sonarr_timeout)
            sonarr_api_key = config['sonarr_api_key']
            
            # Fetch all series once
            all_series = get_sonarr_series(sonarr_url, sonarr_api_key, sonarr_timeout)
            
            # Get exclude tags for Sonarr
            exclude_sonarr_tag_names = config.get('exclude_sonarr_tags', [])
            if isinstance(exclude_sonarr_tag_names, str):
                exclude_sonarr_tag_names = [tag.strip() for tag in exclude_sonarr_tag_names.split(',') if tag.strip()]
            
            exclude_sonarr_tag_ids = get_tag_ids_from_names(sonarr_url, sonarr_api_key, exclude_sonarr_tag_names, sonarr_timeout, debug)
            
            if debug and exclude_sonarr_tag_names:
                print(f"{BLUE}[DEBUG] Exclude Sonarr tags: {exclude_sonarr_tag_names} -> IDs: {exclude_sonarr_tag_ids}{RESET}")
            
            future_days_upcoming_shows = config.get('future_days_upcoming_shows', 30)
            recent_days_new_show = config.get('recent_days_new_show', 7)
            future_only_tv = str(config.get("future_only_tv", "false")).lower() == "true"
            
            print(f"future_days_upcoming_shows: {future_days_upcoming_shows}")
            print(f"recent_days_new_show: {recent_days_new_show}")
            print(f"future_only_tv: {future_only_tv}")
            if exclude_sonarr_tag_names:
                print(f"exclude_sonarr_tags: {', '.join(exclude_sonarr_tag_names)}")
            print()
            
            # Process regular upcoming shows if tv_method is enabled
            future_shows = []
            aired_shows = []
            new_shows = []
            all_shows_with_content = []  # Track shows that got content
            
            if tv_method > 0:
                # Find upcoming shows
                future_shows, aired_shows = find_upcoming_shows(
                    all_series, sonarr_url, sonarr_api_key, future_days_upcoming_shows, utc_offset, debug, exclude_sonarr_tag_ids, future_only_tv
                )
                
                if future_shows:
                    print(f"{GREEN}Found {len(future_shows)} future shows with first episodes within {future_days_upcoming_shows} days:{RESET}")
                    for show in future_shows:
                        print(f"- {show['title']}" + (f" ({show['year']})" if show['year'] else "") + f" - First episode: {show['airDate']}")
                else:
                    print(f"{ORANGE}No future shows found with first episodes within {future_days_upcoming_shows} days.{RESET}")
                
                if aired_shows:
                    print(f"\n{GREEN}Found {len(aired_shows)} aired shows not yet available:{RESET}")
                    for show in aired_shows:
                        print(f"- {show['title']}" + (f" ({show['year']})" if show['year'] else "") + f" - First episode aired: {show['airDate']}")
                elif not future_only_tv:
                    print(f"{ORANGE}No aired shows found that are not yet available.{RESET}")
                else:
                    print(f"{ORANGE}Aired shows excluded due to future_only_tv=True.{RESET}")
                
                # Find new shows
                print(f"\n{BLUE}Finding new shows with S01E01 downloaded...{RESET}")
                new_shows = find_new_shows(
                    all_series, sonarr_url, sonarr_api_key, recent_days_new_show, utc_offset, debug
                )
                
                if new_shows:
                    print(f"{GREEN}Found {len(new_shows)} new shows with S01E01 aired within the past {recent_days_new_show} days:{RESET}")
                    for show in new_shows:
                        print(f"- {show['title']}" + (f" ({show['year']})" if show['year'] else "") + f" - S01E01 aired: {show['airDate']}")
                else:
                    print(f"{ORANGE}No new shows found with S01E01 aired within the past {recent_days_new_show} days.{RESET}")
                
                # Process TV content based on method
                all_shows = future_shows + aired_shows
                if all_shows:
                    print(f"\n{BLUE}Processing content for upcoming shows...{RESET}")
                    successful = 0
                    failed = 0
                    skipped_existing = 0
                    fallback_used = 0
                    
                    for show in all_shows:
                        print(f"\nProcessing: {show['title']}")
                        
                        # Check if content already exists
                        show_path = show.get('path')
                        if show_path:
                            if umtk_root_tv:
                                # Use PureWindowsPath to handle Windows paths from Sonarr
                                show_name = PureWindowsPath(show_path).name
                                season_00_path = Path(umtk_root_tv) / show_name / "Season 00"
                            else:
                                season_00_path = Path(show_path) / "Season 00"
                            
                            clean_title = "".join(c for c in show['title'] if c.isalnum() or c in (' ', '-', '_')).rstrip()
                            
                            # Check for both trailer and coming soon files
                            trailer_pattern = f"{clean_title}.S00E00.Trailer.*"
                            coming_soon_pattern = f"{clean_title}.S00E00.Coming.Soon.*"
                            existing_trailers = []
                            if season_00_path.exists():
                                existing_trailers = list(season_00_path.glob(trailer_pattern)) + list(season_00_path.glob(coming_soon_pattern))
                            
                            if existing_trailers:
                                existing_file = existing_trailers[0]
                                # Determine if it's a trailer or placeholder
                                show['used_trailer'] = '.Trailer.' in existing_file.name
                                print(f"{GREEN}Content already exists for {show['title']}: {existing_file.name} - skipping{RESET}")
                                skipped_existing += 1
                                successful += 1
                                all_shows_with_content.append(show)
                                continue
                        
                        # Process based on method
                        success = False
                        
                        if tv_method == 1:  # Trailer
                            trailer_info = search_trailer_on_youtube(
                                show['title'], 
                                show.get('year'), 
                                show.get('imdbId'),
                                debug,
                                skip_channels
                            )
                            
                            if trailer_info:
                                print(f"Found trailer: {trailer_info['video_title']} ({trailer_info['duration']}) by {trailer_info['uploader']}")
                                success = download_trailer_tv(show, trailer_info, debug, umtk_root_tv)
                            else:
                                print(f"{ORANGE}No suitable trailer found for {show['title']}{RESET}")
                            
                            # If trailer method failed and fallback is enabled, try placeholder
                            if not success and method_fallback:
                                print(f"{ORANGE}Trailer method failed, attempting fallback to placeholder method...{RESET}")
                                success = create_placeholder_tv(show, debug, umtk_root_tv)
                                if success:
                                    fallback_used += 1
                                    print(f"{GREEN}Fallback to placeholder successful for {show['title']}{RESET}")
                        
                        elif tv_method == 2:  # Placeholder
                            success = create_placeholder_tv(show, debug, umtk_root_tv)
                        
                        if success:
                            successful += 1
                            all_shows_with_content.append(show)
                        else:
                            failed += 1
                    
                    print(f"\n{GREEN}TV content processing summary:{RESET}")
                    print(f"Successful: {successful}")
                    print(f"Skipped (already exist): {skipped_existing}")
                    if fallback_used > 0:
                        print(f"Fallback used: {fallback_used}")
                    print(f"Failed: {failed}")
            
            # Process Trending TV Shows
            if trending_tv_method > 0:
                print(f"\n{BLUE}{'=' * 50}{RESET}")
                print(f"{BLUE}Processing Trending TV Shows...{RESET}")
                print(f"{BLUE}{'=' * 50}{RESET}\n")
                
                mdblist_api_key = config.get('mdblist_api_key')
                mdblist_tv_url = config.get('mdblist_tv')
                mdblist_tv_limit = config.get('mdblist_tv_limit', 10)
                
                if not mdblist_api_key:
                    print(f"{RED}Error: mdblist_api_key not configured{RESET}")
                elif not mdblist_tv_url:
                    print(f"{RED}Error: mdblist_tv not configured{RESET}")
                else:
                    print(f"MDBList TV URL: {mdblist_tv_url}")
                    print(f"MDBList TV Limit: {mdblist_tv_limit}")
                    print()
                    
                    # Fetch trending shows from MDBList
                    print(f"{BLUE}Fetching trending TV shows from MDBList...{RESET}")
                    mdblist_tv_items = fetch_mdblist_items(mdblist_tv_url, mdblist_api_key, mdblist_tv_limit, debug)
                    
                    if mdblist_tv_items:
                        print(f"{GREEN}Fetched {len(mdblist_tv_items)} trending TV shows from MDBList{RESET}")
                        
                        # Process trending shows
                        trending_tv_monitored, trending_tv_request_needed = process_trending_tv(
                            mdblist_tv_items, all_series, sonarr_url, sonarr_api_key, debug
                        )
                        
                        if trending_tv_monitored:
                            print(f"\n{GREEN}Found {len(trending_tv_monitored)} trending shows that are monitored but not available:{RESET}")
                            for show in trending_tv_monitored:
                                print(f"- {show['title']}" + (f" ({show['year']})" if show['year'] else ""))
                        else:
                            print(f"{ORANGE}No trending shows found that are monitored but not available.{RESET}")
                        
                        if trending_tv_request_needed:
                            print(f"\n{GREEN}Found {len(trending_tv_request_needed)} trending shows that need to be requested:{RESET}")
                            for show in trending_tv_request_needed:
                                print(f"- {show['title']}" + (f" ({show['year']})" if show['year'] else ""))
                        else:
                            print(f"{ORANGE}No trending shows found that need to be requested.{RESET}")
                        
                        # Process trending TV content
                        all_trending_tv = trending_tv_monitored + trending_tv_request_needed
                        if all_trending_tv:
                            print(f"\n{BLUE}Processing content for trending TV shows...{RESET}")
                            successful = 0
                            failed = 0
                            skipped_existing = 0
                            fallback_used = 0
                            
                            for show in all_trending_tv:
                                # Mark this as a trending show
                                show['is_trending'] = True
                                
                                print(f"\nProcessing: {show['title']}")
                                
                                # Check if content already exists
                                show_path = show.get('path')
                                
                                # Determine the path to check
                                if show_path:
                                    if umtk_root_tv:
                                        # Use PureWindowsPath to handle Windows paths from Sonarr
                                        show_name = PureWindowsPath(show_path).name
                                        season_00_path = Path(umtk_root_tv) / show_name / "Season 00"
                                    else:
                                        season_00_path = Path(show_path) / "Season 00"
                                elif umtk_root_tv:
                                    # For shows without a path, construct from umtk_root_tv
                                    show_title = show.get('title', 'Unknown')
                                    show_year = show.get('year', '')
                                    if show_year:
                                        show_folder = sanitize_filename(f"{show_title} ({show_year})")
                                    else:
                                        show_folder = sanitize_filename(show_title)
                                    season_00_path = Path(umtk_root_tv) / show_folder / "Season 00"
                                else:
                                    season_00_path = None
                                
                                # Check for existing content
                                if season_00_path:
                                    clean_title = "".join(c for c in show['title'] if c.isalnum() or c in (' ', '-', '_')).rstrip()
                                    # Check for both trailer and coming soon files
                                    trailer_pattern = f"{clean_title}.S00E00.Trailer.*"
                                    coming_soon_pattern = f"{clean_title}.S00E00.Coming.Soon.*"
                                    existing_trailers = []
                                    if season_00_path.exists():
                                        existing_trailers = list(season_00_path.glob(trailer_pattern)) + list(season_00_path.glob(coming_soon_pattern))
                                    
                                    if existing_trailers:
                                        existing_file = existing_trailers[0]
                                        # Determine if it's a trailer or placeholder
                                        show['used_trailer'] = '.Trailer.' in existing_file.name
                                        print(f"{GREEN}Content already exists for {show['title']}: {existing_file.name} - skipping{RESET}")
                                        skipped_existing += 1
                                        successful += 1
                                        all_shows_with_content.append(show)
                                        continue
                                
                                # Process based on method
                                success = False
                                
                                if trending_tv_method == 1:  # Trailer
                                    trailer_info = search_trailer_on_youtube(
                                        show['title'], 
                                        show.get('year'), 
                                        show.get('imdbId'),
                                        debug,
                                        skip_channels
                                    )
                                    
                                    if trailer_info:
                                        print(f"Found trailer: {trailer_info['video_title']} ({trailer_info['duration']}) by {trailer_info['uploader']}")
                                        success = download_trailer_tv(show, trailer_info, debug, umtk_root_tv)
                                    else:
                                        print(f"{ORANGE}No suitable trailer found for {show['title']}{RESET}")
                                    
                                    # If trailer method failed and fallback is enabled, try placeholder
                                    if not success and method_fallback:
                                        print(f"{ORANGE}Trailer method failed, attempting fallback to placeholder method...{RESET}")
                                        success = create_placeholder_tv(show, debug, umtk_root_tv)
                                        if success:
                                            fallback_used += 1
                                            print(f"{GREEN}Fallback to placeholder successful for {show['title']}{RESET}")
                                
                                elif trending_tv_method == 2:  # Placeholder
                                    success = create_placeholder_tv(show, debug, umtk_root_tv)
                                
                                if success:
                                    successful += 1
                                    all_shows_with_content.append(show)
                                else:
                                    failed += 1
                            
                            print(f"\n{GREEN}Trending TV content processing summary:{RESET}")
                            print(f"Successful: {successful}")
                            print(f"Skipped (already exist): {skipped_existing}")
                            if fallback_used > 0:
                                print(f"Fallback used: {fallback_used}")
                            print(f"Failed: {failed}")
                    else:
                        print(f"{ORANGE}No trending TV shows fetched from MDBList{RESET}")
            
            # Cleanup TV content (after processing both regular and trending)
            if cleanup:
                print(f"\n{BLUE}Checking for TV content to cleanup...{RESET}")
                cleanup_tv_content(
                    all_series, sonarr_url, sonarr_api_key, tv_method, debug, 
                    exclude_sonarr_tag_ids, future_days_upcoming_shows, utc_offset, 
                    future_only_tv, umtk_root_tv, trending_tv_monitored, trending_tv_request_needed
                )
                print()
            
            # Create TV YAML files (create if either tv_method or trending_tv_method is enabled)
            if tv_method > 0 or trending_tv_method > 0:
                overlay_file = kometa_folder / "UMTK_TV_UPCOMING_SHOWS_OVERLAYS.yml"
                collection_file = kometa_folder / "UMTK_TV_UPCOMING_SHOWS_COLLECTION.yml"
                metadata_file = kometa_folder / "UMTK_TV_METADATA.yml"
                
                create_overlay_yaml_tv(
                    str(overlay_file), future_shows, aired_shows, 
                    trending_tv_monitored if trending_tv_method > 0 else [],
                    trending_tv_request_needed if trending_tv_method > 0 else [],
                    {"backdrop": config.get("backdrop_upcoming_shows", {}),
                     "text": config.get("text_upcoming_shows", {}),
                     "backdrop_aired": config.get("backdrop_upcoming_shows_aired", {}),
                     "text_aired": config.get("text_upcoming_shows_aired", {}),
                     "backdrop_trending_request_needed": config.get("backdrop_trending_shows_request_needed", {}),
                     "text_trending_request_needed": config.get("text_trending_shows_request_needed", {})}
                )
                
                if tv_method > 0:
                    new_shows_overlay_file = kometa_folder / "UMTK_TV_NEW_SHOWS_OVERLAYS.yml"
                    create_new_shows_overlay_yaml(str(new_shows_overlay_file), new_shows,
                                                  {"backdrop": config.get("backdrop_new_show", {}),
                                                   "text": config.get("text_new_show", {})})
                
                create_collection_yaml_tv(str(collection_file), future_shows, aired_shows, config)
                
                # Create metadata file
                create_tv_metadata_yaml(str(metadata_file), all_shows_with_content, config, debug, sonarr_url, sonarr_api_key, all_series, sonarr_timeout)
                
                print(f"\n{GREEN}TV YAML files created successfully{RESET}")
            
            # Create Trending TV collection YAML
            if trending_tv_method > 0:
                mdblist_tv_url = config.get('mdblist_tv')
                mdblist_tv_limit = config.get('mdblist_tv_limit', 10)
                if mdblist_tv_url:
                    trending_collection_file = kometa_folder / "UMTK_TV_TRENDING_COLLECTION.yml"
                    create_trending_collection_yaml_tv(str(trending_collection_file), mdblist_tv_url, mdblist_tv_limit, config)
                    print(f"{GREEN}Trending TV collection YAML created successfully{RESET}")

                    # Create Top 10 TV overlay YAML
                    if mdblist_tv_items:
                        top10_tv_overlay_file = kometa_folder / "UMTK_TV_TOP10_OVERLAYS.yml"
                        create_top10_overlay_yaml_tv(
                            str(top10_tv_overlay_file), 
                            mdblist_tv_items,
                            {"backdrop": config.get("backdrop_trending_top_10", {}),
                             "text": config.get("text_trending_top_10", {})}
                        )
                        print(f"{GREEN}Top 10 TV overlay YAML created successfully{RESET}")
        
        # Determine if we need to process Movies at all (either regular or trending)
        process_movies = (movie_method > 0 or trending_movies_method > 0)
        
        # Process Movies
        if process_movies:
            print(f"\n{BLUE}{'=' * 50}{RESET}")
            print(f"{BLUE}Processing Movies...{RESET}")
            print(f"{BLUE}{'=' * 50}{RESET}\n")
            
            radarr_url = process_radarr_url(config['radarr_url'], config['radarr_api_key'], radarr_timeout)
            radarr_api_key = config['radarr_api_key']
            
            # Fetch all movies once
            all_movies = get_radarr_movies(radarr_url, radarr_api_key, radarr_timeout)
            
            # Get exclude tags for Radarr
            exclude_radarr_tag_names = config.get('exclude_radarr_tags', [])
            if isinstance(exclude_radarr_tag_names, str):
                exclude_radarr_tag_names = [tag.strip() for tag in exclude_radarr_tag_names.split(',') if tag.strip()]
            
            exclude_radarr_tag_ids = get_tag_ids_from_names(radarr_url, radarr_api_key, exclude_radarr_tag_names, radarr_timeout, debug)
            
            if debug and exclude_radarr_tag_names:
                print(f"{BLUE}[DEBUG] Exclude Radarr tags: {exclude_radarr_tag_names} -> IDs: {exclude_radarr_tag_ids}{RESET}")
            
            future_days_upcoming_movies = config.get('future_days_upcoming_movies', 30)
            future_only = str(config.get("future_only", "false")).lower() == "true"
            include_inCinemas = str(config.get("include_inCinemas", "false")).lower() == "true"
            
            print(f"future_days_upcoming_movies: {future_days_upcoming_movies}")
            print(f"future_only: {future_only}")
            print(f"include_inCinemas: {include_inCinemas}")
            if exclude_radarr_tag_names:
                print(f"exclude_radarr_tags: {', '.join(exclude_radarr_tag_names)}")
            print()
            
            # Process regular upcoming movies if movie_method is enabled
            future_movies = []
            released_movies = []
            all_movies_with_content = []  # Track movies that got content
            
            if movie_method > 0:
                # Find upcoming movies
                print(f"{BLUE}Finding upcoming movies...{RESET}")
                future_movies, released_movies = find_upcoming_movies(
                    all_movies, radarr_url, radarr_api_key, future_days_upcoming_movies, utc_offset, future_only, include_inCinemas, debug, exclude_radarr_tag_ids
                )
                
                if future_movies:
                    print(f"{GREEN}Found {len(future_movies)} future movies releasing within {future_days_upcoming_movies} days:{RESET}")
                    for movie in future_movies:
                        release_info = f" - {movie['releaseType']} Release: {movie['releaseDate']}"
                        print(f"- {movie['title']}" + (f" ({movie['year']})" if movie['year'] else "") + release_info)
                else:
                    print(f"{ORANGE}No future movies found releasing within {future_days_upcoming_movies} days.{RESET}")
                
                if released_movies:
                    print(f"\n{GREEN}Found {len(released_movies)} released movies not yet available:{RESET}")
                    for movie in released_movies:
                        release_info = f" - {movie['releaseType']} Released: {movie['releaseDate']}"
                        print(f"- {movie['title']}" + (f" ({movie['year']})" if movie['year'] else "") + release_info)
                elif not future_only:
                    print(f"{ORANGE}No released movies found that are not yet available.{RESET}")
                
                # Process movie content based on method
                all_movies_to_process = future_movies + released_movies
                if all_movies_to_process:
                    print(f"\n{BLUE}Processing content for movies...{RESET}")
                    successful = 0
                    failed = 0
                    fallback_used = 0
                    
                    for movie in all_movies_to_process:
                        print(f"\nProcessing: {movie['title']}")
                        
                        # Check if content already exists
                        movie_path = movie.get('path')
                        if movie_path:
                            movie_title = movie.get('title', 'Unknown')
                            movie_year = movie.get('year', '')
                            folder_name = sanitize_filename(f"{movie_title} ({movie_year}) {{edition-Coming Soon}}")
                            
                            if umtk_root_movies:
                                coming_soon_path = Path(umtk_root_movies) / folder_name
                            else:
                                base_path = Path(movie_path)
                                parent_dir = base_path.parent
                                coming_soon_path = parent_dir / folder_name
                            
                            # Check if actual video file exists with the Coming Soon edition tag
                            if coming_soon_path.exists():
                                existing_files = list(coming_soon_path.glob("*{edition-Coming Soon}.*"))
                                if existing_files:
                                    existing_file = existing_files[0]
                                    print(f"{GREEN}Content already exists for {movie['title']}: {existing_file.name} - skipping{RESET}")
                                    successful += 1
                                    all_movies_with_content.append(movie)
                                    continue
                        
                        # Process based on method
                        success = False
                        
                        if movie_method == 1:  # Trailer
                            trailer_info = search_trailer_on_youtube(
                                movie['title'], 
                                movie.get('year'), 
                                movie.get('imdbId'),
                                debug,
                                skip_channels
                            )
                            
                            if trailer_info:
                                print(f"Found trailer: {trailer_info['video_title']} ({trailer_info['duration']}) by {trailer_info['uploader']}")
                                success = download_trailer_movie(movie, trailer_info, debug, umtk_root_movies, is_trending=False)
                            else:
                                print(f"{ORANGE}No suitable trailer found for {movie['title']}{RESET}")
                            
                            # If trailer method failed and fallback is enabled, try placeholder
                            if not success and method_fallback:
                                print(f"{ORANGE}Trailer method failed, attempting fallback to placeholder method...{RESET}")
                                success = create_placeholder_movie(movie, debug, umtk_root_movies, is_trending=False)
                                if success:
                                    fallback_used += 1
                                    print(f"{GREEN}Fallback to placeholder successful for {movie['title']}{RESET}")
                        
                        elif movie_method == 2:  # Placeholder
                            success = create_placeholder_movie(movie, debug, umtk_root_movies, is_trending=False)
                        
                        if success:
                            successful += 1
                            all_movies_with_content.append(movie)
                        else:
                            failed += 1
                    
                    print(f"\n{GREEN}Movie content processing summary:{RESET}")
                    print(f"Successful: {successful}")
                    if fallback_used > 0:
                        print(f"Fallback used: {fallback_used}")
                    print(f"Failed: {failed}")
            
            # Process Trending Movies
            if trending_movies_method > 0:
                print(f"\n{BLUE}{'=' * 50}{RESET}")
                print(f"{BLUE}Processing Trending Movies...{RESET}")
                print(f"{BLUE}{'=' * 50}{RESET}\n")
                
                mdblist_api_key = config.get('mdblist_api_key')
                mdblist_movies_url = config.get('mdblist_movies')
                mdblist_movies_limit = config.get('mdblist_movies_limit', 10)
                
                if not mdblist_api_key:
                    print(f"{RED}Error: mdblist_api_key not configured{RESET}")
                elif not mdblist_movies_url:
                    print(f"{RED}Error: mdblist_movies not configured{RESET}")
                else:
                    print(f"MDBList Movies URL: {mdblist_movies_url}")
                    print(f"MDBList Movies Limit: {mdblist_movies_limit}")
                    print()
                    
                    # Fetch trending movies from MDBList
                    print(f"{BLUE}Fetching trending movies from MDBList...{RESET}")
                    mdblist_movies_items = fetch_mdblist_items(mdblist_movies_url, mdblist_api_key, mdblist_movies_limit, debug)
                    
                    if mdblist_movies_items:
                        print(f"{GREEN}Fetched {len(mdblist_movies_items)} trending movies from MDBList{RESET}")
                        
                        # Process trending movies
                        trending_movies_monitored, trending_movies_request_needed = process_trending_movies(
                            mdblist_movies_items, all_movies, radarr_url, radarr_api_key, debug
                        )
                        
                        if trending_movies_monitored:
                            print(f"\n{GREEN}Found {len(trending_movies_monitored)} trending movies that are monitored but not available:{RESET}")
                            for movie in trending_movies_monitored:
                                print(f"- {movie['title']}" + (f" ({movie['year']})" if movie['year'] else ""))
                        else:
                            print(f"{ORANGE}No trending movies found that are monitored but not available.{RESET}")
                        
                        if trending_movies_request_needed:
                            print(f"\n{GREEN}Found {len(trending_movies_request_needed)} trending movies that need to be requested:{RESET}")
                            for movie in trending_movies_request_needed:
                                print(f"- {movie['title']}" + (f" ({movie['year']})" if movie['year'] else ""))
                        else:
                            print(f"{ORANGE}No trending movies found that need to be requested.{RESET}")
                        
                        # Process trending movie content
                        all_trending_movies = trending_movies_monitored + trending_movies_request_needed
                        if all_trending_movies:
                            print(f"\n{BLUE}Processing content for trending movies...{RESET}")
                            successful = 0
                            failed = 0
                            skipped_existing = 0
                            fallback_used = 0
                            
                            for movie in all_trending_movies:
                                print(f"\nProcessing: {movie['title']}")
                                
                                # Determine if this is a request needed movie
                                is_request_needed = movie in trending_movies_request_needed
                                
                                # Check if content already exists
                                movie_path = movie.get('path')
                                content_exists = False
                                
                                if movie_path or umtk_root_movies:
                                    movie_title = movie.get('title', 'Unknown')
                                    movie_year = movie.get('year', '')
                                    
                                    # Check for Trending edition
                                    edition_tag = "Trending" if is_request_needed else "Coming Soon"
                                    folder_name = sanitize_filename(f"{movie_title} ({movie_year}) {{edition-{edition_tag}}}")
                                    
                                    if umtk_root_movies:
                                        target_path = Path(umtk_root_movies) / folder_name
                                    elif movie_path:
                                        base_path = Path(movie_path)
                                        parent_dir = base_path.parent
                                        target_path = parent_dir / folder_name
                                    else:
                                        target_path = None
                                    
                                    if target_path and target_path.exists():
                                        existing_files = list(target_path.glob(f"*{{edition-{edition_tag}}}.*"))
                                        if existing_files:
                                            existing_file = existing_files[0]
                                            print(f"{GREEN}Content already exists for {movie['title']}: {existing_file.name} - skipping{RESET}")
                                            skipped_existing += 1
                                            successful += 1
                                            all_movies_with_content.append(movie)
                                            content_exists = True
                                
                                if content_exists:
                                    continue
                                
                                # Process based on method
                                success = False
                                
                                if trending_movies_method == 1:  # Trailer
                                    trailer_info = search_trailer_on_youtube(
                                        movie['title'], 
                                        movie.get('year'), 
                                        movie.get('imdbId'),
                                        debug,
                                        skip_channels
                                    )
                                    
                                    if trailer_info:
                                        print(f"Found trailer: {trailer_info['video_title']} ({trailer_info['duration']}) by {trailer_info['uploader']}")
                                        success = download_trailer_movie(movie, trailer_info, debug, umtk_root_movies, is_trending=is_request_needed)
                                    else:
                                        print(f"{ORANGE}No suitable trailer found for {movie['title']}{RESET}")
                                    
                                    # If trailer method failed and fallback is enabled, try placeholder
                                    if not success and method_fallback:
                                        print(f"{ORANGE}Trailer method failed, attempting fallback to placeholder method...{RESET}")
                                        success = create_placeholder_movie(movie, debug, umtk_root_movies, is_trending=is_request_needed)
                                        if success:
                                            fallback_used += 1
                                            print(f"{GREEN}Fallback to placeholder successful for {movie['title']}{RESET}")
                                
                                elif trending_movies_method == 2:  # Placeholder
                                    success = create_placeholder_movie(movie, debug, umtk_root_movies, is_trending=is_request_needed)
                                
                                if success:
                                    successful += 1
                                    all_movies_with_content.append(movie)
                                else:
                                    failed += 1
                            
                            print(f"\n{GREEN}Trending movie content processing summary:{RESET}")
                            print(f"Successful: {successful}")
                            print(f"Skipped (already exist): {skipped_existing}")
                            if fallback_used > 0:
                                print(f"Fallback used: {fallback_used}")
                            print(f"Failed: {failed}")
                    else:
                        print(f"{ORANGE}No trending movies fetched from MDBList{RESET}")
            
            # Cleanup movie content (after processing both regular and trending)
            if cleanup:
                print(f"\n{BLUE}Checking for movie content to cleanup...{RESET}")
                cleanup_movie_content(
                    all_movies, radarr_url, radarr_api_key, future_movies, released_movies,
                    trending_movies_monitored, trending_movies_request_needed,
                    movie_method, debug, exclude_radarr_tag_ids, umtk_root_movies
                )
            
            # Create Movie YAML files (create if either movie_method or trending_movies_method is enabled)
            if movie_method > 0 or trending_movies_method > 0:
                overlay_file = kometa_folder / "UMTK_MOVIES_UPCOMING_OVERLAYS.yml"
                collection_file = kometa_folder / "UMTK_MOVIES_UPCOMING_COLLECTION.yml"
                metadata_file = kometa_folder / "UMTK_MOVIES_METADATA.yml"
                
                create_overlay_yaml_movies(
                    str(overlay_file), future_movies, released_movies,
                    trending_movies_monitored if trending_movies_method > 0 else [],
                    trending_movies_request_needed if trending_movies_method > 0 else [],
                    {"backdrop_future": config.get("backdrop_upcoming_movies_future", {}),
                     "text_future": config.get("text_upcoming_movies_future", {}),
                     "backdrop_released": config.get("backdrop_upcoming_movies_released", {}),
                     "text_released": config.get("text_upcoming_movies_released", {}),
                     "backdrop_trending_request_needed": config.get("backdrop_trending_movies_request_needed", {}),
                     "text_trending_request_needed": config.get("text_trending_movies_request_needed", {})}
                )
                
                create_collection_yaml_movies(str(collection_file), future_movies, released_movies, config)
                
                # Create metadata file
                create_movies_metadata_yaml(str(metadata_file), all_movies_with_content, config, debug)
                
                print(f"\n{GREEN}Movie YAML files created successfully{RESET}")
            
            # Create Trending Movies collection YAML
            if trending_movies_method > 0:
                mdblist_movies_url = config.get('mdblist_movies')
                mdblist_movies_limit = config.get('mdblist_movies_limit', 10)
                if mdblist_movies_url:
                    trending_collection_file = kometa_folder / "UMTK_MOVIES_TRENDING_COLLECTION.yml"
                    create_trending_collection_yaml_movies(str(trending_collection_file), mdblist_movies_url, mdblist_movies_limit, config)
                    print(f"{GREEN}Trending Movies collection YAML created successfully{RESET}")

                    # Create Top 10 Movies overlay YAML
                    if mdblist_movies_items:
                        top10_movies_overlay_file = kometa_folder / "UMTK_MOVIES_TOP10_OVERLAYS.yml"
                        create_top10_overlay_yaml_movies(
                            str(top10_movies_overlay_file), 
                            mdblist_movies_items,
                            {"backdrop": config.get("backdrop_trending_top_10", {}),
                             "text": config.get("text_trending_top_10", {})}
                        )
                        print(f"{GREEN}Top 10 Movies overlay YAML created successfully{RESET}")
        
        # Calculate and display runtime
        end_time = datetime.now()
        runtime = end_time - start_time
        hours, remainder = divmod(runtime.total_seconds(), 3600)
        minutes, seconds = divmod(remainder, 60)
        runtime_formatted = f"{int(hours):02d}:{int(minutes):02d}:{int(seconds):02d}"
        
        print(f"\n{GREEN}All processing complete!{RESET}")
        print(f"Total runtime: {runtime_formatted}")
        
    except ConnectionError as e:
        print(f"{RED}Error: {str(e)}{RESET}")
        sys.exit(1)
    except Exception as e:
        print(f"{RED}Unexpected error: {str(e)}{RESET}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()