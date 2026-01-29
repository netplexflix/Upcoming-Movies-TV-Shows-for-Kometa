"""
Media handling functions for UMTK - trailers, placeholders, and cleanup
"""

import os
import re
import json
import shutil
import subprocess
import yt_dlp
from pathlib import Path, PureWindowsPath
from datetime import datetime, timedelta, timezone

from .constants import GREEN, ORANGE, RED, BLUE, RESET
from .utils import sanitize_filename, get_user_info, get_file_owner, convert_utc_to_local
from .config_loader import get_cookies_path, get_video_folder
from .sonarr import get_sonarr_episodes


def _normalize(s: str) -> str:
    """Normalize string for comparison"""
    return re.sub(r'[^a-z0-9]+', ' ', (s or '').lower()).strip()


def _base_title(title: str) -> str:
    """Extract base title without year"""
    return re.sub(r'\s*[\(\[]\d{4}[\)\]]\s*', ' ', title or '').strip()


def _title_matches(video_title: str, content_title: str) -> bool:
    """Check if video title matches content title"""
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


def download_trailer_tv(show, trailer_info, debug=False, umtk_root_tv=None):
    """Download trailer for TV show"""
    show_path = show.get('path')
    
    # Determine the target directory
    if umtk_root_tv:
        if show_path:
            show_name = PureWindowsPath(show_path).name
        else:
            show_title = show.get('title', 'Unknown')
            show_year = show.get('year', '')
            if show_year:
                show_name = sanitize_filename(f"{show_title} ({show_year})")
            else:
                show_name = sanitize_filename(show_title)
        
        parent_dir = Path(umtk_root_tv) / show_name
        season_00_path = parent_dir / "Season 00"
    else:
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
            try:
                os.chmod(parent_dir, 0o777)
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
    
    try:
        season_00_path.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(season_00_path, 0o777)
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
            
            try:
                os.chmod(downloaded_file, 0o666)
                if debug:
                    print(f"{BLUE}[DEBUG] Set permissions 644 on {downloaded_file}{RESET}")
            except Exception as perm_error:
                if debug:
                    print(f"{ORANGE}[DEBUG] Could not set file permissions: {perm_error}{RESET}")
            
            size_mb = downloaded_file.stat().st_size / (1024 * 1024)
            print(f"{GREEN}Successfully downloaded trailer for {show['title']}: {downloaded_file.name} ({size_mb:.1f} MB){RESET}")
            
            if show.get('is_trending', False):
                marker_file = season_00_path / ".trending"
                try:
                    marker_file.touch()
                    if debug:
                        print(f"{BLUE}[DEBUG] Created trending marker file: {marker_file}{RESET}")
                except Exception as e:
                    if debug:
                        print(f"{ORANGE}[DEBUG] Could not create trending marker: {e}{RESET}")
            
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
    
    edition_tag = "Trending" if is_trending else "Coming Soon"
    
    folder_name = sanitize_filename(f"{movie_title} ({movie_year}) {{edition-{edition_tag}}}")
    file_name = sanitize_filename(f"{movie_title} ({movie_year}) {{tmdb-{tmdb_id}}} {{edition-{edition_tag}}}")
    
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
    
    if debug:
        print(f"{BLUE}[DEBUG] Movie path from Radarr: {movie_path}{RESET}")
        print(f"{BLUE}[DEBUG] Parent directory: {parent_dir}{RESET}")
        print(f"{BLUE}[DEBUG] Target path: {target_path}{RESET}")
        print(f"{BLUE}[DEBUG] Edition tag: {edition_tag}{RESET}")
        if umtk_root_movies:
            print(f"{BLUE}[DEBUG] Using custom umtk_root_movies: {umtk_root_movies}{RESET}")

    if not parent_dir.exists():
        try:
            parent_dir.mkdir(parents=True, exist_ok=True)
            try:
                os.chmod(parent_dir, 0o777)
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
    
    try:
        target_path.mkdir(parents=True, exist_ok=True)
        
        try:
            os.chmod(target_path, 0o777)
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
                os.chmod(downloaded_file, 0o666)
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
    video_folder = get_video_folder()
    
    source_files = list(video_folder.glob('UMTK.*'))
    
    if not source_files:
        print(f"{RED}No UMTK video file found in video folder{RESET}")
        return False
    
    source_file = source_files[0]
    video_extension = source_file.suffix
    
    show_path = show.get('path')
    
    if umtk_root_tv:
        if show_path:
            show_name = PureWindowsPath(show_path).name
        else:
            show_title = show.get('title', 'Unknown')
            show_year = show.get('year', '')
            if show_year:
                show_name = sanitize_filename(f"{show_title} ({show_year})")
            else:
                show_name = sanitize_filename(show_title)
        
        parent_dir = Path(umtk_root_tv) / show_name
        season_00_path = parent_dir / "Season 00"
    else:
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
    
    if dest_file.exists():
        if debug:
            print(f"{ORANGE}[DEBUG] Placeholder file already exists for {show['title']}: {dest_file}{RESET}")
        show['used_trailer'] = False
        return True
    
    if not parent_dir.exists():
        try:
            parent_dir.mkdir(parents=True, exist_ok=True)
            try:
                os.chmod(parent_dir, 0o777)
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
        
    try:
        season_00_path.mkdir(parents=True, exist_ok=True)
        
        try:
            os.chmod(season_00_path, 0o777)
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
        
        try:
            os.chmod(dest_file, 0o666)
            if debug:
                print(f"{BLUE}[DEBUG] Set permissions 644 on {dest_file}{RESET}")
        except Exception as perm_error:
            if debug:
                print(f"{ORANGE}[DEBUG] Could not set file permissions: {perm_error}{RESET}")
        
        size_mb = dest_file.stat().st_size / (1024 * 1024)
        print(f"{GREEN}Created placeholder for {show['title']}: {dest_file.name} ({size_mb:.1f} MB){RESET}")
        
        if show.get('is_trending', False):
            marker_file = season_00_path / ".trending"
            try:
                marker_file.touch()
                if debug:
                    print(f"{BLUE}[DEBUG] Created trending marker file: {marker_file}{RESET}")
            except Exception as e:
                if debug:
                    print(f"{ORANGE}[DEBUG] Could not create trending marker: {e}{RESET}")
        
        show['used_trailer'] = False
        return True
    except Exception as e:
        print(f"{RED}Error creating placeholder for {show['title']}: {e}{RESET}")
        return False


def create_placeholder_movie(movie, debug=False, umtk_root_movies=None, is_trending=False):
    """Create placeholder video for movie"""
    video_folder = get_video_folder()
    
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
    
    edition_tag = "Trending" if is_trending else "Coming Soon"
    
    folder_name = sanitize_filename(f"{movie_title} ({movie_year}) {{edition-{edition_tag}}}")
    file_name = sanitize_filename(f"{movie_title} ({movie_year}) {{tmdb-{tmdb_id}}} {{edition-{edition_tag}}}")
    
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
                os.chmod(parent_dir, 0o777)
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
            os.chmod(target_path, 0o777)
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
            os.chmod(dest_file, 0o666)
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