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

VERSION = "2025.10.021"

# ANSI color codes
GREEN = '\033[32m'
ORANGE = '\033[33m'
BLUE = '\033[34m'
RED = '\033[31m'
RESET = '\033[0m'
BOLD = '\033[1m'

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

def process_sonarr_url(base_url, api_key):
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
            response = requests.get(f"{test_url}/health", headers=headers, timeout=90)
            if response.status_code == 200:
                print(f"Successfully connected to Sonarr at: {test_url}")
                return test_url
        except requests.exceptions.RequestException as e:
            print(f"{ORANGE}Testing URL {test_url} - Failed: {str(e)}{RESET}")
            continue
    
    raise ConnectionError(f"{RED}Unable to establish connection to Sonarr. Tried the following URLs:\n" + 
                        "\n".join([f"- {base_url}{path}" for path in api_paths]) + 
                        f"\nPlease verify your URL and API key and ensure Sonarr is running.{RESET}")

def process_radarr_url(base_url, api_key):
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
            response = requests.get(f"{test_url}/health", headers=headers, timeout=90)
            if response.status_code == 200:
                print(f"Successfully connected to Radarr at: {test_url}")
                return test_url
        except requests.exceptions.RequestException as e:
            print(f"{ORANGE}Testing URL {test_url} - Failed: {str(e)}{RESET}")
            continue
    
    raise ConnectionError(f"{RED}Unable to establish connection to Radarr. Tried the following URLs:\n" + 
                        "\n".join([f"- {base_url}{path}" for path in api_paths]) + 
                        f"\nPlease verify your URL and API key and ensure Radarr is running.{RESET}")

def get_sonarr_series(sonarr_url, api_key):
    """Get all series from Sonarr"""
    try:
        url = f"{sonarr_url}/series"
        headers = {"X-Api-Key": api_key}
        response = requests.get(url, headers=headers, timeout=90)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"{RED}Error connecting to Sonarr: {str(e)}{RESET}")
        sys.exit(1)

def get_sonarr_episodes(sonarr_url, api_key, series_id):
    """Get episodes for a specific series"""
    try:
        url = f"{sonarr_url}/episode?seriesId={series_id}"
        headers = {"X-Api-Key": api_key}
        response = requests.get(url, headers=headers, timeout=90)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"{RED}Error fetching episodes from Sonarr: {str(e)}{RESET}")
        sys.exit(1)

def get_radarr_movies(radarr_url, api_key):
    """Get all movies from Radarr"""
    try:
        url = f"{radarr_url}/movie"
        headers = {"X-Api-Key": api_key}
        response = requests.get(url, headers=headers, timeout=90)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
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
def find_upcoming_shows(sonarr_url, api_key, future_days_upcoming_shows, utc_offset=0, debug=False, exclude_tags=None, future_only_tv=False):
    """Find shows with upcoming episodes that have their first episode airing within specified days"""
    future_shows = []
    aired_shows = []
    
    cutoff_date = datetime.now(timezone.utc) + timedelta(days=future_days_upcoming_shows)
    now_local = datetime.now(timezone.utc) + timedelta(hours=utc_offset)
    
    if debug:
        print(f"{BLUE}[DEBUG] Cutoff date: {cutoff_date}, Now local: {now_local}{RESET}")
        print(f"{BLUE}[DEBUG] Future only TV: {future_only_tv}{RESET}")
    
    all_series = get_sonarr_series(sonarr_url, api_key)
    
    if debug:
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
            if air_date > now_local:
                future_shows.append(show_dict)
                if debug:
                    print(f"{GREEN}[DEBUG] Added to future shows: {series['title']}{RESET}")
            elif not future_only_tv:  # Only add aired shows if future_only_tv is False
                aired_shows.append(show_dict)
                if debug:
                    print(f"{GREEN}[DEBUG] Added to aired shows: {series['title']}{RESET}")
            elif debug:
                print(f"{ORANGE}[DEBUG] Skipping aired show due to future_only_tv=True: {series['title']}{RESET}")
    
    return future_shows, aired_shows

def find_new_shows(sonarr_url, api_key, recent_days_new_show, utc_offset=0, debug=False):
    """Find shows where S01E01 has been downloaded and aired within specified past days"""
    new_shows = []
    
    now_local = datetime.now(timezone.utc) + timedelta(hours=utc_offset)
    cutoff_date = now_local - timedelta(days=recent_days_new_show)
    
    if debug:
        print(f"{BLUE}[DEBUG] Looking for shows with S01E01 aired between {cutoff_date} and {now_local}{RESET}")
    
    all_series = get_sonarr_series(sonarr_url, api_key)
    
    if debug:
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
def find_upcoming_movies(radarr_url, api_key, future_days_upcoming_movies, utc_offset=0, future_only=False, include_inCinemas=False, debug=False, exclude_tags=None):
    """Find movies that are monitored and meet release date criteria"""
    future_movies = []
    released_movies = []
    
    cutoff_date = datetime.now(timezone.utc) + timedelta(days=future_days_upcoming_movies)
    now_local = datetime.now(timezone.utc) + timedelta(hours=utc_offset)
    
    if debug:
        print(f"{BLUE}[DEBUG] Cutoff date: {cutoff_date}, Now local: {now_local}{RESET}")
        print(f"{BLUE}[DEBUG] Future only mode: {future_only}{RESET}")
        print(f"{BLUE}[DEBUG] Include inCinemas: {include_inCinemas}{RESET}")
    
    all_movies = get_radarr_movies(radarr_url, api_key)
    
    if debug:
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
        
        if release_date > now_local and release_date <= cutoff_date:
            future_movies.append(movie_dict)
            if debug:
                print(f"{GREEN}[DEBUG] Added to future movies: {movie['title']}{RESET}")
        elif release_date <= now_local and not future_only:
            released_movies.append(movie_dict)
            if debug:
                print(f"{GREEN}[DEBUG] Added to released movies: {movie['title']}{RESET}")
    
    return future_movies, released_movies

def get_tag_ids_from_names(api_url, api_key, tag_names, debug=False):
    """Convert tag names to tag IDs"""
    if not tag_names:
        return []
    
    try:
        url = f"{api_url}/tag"
        headers = {"X-Api-Key": api_key}
        response = requests.get(url, headers=headers, timeout=90)
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
    if not show_path:
        print(f"{RED}No path found for show: {show.get('title')}{RESET}")
        return False

    if umtk_root_tv:
        # Use custom root path
        show_name = Path(show_path).name
        season_00_path = Path(umtk_root_tv) / show_name / "Season 00"
    else:
        # Use original logic
        season_00_path = Path(show_path) / "Season 00"
    
    # Check if parent directory exists and is writable
    if umtk_root_tv:
        parent_dir = Path(umtk_root_tv) / Path(show_path).name
    else:
        parent_dir = Path(show_path)
    
    if not parent_dir.exists():
        print(f"{RED}Error: Parent directory does not exist: {parent_dir}{RESET}")
        return False
    
    if not os.access(parent_dir, os.W_OK):
        print(f"{RED}Error: No write permission for directory: {parent_dir}{RESET}")
        print(f"{RED}Directory owner: {parent_dir.stat().st_uid}:{parent_dir.stat().st_gid}{RESET}")
        print(f"{RED}Current user: {os.getuid()}:{os.getgid()}{RESET}")
        return False
    
    try:
        season_00_path.mkdir(parents=True, exist_ok=True)
    except PermissionError as e:
        print(f"{RED}Permission error creating directory {season_00_path}: {e}{RESET}")
        print(f"{RED}Parent directory permissions: {oct(parent_dir.stat().st_mode)[-3:]}{RESET}")
        return False
    except Exception as e:
        print(f"{RED}Error creating directory {season_00_path}: {e}{RESET}")
        return False

    clean_title = "".join(c for c in show['title'] if c.isalnum() or c in (' ', '-', '_')).rstrip()

    if debug:
        print(f"{BLUE}[DEBUG] Show path: {show_path}{RESET}")
        print(f"{BLUE}[DEBUG] Season 00 path: {season_00_path}{RESET}")
        if umtk_root_tv:
            print(f"{BLUE}[DEBUG] Using custom umtk_root_tv: {umtk_root_tv}{RESET}")

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
            size_mb = downloaded_file.stat().st_size / (1024 * 1024)
            print(f"{GREEN}Successfully downloaded trailer for {show['title']}: {downloaded_file.name} ({size_mb:.1f} MB){RESET}")
            return True

        print(f"{RED}Trailer file not found after download for {show['title']}{RESET}")
        return False

    except Exception as e:
        print(f"{RED}Download error for {show['title']}: {e}{RESET}")
        return False

def download_trailer_movie(movie, trailer_info, debug=False, umtk_root_movies=None):
    """Download trailer for movie"""
    movie_path = movie.get('path')
    if not movie_path:
        print(f"{RED}No path found for movie: {movie.get('title')}{RESET}")
        return False

    movie_title = movie.get('title', 'Unknown')
    movie_year = movie.get('year', '')
    tmdb_id = movie.get('tmdbId', '')
    
    folder_name = sanitize_filename(f"{movie_title} ({movie_year}) {{edition-Coming Soon}}")
    file_name = sanitize_filename(f"{movie_title} ({movie_year}) {{tmdb-{tmdb_id}}} {{edition-Coming Soon}}")
    
    if umtk_root_movies:
        # Use custom root path
        coming_soon_path = Path(umtk_root_movies) / folder_name
    else:
        # Use original logic
        base_path = Path(movie_path)
        parent_dir = base_path.parent
        coming_soon_path = parent_dir / folder_name
    
    coming_soon_path.mkdir(parents=True, exist_ok=True)

    if debug:
        print(f"{BLUE}[DEBUG] Movie path: {movie_path}{RESET}")
        print(f"{BLUE}[DEBUG] Coming Soon path: {coming_soon_path}{RESET}")
        if umtk_root_movies:
            print(f"{BLUE}[DEBUG] Using custom umtk_root_movies: {umtk_root_movies}{RESET}")

    filename = f"{file_name}.%(ext)s"
    output_path = coming_soon_path / filename

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

        print(f"Downloading trailer for {movie['title']} (prefer 1080p MKV/MP4)...")

        try:
            _run('(bv*[ext=mkv][height=1080]+ba/b[ext=mkv][height=1080]) / (bv*[ext=mp4][height=1080]+ba[ext=m4a]/b[ext=mp4][height=1080]) / (bv*[height=1080]+ba/b[height=1080])')
        except Exception as e1:
            if debug:
                print(f"{ORANGE}[DEBUG] 1080p exact failed ({e1}); trying best <=1080p{RESET}")
            _run('(bv*[ext=mkv][height<=1080]+ba/b[ext=mkv][height<=1080]) / (bv*[ext=mp4][height<=1080]+ba[ext=m4a]/b[ext=mp4][height<=1080]) / (bv*[height<=1080]+ba/b[height<=1080])')

        downloaded_files = list(coming_soon_path.glob(f"{file_name}.*"))
        if downloaded_files:
            downloaded_file = downloaded_files[0]
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
    if not show_path:
        print(f"{RED}No path found for show: {show.get('title')}{RESET}")
        return False
    
    if umtk_root_tv:
        # Use custom root path
        show_name = Path(show_path).name
        season_00_path = Path(umtk_root_tv) / show_name / "Season 00"
    else:
        # Use original logic
        season_00_path = Path(show_path) / "Season 00"
    
    clean_title = "".join(c for c in show['title'] if c.isalnum() or c in (' ', '-', '_')).rstrip()
    dest_file = season_00_path / f"{clean_title}.S00E00.Trailer{video_extension}"
    
    if debug:
        print(f"{BLUE}[DEBUG] Show path: {show_path}{RESET}")
        print(f"{BLUE}[DEBUG] Season 00 path: {season_00_path}{RESET}")
        print(f"{BLUE}[DEBUG] Destination file: {dest_file}{RESET}")
        if umtk_root_tv:
            print(f"{BLUE}[DEBUG] Using custom umtk_root_tv: {umtk_root_tv}{RESET}")
    
    # Check if parent directory exists and is writable
    parent_dir = Path(show_path)
    if not parent_dir.exists():
        print(f"{RED}Error: Parent directory does not exist: {parent_dir}{RESET}")
        return False
    
    if not os.access(parent_dir, os.W_OK):
        print(f"{RED}Error: No write permission for directory: {parent_dir}{RESET}")
        print(f"{RED}Directory owner: {parent_dir.stat().st_uid}:{parent_dir.stat().st_gid}{RESET}")
        print(f"{RED}Current user: {os.getuid()}:{os.getgid()}{RESET}")
        return False
        
    try:
        season_00_path.mkdir(parents=True, exist_ok=True)
    except PermissionError as e:
        print(f"{RED}Permission error creating directory {season_00_path}: {e}{RESET}")
        print(f"{RED}Parent directory permissions: {oct(parent_dir.stat().st_mode)[-3:]}{RESET}")
        return False
    except Exception as e:
        print(f"{RED}Error creating directory {season_00_path}: {e}{RESET}")
        return False
    
    try:
        shutil.copy2(source_file, dest_file)
        size_mb = dest_file.stat().st_size / (1024 * 1024)
        print(f"{GREEN}Created placeholder for {show['title']}: {dest_file.name} ({size_mb:.1f} MB){RESET}")
        return True
    except Exception as e:
        print(f"{RED}Error creating placeholder for {show['title']}: {e}{RESET}")
        return False

def create_placeholder_movie(movie, debug=False, umtk_root_movies=None):
    """Create placeholder video for movie"""
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
    
    movie_path = movie.get('path')
    if not movie_path:
        print(f"{RED}No path found for movie: {movie.get('title')}{RESET}")
        return False
    
    movie_title = movie.get('title', 'Unknown')
    movie_year = movie.get('year', '')
    tmdb_id = movie.get('tmdbId', '')
    
    folder_name = sanitize_filename(f"{movie_title} ({movie_year}) {{edition-Coming Soon}}")
    file_name = sanitize_filename(f"{movie_title} ({movie_year}) {{tmdb-{tmdb_id}}} {{edition-Coming Soon}}")
    
    if umtk_root_movies:
        # Use custom root path
        coming_soon_path = Path(umtk_root_movies) / folder_name
    else:
        # Use original logic
        base_path = Path(movie_path)
        parent_dir = base_path.parent
        coming_soon_path = parent_dir / folder_name
    
    dest_file = coming_soon_path / f"{file_name}{video_extension}"
    
    if debug:
        print(f"{BLUE}[DEBUG] Movie path: {movie_path}{RESET}")
        print(f"{BLUE}[DEBUG] Coming Soon path: {coming_soon_path}{RESET}")
        print(f"{BLUE}[DEBUG] Destination file: {dest_file}{RESET}")
        if umtk_root_movies:
            print(f"{BLUE}[DEBUG] Using custom umtk_root_movies: {umtk_root_movies}{RESET}")

    if dest_file.exists():
        if debug:
            print(f"{ORANGE}[DEBUG] Placeholder file already exists for {movie['title']}{RESET}")
        return True
    
    try:
        coming_soon_path.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_file, dest_file)
        
        size_mb = dest_file.stat().st_size / (1024 * 1024)
        print(f"{GREEN}Created placeholder for {movie['title']}: {dest_file.name} ({size_mb:.1f} MB){RESET}")
        return True
        
    except Exception as e:
        print(f"{RED}Error creating placeholder for {movie['title']}: {e}{RESET}")
        return False

# Cleanup functions
def cleanup_tv_content(sonarr_url, api_key, tv_method, debug=False, exclude_tags=None, future_days_upcoming_shows=30, utc_offset=0, future_only_tv=False, umtk_root_tv=None):
    """Cleanup TV show trailers or placeholders"""
    if debug:
        print(f"{BLUE}[DEBUG] Starting TV content cleanup process (method: {tv_method}){RESET}")
        if umtk_root_tv:
            print(f"{BLUE}[DEBUG] Using custom umtk_root_tv for cleanup: {umtk_root_tv}{RESET}")
    
    removed_count = 0
    checked_count = 0
    
    all_series = get_sonarr_series(sonarr_url, api_key)
    
    # Get current upcoming shows to compare against
    current_future_shows, current_aired_shows = find_upcoming_shows(sonarr_url, api_key, future_days_upcoming_shows, utc_offset, debug, exclude_tags, future_only_tv)
    current_upcoming_titles = {show['title'] for show in current_future_shows + current_aired_shows}
    
    if debug:
        print(f"{BLUE}[DEBUG] Current upcoming shows: {current_upcoming_titles}{RESET}")
    
    for series in all_series:
        show_path = series.get('path')
        if not show_path:
            continue
        
        # Use custom root path if specified, otherwise use original logic
        if umtk_root_tv:
            show_name = Path(show_path).name
            season_00_path = Path(umtk_root_tv) / show_name / "Season 00"
        else:
            season_00_path = Path(show_path) / "Season 00"
        
        # Skip if Season 00 doesn't exist
        if not season_00_path.exists():
            if debug:
                print(f"{BLUE}[DEBUG] Season 00 path doesn't exist for {series['title']}, skipping{RESET}")
            continue
            
        trailer_files = list(season_00_path.glob("*.S00E00.Trailer.*"))
                
        for trailer_file in trailer_files:
            checked_count += 1
            if debug:
                print(f"{BLUE}[DEBUG] Checking trailer: {trailer_file.name} for {series['title']}{RESET}")
            
            should_remove = False
            removal_reason = ""
            
            # Check if show is no longer in upcoming shows list (due to exclusion tags, unmonitored, or date changes)
            if series['title'] not in current_upcoming_titles:
                # Additional checks to determine why it's not in the list
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
                        elif future_only_tv and air_date <= now_local:
                            should_remove = True
                            removal_reason = "aired show excluded due to future_only_tv=True"
                    else:
                        should_remove = True
                        removal_reason = "no valid S01E01 or air date found"
            elif debug:
                print(f"{BLUE}[DEBUG] Keeping content for {series['title']} - still in upcoming shows list{RESET}")
            
            if should_remove:
                try:
                    file_size_mb = trailer_file.stat().st_size / (1024 * 1024)
                    trailer_file.unlink()
                    removed_count += 1
                    print(f"{GREEN}Removed content for {series['title']} - {removal_reason} ({file_size_mb:.1f} MB freed){RESET}")
                    if debug:
                        print(f"{BLUE}[DEBUG] Deleted: {trailer_file}{RESET}")
                except Exception as e:
                    print(f"{RED}Error removing content for {series['title']}: {e}{RESET}")
    
    if removed_count > 0:
        print(f"{GREEN}TV cleanup complete: Removed {removed_count} file(s) from {checked_count} checked{RESET}")
    elif checked_count > 0:
        print(f"{GREEN}TV cleanup complete: No files needed removal ({checked_count} checked){RESET}")
    elif debug:
        print(f"{BLUE}[DEBUG] No TV content found to check{RESET}")

def cleanup_movie_content(radarr_url, api_key, future_movies, released_movies, movie_method, debug=False, exclude_tags=None, umtk_root_movies=None):
    """Cleanup movie trailers or placeholders"""
    if debug:
        print(f"{BLUE}[DEBUG] Starting movie content cleanup process (method: {movie_method}){RESET}")
        if umtk_root_movies:
            print(f"{BLUE}[DEBUG] Using custom umtk_root_movies for cleanup: {umtk_root_movies}{RESET}")
    
    removed_count = 0
    checked_count = 0
    
    all_movies = get_radarr_movies(radarr_url, api_key)
    
    # Create a set of current valid movie titles for quick lookup
    current_valid_movies = {movie['title'] for movie in future_movies + released_movies}
    
    if debug:
        print(f"{BLUE}[DEBUG] Current valid movies: {len(current_valid_movies)} movies{RESET}")
    
    valid_coming_soon_paths = set()
    for movie in future_movies + released_movies:
        if movie.get('path'):
            movie_title = movie.get('title', 'Unknown')
            movie_year = movie.get('year', '')
            folder_name = sanitize_filename(f"{movie_title} ({movie_year}) {{edition-Coming Soon}}")
            
            if umtk_root_movies:
                coming_soon_path = Path(umtk_root_movies) / folder_name
            else:
                base_path = Path(movie['path'])
                parent_dir = base_path.parent
                coming_soon_path = parent_dir / folder_name
            
            valid_coming_soon_paths.add(str(coming_soon_path))
    
    radarr_movie_lookup = {}
    for movie in all_movies:
        movie_path = movie.get('path')
        if not movie_path:
            continue
        
        movie_title = movie.get('title', 'Unknown')
        movie_year = movie.get('year', '')
        folder_name = sanitize_filename(f"{movie_title} ({movie_year}) {{edition-Coming Soon}}")
        
        if umtk_root_movies:
            coming_soon_path = Path(umtk_root_movies) / folder_name
        else:
            base_path = Path(movie_path)
            parent_dir = base_path.parent
            coming_soon_path = parent_dir / folder_name
        
        radarr_movie_lookup[str(coming_soon_path)] = movie
    
    # Determine directories to scan
    parent_dirs_to_scan = set()
    
    if umtk_root_movies:
        # If using custom root, only scan the custom root directory
        parent_dirs_to_scan.add(Path(umtk_root_movies))
        if debug:
            print(f"{BLUE}[DEBUG] Scanning custom root directory: {umtk_root_movies}{RESET}")
    else:
        # Original logic: scan parent directories of all movie paths
        for movie in all_movies:
            movie_path = movie.get('path')
            if movie_path:
                base_path = Path(movie_path)
                parent_dirs_to_scan.add(base_path.parent)
        
        for valid_path in valid_coming_soon_paths:
            parent_dirs_to_scan.add(Path(valid_path).parent)
        
        if debug:
            print(f"{BLUE}[DEBUG] Scanning {len(parent_dirs_to_scan)} parent directories for Coming Soon folders{RESET}")
    
    for parent_dir in parent_dirs_to_scan:
        if not parent_dir.exists():
            if debug:
                print(f"{ORANGE}[DEBUG] Directory does not exist: {parent_dir}{RESET}")
            continue
            
        try:
            for folder in parent_dir.iterdir():
                if folder.is_dir() and "{edition-Coming Soon}" in folder.name:
                    checked_count += 1
                    folder_path_str = str(folder)
                    
                    if debug:
                        print(f"{BLUE}[DEBUG] Found Coming Soon folder: {folder.name}{RESET}")
                    
                    should_remove = False
                    reason = ""
                    movie_title = "Unknown Movie"
                    
                    if folder_path_str in radarr_movie_lookup:
                        movie = radarr_movie_lookup[folder_path_str]
                        movie_title = movie.get('title', 'Unknown Movie')
                        
                        if movie.get('hasFile', False):
                            should_remove = True
                            reason = "movie has been downloaded"
                        elif not movie.get('monitored', False):
                            should_remove = True
                            reason = "movie is no longer monitored"
                        elif exclude_tags and any(tag in movie.get('tags', []) for tag in exclude_tags):
                            should_remove = True
                            reason = "movie has excluded tags"
                        elif movie_title not in current_valid_movies:
                            should_remove = True
                            reason = "movie no longer meets criteria"
                        elif debug:
                            print(f"{BLUE}[DEBUG] Keeping content for {movie_title} - still valid{RESET}")
                    else:
                        should_remove = True
                        reason = "movie no longer exists in Radarr"
                        try:
                            folder_name = folder.name
                            if " {edition-Coming Soon}" in folder_name:
                                movie_title = folder_name.replace(" {edition-Coming Soon}", "")
                        except:
                            movie_title = folder.name
                    
                    if should_remove:
                        try:
                            total_size = sum(f.stat().st_size for f in folder.rglob('*') if f.is_file())
                            size_mb = total_size / (1024 * 1024)
                            
                            shutil.rmtree(folder)
                            removed_count += 1
                            print(f"{GREEN}Removed content for {movie_title} - {reason} ({size_mb:.1f} MB freed){RESET}")
                            if debug:
                                print(f"{BLUE}[DEBUG] Deleted: {folder}{RESET}")
                        except Exception as e:
                            print(f"{RED}Error removing content for {movie_title}: {e}{RESET}")
        except Exception as e:
            if debug:
                print(f"{ORANGE}[DEBUG] Error scanning directory {parent_dir}: {e}{RESET}")
            continue
    
    if removed_count > 0:
        print(f"{GREEN}Movie cleanup complete: Removed {removed_count} folder(s) from {checked_count} checked{RESET}")
    elif checked_count > 0:
        print(f"{GREEN}Movie cleanup complete: No folders needed removal ({checked_count} checked){RESET}")
    elif debug:
        print(f"{BLUE}[DEBUG] No Coming Soon folders found to check{RESET}")

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

def create_overlay_yaml_tv(output_file, future_shows, aired_shows, config_sections):
    """Create overlay YAML file for TV shows"""
    import yaml

    if not future_shows and not aired_shows:
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
            # Remove date-related configs as they're not used for aired shows
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
    
    final_output = {"overlays": overlays_dict}
    
    with open(output_file, "w", encoding="utf-8") as f:
        yaml.dump(final_output, f, sort_keys=False)

def create_new_shows_overlay_yaml(output_file, shows, config_sections):
    """Create overlay YAML file for new shows"""
    import yaml

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
    import yaml
    from yaml.representer import SafeRepresenter
    from collections import OrderedDict

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

def create_overlay_yaml_movies(output_file, future_movies, released_movies, config_sections):
    """Create overlay YAML file for movies"""
    import yaml

    if not future_movies and not released_movies:
        with open(output_file, "w", encoding="utf-8") as f:
            f.write("#No matching movies found")
        return
    
    overlays_dict = {}
    
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
    
    final_output = {"overlays": overlays_dict}
    
    with open(output_file, "w", encoding="utf-8") as f:
        yaml.dump(final_output, f, sort_keys=False)

def create_collection_yaml_movies(output_file, future_movies, released_movies, config):
    """Create collection YAML file for movies"""
    import yaml
    from yaml.representer import SafeRepresenter
    from collections import OrderedDict

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

def main():
    start_time = datetime.now()
    print(f"{BLUE}{'*' * 50}\n{'*' * 1}Upcoming Movies & TV Shows for Kometa {VERSION}{'*' * 1}\n{'*' * 50}{RESET}")
    
    # Add Docker detection message
    if os.environ.get('DOCKER') == 'true':
        print(f"{GREEN}Running in Docker container{RESET}")
    
    check_for_updates()
    
    config = load_config()
    
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
    method_fallback = str(config.get("method_fallback", "false")).lower() == "true"
    
    print(f"TV processing method: {tv_method} ({'Disabled' if tv_method == 0 else 'Trailer' if tv_method == 1 else 'Placeholder'})")
    print(f"Movie processing method: {movie_method} ({'Disabled' if movie_method == 0 else 'Trailer' if movie_method == 1 else 'Placeholder'})")
    print(f"Method fallback: {method_fallback}")
    print()
    
    # Check requirements based on methods
    if tv_method == 1 or movie_method == 1:
        if not check_yt_dlp_installed():
            print(f"{RED}yt-dlp is required for trailer downloading but not installed.{RESET}")
            sys.exit(1)
    
    # Check for placeholder requirements (both original methods and fallback)
    if tv_method == 2 or movie_method == 2 or (method_fallback and (tv_method == 1 or movie_method == 1)):
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
        # Process TV Shows
        if tv_method > 0:
            print(f"{BLUE}{'=' * 50}{RESET}")
            print(f"{BLUE}Processing TV Shows...{RESET}")
            print(f"{BLUE}{'=' * 50}{RESET}\n")
            
            sonarr_url = process_sonarr_url(config['sonarr_url'], config['sonarr_api_key'])
            sonarr_api_key = config['sonarr_api_key']
            
            # Get exclude tags for Sonarr
            exclude_sonarr_tag_names = config.get('exclude_sonarr_tags', [])
            if isinstance(exclude_sonarr_tag_names, str):
                exclude_sonarr_tag_names = [tag.strip() for tag in exclude_sonarr_tag_names.split(',') if tag.strip()]
            
            exclude_sonarr_tag_ids = get_tag_ids_from_names(sonarr_url, sonarr_api_key, exclude_sonarr_tag_names, debug)
            
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
            
            # Cleanup TV content
            if cleanup:
                print(f"{BLUE}Checking for TV content to cleanup...{RESET}")
                cleanup_tv_content(sonarr_url, sonarr_api_key, tv_method, debug, exclude_sonarr_tag_ids, future_days_upcoming_shows, utc_offset, future_only_tv, umtk_root_tv)
                print()
            
            # Find upcoming shows
            future_shows, aired_shows = find_upcoming_shows(
                sonarr_url, sonarr_api_key, future_days_upcoming_shows, utc_offset, debug, exclude_sonarr_tag_ids, future_only_tv
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
                sonarr_url, sonarr_api_key, recent_days_new_show, utc_offset, debug
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
                            # Use custom root path for checking existing files
                            show_name = Path(show_path).name
                            season_00_path = Path(umtk_root_tv) / show_name / "Season 00"
                        else:
                            # Use original logic
                            season_00_path = Path(show_path) / "Season 00"
                        
                        clean_title = "".join(c for c in show['title'] if c.isalnum() or c in (' ', '-', '_')).rstrip()
                        
                        trailer_pattern = f"{clean_title}.S00E00.Trailer.*"
                        existing_trailers = list(season_00_path.glob(trailer_pattern)) if season_00_path.exists() else []
                        
                        if existing_trailers:
                            existing_file = existing_trailers[0]
                            print(f"{GREEN}Content already exists for {show['title']}: {existing_file.name} - skipping{RESET}")
                            skipped_existing += 1
                            successful += 1
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
                    else:
                        failed += 1
                
                print(f"\n{GREEN}TV content processing summary:{RESET}")
                print(f"Successful: {successful}")
                print(f"Skipped (already exist): {skipped_existing}")
                if fallback_used > 0:
                    print(f"Fallback used: {fallback_used}")
                print(f"Failed: {failed}")
            
            # Create TV YAML files
            overlay_file = kometa_folder / "UMTK_TV_UPCOMING_SHOWS_OVERLAYS.yml"
            new_shows_overlay_file = kometa_folder / "UMTK_TV_NEW_SHOWS_OVERLAYS.yml"
            collection_file = kometa_folder / "UMTK_TV_UPCOMING_SHOWS_COLLECTION.yml"
            
            create_overlay_yaml_tv(str(overlay_file), future_shows, aired_shows, 
                               {"backdrop": config.get("backdrop_upcoming_shows", {}),
                                "text": config.get("text_upcoming_shows", {}),
                                "backdrop_aired": config.get("backdrop_upcoming_shows_aired", {}),
                                "text_aired": config.get("text_upcoming_shows_aired", {})})
            
            create_new_shows_overlay_yaml(str(new_shows_overlay_file), new_shows,
                                          {"backdrop": config.get("backdrop_new_show", {}),
                                           "text": config.get("text_new_show", {})})
            
            create_collection_yaml_tv(str(collection_file), future_shows, aired_shows, config)
            
            print(f"\n{GREEN}TV YAML files created successfully{RESET}")
        
        # Process Movies
        if movie_method > 0:
            print(f"\n{BLUE}{'=' * 50}{RESET}")
            print(f"{BLUE}Processing Movies...{RESET}")
            print(f"{BLUE}{'=' * 50}{RESET}\n")
            
            radarr_url = process_radarr_url(config['radarr_url'], config['radarr_api_key'])
            radarr_api_key = config['radarr_api_key']
            
            # Get exclude tags for Radarr
            exclude_radarr_tag_names = config.get('exclude_radarr_tags', [])
            if isinstance(exclude_radarr_tag_names, str):
                exclude_radarr_tag_names = [tag.strip() for tag in exclude_radarr_tag_names.split(',') if tag.strip()]
            
            exclude_radarr_tag_ids = get_tag_ids_from_names(radarr_url, radarr_api_key, exclude_radarr_tag_names, debug)
            
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
            
            # Find upcoming movies
            print(f"{BLUE}Finding upcoming movies...{RESET}")
            future_movies, released_movies = find_upcoming_movies(
                radarr_url, radarr_api_key, future_days_upcoming_movies, utc_offset, future_only, include_inCinemas, debug, exclude_radarr_tag_ids
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
            all_movies = future_movies + released_movies
            if all_movies:
                print(f"\n{BLUE}Processing content for movies...{RESET}")
                successful = 0
                failed = 0
                fallback_used = 0
                
                for movie in all_movies:
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
                            success = download_trailer_movie(movie, trailer_info, debug, umtk_root_movies)
                        else:
                            print(f"{ORANGE}No suitable trailer found for {movie['title']}{RESET}")
                        
                        # If trailer method failed and fallback is enabled, try placeholder
                        if not success and method_fallback:
                            print(f"{ORANGE}Trailer method failed, attempting fallback to placeholder method...{RESET}")
                            success = create_placeholder_movie(movie, debug, umtk_root_movies)
                            if success:
                                fallback_used += 1
                                print(f"{GREEN}Fallback to placeholder successful for {movie['title']}{RESET}")
                    
                    elif movie_method == 2:  # Placeholder
                        success = create_placeholder_movie(movie, debug, umtk_root_movies)
                    
                    if success:
                        successful += 1
                    else:
                        failed += 1
                
                print(f"\n{GREEN}Movie content processing summary:{RESET}")
                print(f"Successful: {successful}")
                if fallback_used > 0:
                    print(f"Fallback used: {fallback_used}")
                print(f"Failed: {failed}")
            
            # Cleanup movie content
            if cleanup:
                print(f"\n{BLUE}Checking for movie content to cleanup...{RESET}")
                cleanup_movie_content(radarr_url, radarr_api_key, future_movies, released_movies, movie_method, debug, exclude_radarr_tag_ids, umtk_root_movies)
            
            # Create Movie YAML files
            overlay_file = kometa_folder / "UMTK_MOVIES_UPCOMING_OVERLAYS.yml"
            collection_file = kometa_folder / "UMTK_MOVIES_UPCOMING_COLLECTION.yml"
            
            create_overlay_yaml_movies(str(overlay_file), future_movies, released_movies,
                              {"backdrop_future": config.get("backdrop_upcoming_movies_future", {}),
                               "text_future": config.get("text_upcoming_movies_future", {}),
                               "backdrop_released": config.get("backdrop_upcoming_movies_released", {}),
                               "text_released": config.get("text_upcoming_movies_released", {})})
            
            create_collection_yaml_movies(str(collection_file), future_movies, released_movies, config)
            
            print(f"\n{GREEN}Movie YAML files created successfully{RESET}")
        
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
        sys.exit(1)

if __name__ == "__main__":
    main()
