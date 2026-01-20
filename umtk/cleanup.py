"""
Cleanup functions for UMTK - removes outdated trailers and placeholders
"""

import os
import re
import shutil
import requests
from pathlib import Path, PureWindowsPath
from datetime import datetime, timedelta, timezone

from .constants import GREEN, ORANGE, RED, BLUE, RESET
from .utils import sanitize_filename, get_user_info, get_file_owner, convert_utc_to_local
from .sonarr import get_sonarr_episodes


def cleanup_tv_content(all_series, sonarr_url, api_key, tv_method, debug=False, exclude_tags=None, 
                       future_days_upcoming_shows=30, utc_offset=0, future_only_tv=False, 
                       umtk_root_tv=None, trending_monitored=None, trending_request_needed=None):
    """Cleanup TV show trailers or placeholders"""
    from .finders import find_upcoming_shows
    
    if debug:
        print(f"{BLUE}[DEBUG] Starting TV content cleanup process (method: {tv_method}){RESET}")
        if umtk_root_tv:
            print(f"{BLUE}[DEBUG] Using custom umtk_root_tv for cleanup: {umtk_root_tv}{RESET}")
    
    removed_count = 0
    checked_count = 0
    
    try:
        current_future_shows, current_aired_shows = find_upcoming_shows(
            all_series, sonarr_url, api_key, future_days_upcoming_shows, 
            utc_offset, debug, exclude_tags, future_only_tv
        )
    except requests.exceptions.RequestException:
        print(f"{RED}Error during TV cleanup - Sonarr connection failed. Skipping cleanup.{RESET}")
        return
    
    current_upcoming_titles = {show['title'] for show in current_future_shows + current_aired_shows}
    
    current_trending_shows = []
    if trending_monitored:
        current_trending_shows.extend(trending_monitored)
    if trending_request_needed:
        current_trending_shows.extend(trending_request_needed)
    
    current_trending_titles = {show['title'] for show in current_trending_shows}
    
    def normalize_title(title):
        normalized = re.sub(r'\s*\(\d{4}\)\s*', '', title)
        normalized = re.sub(r'[^\w\s]', '', normalized)
        normalized = ' '.join(normalized.lower().split())
        return normalized
    
    current_trending_normalized = {normalize_title(show['title']): show['title'] for show in current_trending_shows}
    
    if debug:
        print(f"{BLUE}[DEBUG] Current upcoming shows: {len(current_upcoming_titles)}{RESET}")
        print(f"{BLUE}[DEBUG] Current trending shows: {len(current_trending_titles)}{RESET}")
        if current_trending_titles:
            print(f"{BLUE}[DEBUG] Trending titles: {current_trending_titles}{RESET}")
    
    series_by_folder_name = {}
    if umtk_root_tv:
        for series in all_series:
            show_path = series.get('path')
            if show_path:
                folder_name = PureWindowsPath(show_path).name
                series_by_folder_name[folder_name] = series
                if debug:
                    print(f"{BLUE}[DEBUG] Mapped folder '{folder_name}' to series '{series['title']}'{RESET}")
    
    series_by_path = {}
    for series in all_series:
        show_path = series.get('path')
        if show_path:
            series_by_path[show_path] = series
    
    dirs_to_scan = []
    
    if umtk_root_tv:
        root_path = Path(umtk_root_tv)
        if root_path.exists():
            dirs_to_scan = [d for d in root_path.iterdir() if d.is_dir()]
        if debug:
            print(f"{BLUE}[DEBUG] Scanning custom root directory: {umtk_root_tv} ({len(dirs_to_scan)} show folders){RESET}")
    else:
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
        
        if not season_00_path.exists():
            continue
        
        is_trending = (season_00_path / ".trending").exists()
        
        show_folder_name = show_dir.name
        
        title_match = re.match(r'^(.+?)\s*\((\d{4})\)', show_folder_name)
        if title_match:
            show_title_from_folder = title_match.group(1).strip()
        else:
            show_title_from_folder = show_folder_name
        
        series = None
        if umtk_root_tv:
            series = series_by_folder_name.get(show_folder_name)
            if debug:
                if series:
                    print(f"{BLUE}[DEBUG] Found series for folder '{show_folder_name}': {series['title']}{RESET}")
                else:
                    print(f"{BLUE}[DEBUG] No series found for folder '{show_folder_name}'{RESET}")
        else:
            series = series_by_path.get(str(show_dir))
        
        if debug:
            print(f"{BLUE}[DEBUG] Checking show folder: {show_folder_name} (trending: {is_trending}, in Sonarr: {series is not None}){RESET}")
        
        trailer_files = list(season_00_path.glob("*.S00E00.Trailer.*")) + list(season_00_path.glob("*.S00E00.Coming.Soon.*"))
        
        for trailer_file in trailer_files:
            checked_count += 1
            if debug:
                print(f"{BLUE}[DEBUG] Checking file: {trailer_file.name} (trending: {is_trending}){RESET}")
            
            should_remove = False
            removal_reason = ""
            display_title = series['title'] if series else show_title_from_folder
            
            if is_trending:
                found_in_trending = False
                
                if series:
                    check_title = series['title']
                else:
                    check_title = show_title_from_folder
                
                if check_title in current_trending_titles:
                    found_in_trending = True
                    if debug:
                        print(f"{BLUE}[DEBUG] Exact match found: '{check_title}'{RESET}")
                else:
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
                if not series:
                    should_remove = True
                    removal_reason = "show no longer exists in Sonarr"
                    if debug:
                        print(f"{BLUE}[DEBUG] No series found in Sonarr for {show_title_from_folder}{RESET}")
                        print(f"{BLUE}[DEBUG] Folder name: {show_folder_name}{RESET}")
                        print(f"{BLUE}[DEBUG] Available folder mappings: {list(series_by_folder_name.keys())}{RESET}")
                else:
                    if series['title'] not in current_upcoming_titles:
                        try:
                            episodes = get_sonarr_episodes(sonarr_url, api_key, series['id'])
                        except requests.exceptions.RequestException:
                            print(f"{RED}Error fetching episodes during cleanup - Sonarr connection failed. Skipping remaining cleanup.{RESET}")
                            return
                        
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
                if umtk_root_tv:
                    if not os.access(show_dir, os.W_OK):
                        print(f"{RED}Permission denied: Cannot remove show folder {show_dir.name} for {display_title}{RESET}")
                        print(f"{RED}Directory owner: {get_file_owner(show_dir)}{RESET}")
                        print(f"{RED}Current user: {get_user_info()}{RESET}")
                        print(f"{RED}Directory permissions: {oct(show_dir.stat().st_mode)[-3:]}{RESET}")
                        continue
                    
                    parent_dir = show_dir.parent
                    if not os.access(parent_dir, os.W_OK):
                        print(f"{RED}Permission denied: No write access to parent directory {parent_dir}{RESET}")
                        print(f"{RED}Directory owner: {get_file_owner(parent_dir)}{RESET}")
                        print(f"{RED}Current user: {get_user_info()}{RESET}")
                        print(f"{RED}Directory permissions: {oct(parent_dir.stat().st_mode)[-3:]}{RESET}")
                        continue
                    
                    try:
                        try:
                            os.chmod(show_dir, 0o777)
                            if debug:
                                print(f"{BLUE}[DEBUG] Set permissions 755 on {show_dir}{RESET}")
                        except Exception as perm_err:
                            if debug:
                                print(f"{ORANGE}[DEBUG] Could not set directory permissions: {perm_err}{RESET}")
                        
                        total_size = sum(f.stat().st_size for f in show_dir.rglob('*') if f.is_file())
                        size_mb = total_size / (1024 * 1024)
                        
                        shutil.rmtree(show_dir)
                        
                        removed_count += 1
                        content_type = "trending content" if is_trending else "content"
                        print(f"{GREEN}Removed show folder for {display_title} - {removal_reason} ({size_mb:.1f} MB freed){RESET}")
                        if debug:
                            print(f"{BLUE}[DEBUG] Deleted entire folder: {show_dir}{RESET}")
                        
                        break
                        
                    except PermissionError as e:
                        print(f"{RED}Permission error removing show folder for {display_title}: {e}{RESET}")
                        print(f"{RED}Directory owner: {get_file_owner(show_dir)}{RESET}")
                        print(f"{RED}Current user: {get_user_info()}{RESET}")
                        print(f"{RED}Directory permissions: {oct(show_dir.stat().st_mode)[-3:]}{RESET}")
                    except Exception as e:
                        error_msg = str(e)
                        print(f"{RED}Error removing show folder for {display_title}: {e}{RESET}")
                        if "Permission denied" in error_msg or "Errno 13" in error_msg:
                            print(f"{RED}Directory owner: {get_file_owner(show_dir)}{RESET}")
                            print(f"{RED}Current user: {get_user_info()}{RESET}")
                            if show_dir.exists():
                                print(f"{RED}Directory permissions: {oct(show_dir.stat().st_mode)[-3:]}{RESET}")
                else:
                    if not os.access(trailer_file, os.W_OK):
                        print(f"{RED}Permission denied: Cannot remove {trailer_file.name} for {display_title}{RESET}")
                        print(f"{RED}File owner: {get_file_owner(trailer_file)}{RESET}")
                        print(f"{RED}Current user: {get_user_info()}{RESET}")
                        print(f"{RED}File permissions: {oct(trailer_file.stat().st_mode)[-3:]}{RESET}")
                        continue
                    
                    if not os.access(season_00_path, os.W_OK):
                        print(f"{RED}Permission denied: No write access to directory {season_00_path}{RESET}")
                        print(f"{RED}Directory owner: {get_file_owner(season_00_path)}{RESET}")
                        print(f"{RED}Current user: {get_user_info()}{RESET}")
                        print(f"{RED}Directory permissions: {oct(season_00_path.stat().st_mode)[-3:]}{RESET}")
                        continue
                    
                    try:
                        try:
                            os.chmod(season_00_path, 0o777)
                            if debug:
                                print(f"{BLUE}[DEBUG] Set permissions 755 on {season_00_path}{RESET}")
                        except Exception as perm_err:
                            if debug:
                                print(f"{ORANGE}[DEBUG] Could not set directory permissions: {perm_err}{RESET}")
                        
                        file_size_mb = trailer_file.stat().st_size / (1024 * 1024)
                        trailer_file.unlink()
                        
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


def cleanup_movie_content(all_movies, radarr_url, api_key, future_movies, released_movies, 
                          trending_monitored, trending_request_needed, movie_method, debug=False, 
                          exclude_tags=None, umtk_root_movies=None):
    """Cleanup movie trailers or placeholders"""
    if debug:
        print(f"{BLUE}[DEBUG] Starting movie content cleanup process (method: {movie_method}){RESET}")
        if umtk_root_movies:
            print(f"{BLUE}[DEBUG] Using custom umtk_root_movies for cleanup: {umtk_root_movies}{RESET}")
    
    removed_count = 0
    checked_count = 0
    
    current_upcoming_titles = {movie['title'] for movie in future_movies + released_movies}
    
    current_trending_movies = trending_monitored + trending_request_needed
    current_trending_titles = {movie['title'] for movie in current_trending_movies}
    
    def normalize_title(title):
        normalized = re.sub(r'\s*\(\d{4}\)\s*', '', title)
        normalized = re.sub(r'[^\w\s]', '', normalized)
        normalized = ' '.join(normalized.lower().split())
        return normalized
    
    current_trending_normalized = {normalize_title(movie['title']): movie['title'] for movie in current_trending_movies}
    
    current_trending_monitored_titles = {movie['title'] for movie in trending_monitored}
    current_trending_monitored_normalized = {normalize_title(movie['title']): movie['title'] for movie in trending_monitored}
    
    if debug:
        print(f"{BLUE}[DEBUG] Current upcoming movies: {len(current_upcoming_titles)}{RESET}")
        print(f"{BLUE}[DEBUG] Current trending movies: {len(current_trending_titles)}{RESET}")
        print(f"{BLUE}[DEBUG] Current trending monitored movies: {len(current_trending_monitored_titles)}{RESET}")
        if current_trending_titles:
            print(f"{BLUE}[DEBUG] Trending titles: {current_trending_titles}{RESET}")
    
    radarr_movie_lookup_coming_soon = {}
    radarr_movie_lookup_trending = {}
    
    for movie in all_movies:
        movie_path = movie.get('path')
        if not movie_path:
            continue
        
        movie_title = movie.get('title', 'Unknown')
        movie_year = movie.get('year', '')
        
        folder_name_coming = sanitize_filename(f"{movie_title} ({movie_year}) {{edition-Coming Soon}}")
        if umtk_root_movies:
            folder_path_coming = Path(umtk_root_movies) / folder_name_coming
        else:
            base_path = Path(movie_path)
            parent_dir = base_path.parent
            folder_path_coming = parent_dir / folder_name_coming
        radarr_movie_lookup_coming_soon[str(folder_path_coming)] = movie
        
        folder_name_trending = sanitize_filename(f"{movie_title} ({movie_year}) {{edition-Trending}}")
        if umtk_root_movies:
            folder_path_trending = Path(umtk_root_movies) / folder_name_trending
        else:
            base_path = Path(movie_path)
            parent_dir = base_path.parent
            folder_path_trending = parent_dir / folder_name_trending
        radarr_movie_lookup_trending[str(folder_path_trending)] = movie
    
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
                
                try:
                    if is_trending:
                        movie_title = folder.name.replace(" {edition-Trending}", "")
                    else:
                        movie_title = folder.name.replace(" {edition-Coming Soon}", "")
                    
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
                
                if is_trending:
                    lookup_dict = radarr_movie_lookup_trending
                    
                    found_in_trending = False
                    
                    for trending_movie in current_trending_movies:
                        trending_title = trending_movie['title']
                        
                        if title_without_year == trending_title:
                            found_in_trending = True
                            if debug:
                                print(f"{BLUE}[DEBUG] Exact match found: '{title_without_year}' == '{trending_title}'{RESET}")
                            break
                        
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
                    
                    if folder_path_str in lookup_dict:
                        movie = lookup_dict[folder_path_str]
                        movie_title = movie.get('title', movie_title)
                else:
                    lookup_dict = radarr_movie_lookup_coming_soon
                    
                    if folder_path_str in lookup_dict:
                        movie = lookup_dict[folder_path_str]
                        movie_title = movie.get('title', 'Unknown Movie')
                        
                        in_upcoming = movie_title in current_upcoming_titles
                        
                        in_trending_monitored = False
                        if movie_title in current_trending_monitored_titles:
                            in_trending_monitored = True
                        else:
                            normalized_movie = normalize_title(movie_title)
                            for trending_monitored_movie in trending_monitored:
                                if normalized_movie == normalize_title(trending_monitored_movie['title']):
                                    in_trending_monitored = True
                                    break
                        
                        if debug:
                            print(f"{BLUE}[DEBUG] Movie '{movie_title}' - in_upcoming: {in_upcoming}, in_trending_monitored: {in_trending_monitored}{RESET}")
                        
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
                    if not os.access(folder, os.W_OK):
                        print(f"{RED}Permission denied: Cannot remove folder {folder.name} for {movie_title}{RESET}")
                        print(f"{RED}Directory owner: {get_file_owner(folder)}{RESET}")
                        print(f"{RED}Current user: {get_user_info()}{RESET}")
                        print(f"{RED}Directory permissions: {oct(folder.stat().st_mode)[-3:]}{RESET}")
                        continue
                    
                    if not os.access(parent_dir, os.W_OK):
                        print(f"{RED}Permission denied: No write access to parent directory {parent_dir}{RESET}")
                        print(f"{RED}Directory owner: {get_file_owner(parent_dir)}{RESET}")
                        print(f"{RED}Current user: {get_user_info()}{RESET}")
                        print(f"{RED}Directory permissions: {oct(parent_dir.stat().st_mode)[-3:]}{RESET}")
                        continue
                    
                    try:
                        try:
                            os.chmod(folder, 0o777)
                            os.chmod(parent_dir, 0o777)
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