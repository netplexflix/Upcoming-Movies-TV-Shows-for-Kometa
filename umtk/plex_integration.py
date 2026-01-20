"""
Plex metadata integration for UMTK
"""

import re
import time
import requests

from .constants import GREEN, ORANGE, RED, BLUE, RESET
from .utils import sanitize_sort_title


def get_plex_libraries(plex_url, plex_token, debug=False):
    """Get all libraries from Plex"""
    try:
        url = f"{plex_url.rstrip('/')}/library/sections"
        headers = {
            "X-Plex-Token": plex_token,
            "Accept": "application/json"
        }
        
        if debug:
            print(f"{BLUE}[DEBUG] Fetching Plex libraries from: {url}{RESET}")
        
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        libraries = {}
        
        for directory in data.get('MediaContainer', {}).get('Directory', []):
            lib_name = directory.get('title')
            lib_key = directory.get('key')
            lib_type = directory.get('type')
            libraries[lib_name] = {'key': lib_key, 'type': lib_type}
            
            if debug:
                print(f"{BLUE}[DEBUG] Found Plex library: {lib_name} (key: {lib_key}, type: {lib_type}){RESET}")
        
        return libraries
    except requests.exceptions.RequestException as e:
        print(f"{RED}Error connecting to Plex: {str(e)}{RESET}")
        return {}


def get_plex_library_items(plex_url, plex_token, library_key, debug=False):
    """Get all items from a Plex library with their sort titles and external IDs"""
    try:
        url = f"{plex_url.rstrip('/')}/library/sections/{library_key}/all?includeGuids=1"
        headers = {
            "X-Plex-Token": plex_token,
            "Accept": "application/json"
        }
        
        if debug:
            print(f"{BLUE}[DEBUG] Fetching Plex library items from: {url}{RESET}")
        
        response = requests.get(url, headers=headers, timeout=60)
        response.raise_for_status()
        
        data = response.json()
        items = []
        
        metadata_list = data.get('MediaContainer', {}).get('Metadata', [])
        
        if debug:
            print(f"{BLUE}[DEBUG] Raw response contains {len(metadata_list)} items{RESET}")
        
        for item in metadata_list:
            item_data = {
                'ratingKey': item.get('ratingKey'),
                'title': item.get('title'),
                'titleSort': item.get('titleSort', ''),
                'year': item.get('year'),
                'type': item.get('type'),
                'guid': item.get('guid', ''),
            }
            
            guids = item.get('Guid', [])
            
            if debug and len(items) < 3:
                print(f"{BLUE}[DEBUG] Item: {item.get('title')} - Guids: {guids}{RESET}")
            
            for guid_entry in guids:
                guid_id = guid_entry.get('id', '')
                if guid_id.startswith('tmdb://'):
                    item_data['tmdbId'] = guid_id.replace('tmdb://', '')
                elif guid_id.startswith('tvdb://'):
                    item_data['tvdbId'] = guid_id.replace('tvdb://', '')
                elif guid_id.startswith('imdb://'):
                    item_data['imdbId'] = guid_id.replace('imdb://', '')
            
            main_guid = item.get('guid', '')
            if 'tmdb://' in main_guid and 'tmdbId' not in item_data:
                item_data['tmdbId'] = main_guid.split('tmdb://')[1].split('?')[0].split('/')[0]
            elif 'tvdb://' in main_guid and 'tvdbId' not in item_data:
                item_data['tvdbId'] = main_guid.split('tvdb://')[1].split('?')[0].split('/')[0]
            elif 'imdb://' in main_guid and 'imdbId' not in item_data:
                item_data['imdbId'] = main_guid.split('imdb://')[1].split('?')[0].split('/')[0]
            
            items.append(item_data)
        
        if debug:
            with_tmdb = sum(1 for i in items if i.get('tmdbId'))
            with_tvdb = sum(1 for i in items if i.get('tvdbId'))
            with_imdb = sum(1 for i in items if i.get('imdbId'))
            print(f"{BLUE}[DEBUG] Items with TMDB ID: {with_tmdb}, TVDB ID: {with_tvdb}, IMDB ID: {with_imdb}{RESET}")
            
            modified = [i for i in items if i.get('titleSort', '').startswith('!')]
            if modified:
                print(f"{BLUE}[DEBUG] Found {len(modified)} items with modified sort titles (starting with '!'){RESET}")
                for m in modified[:5]:
                    print(f"{BLUE}[DEBUG]   - {m.get('title')}: titleSort='{m.get('titleSort')}'{RESET}")
        
        return items
    except requests.exceptions.RequestException as e:
        print(f"{RED}Error fetching Plex library items: {str(e)}{RESET}")
        if debug:
            import traceback
            traceback.print_exc()
        return []


def get_plex_show_episodes(plex_url, plex_token, show_rating_key, season_number=0, episode_number=0, debug=False):
    """Get specific episode from a TV show"""
    try:
        url = f"{plex_url.rstrip('/')}/library/metadata/{show_rating_key}/children"
        headers = {
            "X-Plex-Token": plex_token,
            "Accept": "application/json"
        }
        
        if debug:
            print(f"{BLUE}[DEBUG] Fetching seasons for show {show_rating_key}{RESET}")
        
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        seasons = data.get('MediaContainer', {}).get('Metadata', [])
        
        if debug:
            print(f"{BLUE}[DEBUG] Found {len(seasons)} seasons{RESET}")
            for s in seasons:
                print(f"{BLUE}[DEBUG]   Season index: {s.get('index')}, title: {s.get('title')}{RESET}")
        
        for season in seasons:
            if season.get('index') == season_number:
                season_key = season.get('ratingKey')
                
                if debug:
                    print(f"{BLUE}[DEBUG] Found season {season_number}, ratingKey: {season_key}{RESET}")
                
                episodes_url = f"{plex_url.rstrip('/')}/library/metadata/{season_key}/children"
                episodes_response = requests.get(episodes_url, headers=headers, timeout=30)
                episodes_response.raise_for_status()
                
                episodes_data = episodes_response.json()
                episodes = episodes_data.get('MediaContainer', {}).get('Metadata', [])
                
                if debug:
                    print(f"{BLUE}[DEBUG] Found {len(episodes)} episodes in season {season_number}{RESET}")
                    for ep in episodes:
                        print(f"{BLUE}[DEBUG]   Episode index: {ep.get('index')}, title: {ep.get('title')}{RESET}")
                
                for episode in episodes:
                    if episode.get('index') == episode_number:
                        return {
                            'ratingKey': episode.get('ratingKey'),
                            'title': episode.get('title'),
                            'index': episode.get('index'),
                            'parentIndex': episode.get('parentIndex')
                        }
        
        if debug:
            print(f"{ORANGE}[DEBUG] Season {season_number} Episode {episode_number} not found{RESET}")
        
        return None
    except requests.exceptions.RequestException as e:
        if debug:
            print(f"{ORANGE}[DEBUG] Error fetching episode: {str(e)}{RESET}")
        return None


def update_plex_sort_title(plex_url, plex_token, rating_key, new_sort_title, debug=False):
    """Update the sort title of a Plex item"""
    try:
        url = f"{plex_url.rstrip('/')}/library/metadata/{rating_key}"
        headers = {
            "X-Plex-Token": plex_token
        }
        params = {
            "titleSort.value": new_sort_title,
            "titleSort.locked": 1
        }
        
        if debug:
            print(f"{BLUE}[DEBUG] Updating sort title - URL: {url}, params: {params}{RESET}")
        
        response = requests.put(url, headers=headers, params=params, timeout=30)
        response.raise_for_status()
        
        if debug:
            print(f"{BLUE}[DEBUG] Response status: {response.status_code}{RESET}")
        
        return True
    except requests.exceptions.RequestException as e:
        print(f"{RED}Error updating sort title: {str(e)}{RESET}")
        if debug:
            import traceback
            traceback.print_exc()
        return False


def update_plex_episode_title(plex_url, plex_token, rating_key, new_title, debug=False):
    """Update the title of a Plex episode"""
    try:
        url = f"{plex_url.rstrip('/')}/library/metadata/{rating_key}"
        headers = {
            "X-Plex-Token": plex_token
        }
        params = {
            "title.value": new_title,
            "title.locked": 1
        }
        
        if debug:
            print(f"{BLUE}[DEBUG] Updating episode title - URL: {url}, params: {params}{RESET}")
        
        response = requests.put(url, headers=headers, params=params, timeout=30)
        response.raise_for_status()
        
        if debug:
            print(f"{BLUE}[DEBUG] Response status: {response.status_code}{RESET}")
        
        return True
    except requests.exceptions.RequestException as e:
        print(f"{RED}Error updating episode title: {str(e)}{RESET}")
        if debug:
            import traceback
            traceback.print_exc()
        return False


def reset_plex_sort_title(plex_url, plex_token, rating_key, original_title, debug=False):
    """Reset the sort title of a Plex item to its original title (unlocked)"""
    try:
        url = f"{plex_url.rstrip('/')}/library/metadata/{rating_key}"
        headers = {
            "X-Plex-Token": plex_token
        }
        clean_title = sanitize_sort_title(original_title)
        params = {
            "titleSort.value": clean_title,
            "titleSort.locked": 0
        }
        
        if debug:
            print(f"{BLUE}[DEBUG] Resetting sort title - URL: {url}, params: {params}{RESET}")
        
        response = requests.put(url, headers=headers, params=params, timeout=30)
        response.raise_for_status()
        
        if debug:
            print(f"{BLUE}[DEBUG] Response status: {response.status_code}{RESET}")
        
        return True
    except requests.exceptions.RequestException as e:
        print(f"{RED}Error resetting sort title: {str(e)}{RESET}")
        if debug:
            import traceback
            traceback.print_exc()
        return False


def check_show_has_previous_seasons(plex_url, plex_token, show_rating_key, debug=False):
    """Check if a TV show has any previous seasons (Season 1+) with downloaded episodes"""
    try:
        url = f"{plex_url.rstrip('/')}/library/metadata/{show_rating_key}/children"
        headers = {
            "X-Plex-Token": plex_token,
            "Accept": "application/json"
        }
        
        if debug:
            print(f"{BLUE}[DEBUG] Checking for previous seasons for show {show_rating_key}{RESET}")
        
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        seasons = data.get('MediaContainer', {}).get('Metadata', [])
        
        for season in seasons:
            season_index = season.get('index', 0)
            
            if season_index == 0:
                continue
            
            leaf_count = season.get('leafCount', 0)
            
            if debug:
                print(f"{BLUE}[DEBUG]   Season {season_index}: leafCount={leaf_count}{RESET}")
            
            if leaf_count > 0:
                if debug:
                    print(f"{BLUE}[DEBUG]   Found previous content in Season {season_index}{RESET}")
                return True
        
        if debug:
            print(f"{BLUE}[DEBUG]   No previous seasons with content found{RESET}")
        
        return False
        
    except requests.exceptions.RequestException as e:
        if debug:
            print(f"{ORANGE}[DEBUG] Error checking for previous seasons: {str(e)}{RESET}")
        return True


def update_plex_tv_metadata(plex_url, plex_token, tv_libraries, all_shows_with_content, 
                            mdblist_tv_items, config, debug=False, retry_count=0, max_retries=4):
    """Update TV show metadata directly in Plex"""
    append_dates = str(config.get("append_dates_to_sort_titles", "true")).lower() == "true"
    add_rank_to_sort_title = str(config.get("add_rank_to_sort_title", "false")).lower() == "true"
    edit_episode_titles = str(config.get("edit_S00E00_episode_title", "false")).lower() == "true"
    
    if debug:
        print(f"{BLUE}[DEBUG] Plex TV metadata update settings:{RESET}")
        print(f"{BLUE}[DEBUG]   append_dates_to_sort_titles: {append_dates}{RESET}")
        print(f"{BLUE}[DEBUG]   add_rank_to_sort_title: {add_rank_to_sort_title}{RESET}")
        print(f"{BLUE}[DEBUG]   edit_S00E00_episode_title: {edit_episode_titles}{RESET}")
        print(f"{BLUE}[DEBUG]   all_shows_with_content count: {len(all_shows_with_content)}{RESET}")
        print(f"{BLUE}[DEBUG]   mdblist_tv_items count: {len(mdblist_tv_items) if mdblist_tv_items else 0}{RESET}")
    
    if not append_dates and not add_rank_to_sort_title and not edit_episode_titles:
        if debug:
            print(f"{BLUE}[DEBUG] All Plex TV metadata options disabled, skipping{RESET}")
        return
    
    libraries = get_plex_libraries(plex_url, plex_token, debug)
    
    if not libraries:
        print(f"{RED}Could not fetch Plex libraries{RESET}")
        return
    
    if isinstance(tv_libraries, str):
        tv_library_names = [lib.strip() for lib in tv_libraries.split(',') if lib.strip()]
    else:
        tv_library_names = tv_libraries if tv_libraries else []
    
    if debug:
        print(f"{BLUE}[DEBUG] Configured TV libraries: {tv_library_names}{RESET}")
        print(f"{BLUE}[DEBUG] Available Plex libraries: {list(libraries.keys())}{RESET}")
    
    if not tv_library_names:
        print(f"{ORANGE}No TV libraries configured for Plex metadata updates{RESET}")
        return
    
    all_plex_items = []
    
    for lib_name in tv_library_names:
        if lib_name in libraries and libraries[lib_name]['type'] == 'show':
            lib_key = libraries[lib_name]['key']
            items = get_plex_library_items(plex_url, plex_token, lib_key, debug)
            all_plex_items.extend(items)
            print(f"{GREEN}Found {len(items)} shows in Plex library: {lib_name}{RESET}")
        else:
            print(f"{ORANGE}TV library '{lib_name}' not found in Plex or is not a show library{RESET}")
            if debug:
                matching = [k for k in libraries.keys() if lib_name.lower() in k.lower()]
                if matching:
                    print(f"{BLUE}[DEBUG] Did you mean one of these? {matching}{RESET}")
    
    if not all_plex_items:
        print(f"{ORANGE}No TV items found in configured Plex libraries{RESET}")
        return
    
    valid_date_tvdb_ids = set()
    valid_rank_tvdb_ids = {}
    shows_with_content = {}
    
    if add_rank_to_sort_title and mdblist_tv_items:
        for item in mdblist_tv_items:
            if item.get('rank') and item.get('tvdb_id'):
                valid_rank_tvdb_ids[str(item['tvdb_id'])] = item['rank']
        if debug:
            print(f"{BLUE}[DEBUG] Valid rank TVDB IDs: {valid_rank_tvdb_ids}{RESET}")
    
    for show in all_shows_with_content:
        tvdb_id = show.get('tvdbId')
        if tvdb_id:
            tvdb_id_str = str(tvdb_id)
            shows_with_content[tvdb_id_str] = show
            
            if append_dates and tvdb_id_str not in valid_rank_tvdb_ids and show.get('airDate'):
                valid_date_tvdb_ids.add(tvdb_id_str)
    
    if debug:
        print(f"{BLUE}[DEBUG] Shows with content TVDB IDs: {list(shows_with_content.keys())}{RESET}")
        print(f"{BLUE}[DEBUG] Valid date TVDB IDs: {valid_date_tvdb_ids}{RESET}")
    
    plex_items_by_tvdb = {}
    for plex_item in all_plex_items:
        tvdb_id = plex_item.get('tvdbId')
        if tvdb_id:
            plex_items_by_tvdb[str(tvdb_id)] = plex_item
    
    missing_items = []
    all_target_tvdb_ids = set(valid_date_tvdb_ids) | set(valid_rank_tvdb_ids.keys()) | set(shows_with_content.keys())
    
    for tvdb_id in all_target_tvdb_ids:
        if tvdb_id not in plex_items_by_tvdb:
            show_title = "Unknown"
            if tvdb_id in shows_with_content:
                show_title = shows_with_content[tvdb_id].get('title', 'Unknown')
            missing_items.append({'tvdb_id': tvdb_id, 'title': show_title})
    
    if missing_items and retry_count < max_retries:
        print(f"{ORANGE}The following {len(missing_items)} item(s) are not yet present in Plex:{RESET}")
        for item in missing_items:
            print(f"  - {item['title']} (TVDB: {item['tvdb_id']})")
        print(f"{ORANGE}Waiting 1 minute before retry ({retry_count + 1}/{max_retries + 1})...{RESET}")
        time.sleep(60)
        return update_plex_tv_metadata(plex_url, plex_token, tv_libraries, all_shows_with_content,
                                       mdblist_tv_items, config, debug, retry_count + 1, max_retries)
    
    if missing_items:
        print(f"{RED}The following item(s) could not be found in Plex after {max_retries + 1} attempts:{RESET}")
        for item in missing_items:
            print(f"  - {item['title']} (TVDB: {item['tvdb_id']})")
    
    updated_sort_titles = 0
    updated_episode_titles = 0
    reset_sort_titles = 0
    
    for plex_item in all_plex_items:
        tvdb_id = plex_item.get('tvdbId')
        rating_key = plex_item.get('ratingKey')
        current_sort_title = plex_item.get('titleSort', '')
        original_title = plex_item.get('title', '')
        
        has_modified_sort = False
        if current_sort_title and current_sort_title.startswith('!'):
            if len(current_sort_title) > 9 and current_sort_title[1:9].isdigit():
                has_modified_sort = True
            elif len(current_sort_title) > 3 and current_sort_title[1:3].isdigit():
                has_modified_sort = True
        
        if not tvdb_id:
            if has_modified_sort:
                if debug:
                    print(f"{BLUE}[DEBUG] Item '{original_title}' has modified sort title but no TVDB ID - resetting{RESET}")
                if reset_plex_sort_title(plex_url, plex_token, rating_key, original_title, debug):
                    reset_sort_titles += 1
                    print(f"{GREEN}Reset sort title for {original_title} (no TVDB ID){RESET}")
            continue
        
        tvdb_id_str = str(tvdb_id)
        
        should_have_rank = tvdb_id_str in valid_rank_tvdb_ids
        should_have_date = tvdb_id_str in valid_date_tvdb_ids
        
        if debug and (should_have_rank or should_have_date or has_modified_sort):
            print(f"{BLUE}[DEBUG] Processing '{original_title}' (TVDB: {tvdb_id_str}){RESET}")
            print(f"{BLUE}[DEBUG]   current_sort_title: '{current_sort_title}'{RESET}")
            print(f"{BLUE}[DEBUG]   has_modified_sort: {has_modified_sort}{RESET}")
            print(f"{BLUE}[DEBUG]   should_have_rank: {should_have_rank}{RESET}")
            print(f"{BLUE}[DEBUG]   should_have_date: {should_have_date}{RESET}")
        
        if should_have_rank:
            rank = valid_rank_tvdb_ids[tvdb_id_str]
            rank_str = f"{int(rank):02d}"
            sanitized_title = sanitize_sort_title(original_title)
            new_sort_title = f"!{rank_str} {sanitized_title}"
            
            if current_sort_title != new_sort_title:
                if debug:
                    print(f"{BLUE}[DEBUG] Will update sort title from '{current_sort_title}' to '{new_sort_title}'{RESET}")
                if update_plex_sort_title(plex_url, plex_token, rating_key, new_sort_title, debug):
                    updated_sort_titles += 1
                    print(f"{GREEN}Updated sort title for {original_title}: {new_sort_title}{RESET}")
        
        elif should_have_date:
            show_data = shows_with_content.get(tvdb_id_str)
            if show_data and show_data.get('airDate'):
                date_str = show_data['airDate'].replace('-', '')
                sanitized_title = sanitize_sort_title(original_title)
                new_sort_title = f"!{date_str} {sanitized_title}"
                
                if current_sort_title != new_sort_title:
                    if debug:
                        print(f"{BLUE}[DEBUG] Will update sort title from '{current_sort_title}' to '{new_sort_title}'{RESET}")
                    if update_plex_sort_title(plex_url, plex_token, rating_key, new_sort_title, debug):
                        updated_sort_titles += 1
                        print(f"{GREEN}Updated sort title for {original_title}: {new_sort_title}{RESET}")
        
        elif has_modified_sort:
            has_previous_content = check_show_has_previous_seasons(plex_url, plex_token, rating_key, debug)
            
            if has_previous_content:
                if debug:
                    print(f"{BLUE}[DEBUG] Skipping sort title reset for '{original_title}' - has previous seasons with content{RESET}")
                continue
            
            if debug:
                print(f"{BLUE}[DEBUG] Will reset sort title for '{original_title}'{RESET}")
            if reset_plex_sort_title(plex_url, plex_token, rating_key, original_title, debug):
                reset_sort_titles += 1
                print(f"{GREEN}Reset sort title for {original_title}{RESET}")
        
        if edit_episode_titles and tvdb_id_str in shows_with_content:
            show_data = shows_with_content[tvdb_id_str]
            used_trailer = show_data.get('used_trailer', False)
            episode_title = "Trailer" if used_trailer else "Coming Soon"
            
            if debug:
                print(f"{BLUE}[DEBUG] Checking S00E00 for '{original_title}' (used_trailer: {used_trailer}){RESET}")
            
            episode = get_plex_show_episodes(plex_url, plex_token, rating_key, 0, 0, debug)
            if episode:
                current_ep_title = episode.get('title', '')
                if current_ep_title != episode_title:
                    if debug:
                        print(f"{BLUE}[DEBUG] Will update episode title from '{current_ep_title}' to '{episode_title}'{RESET}")
                    if update_plex_episode_title(plex_url, plex_token, episode['ratingKey'], episode_title, debug):
                        updated_episode_titles += 1
                        print(f"{GREEN}Updated S00E00 title for {original_title}: {episode_title}{RESET}")
                elif debug:
                    print(f"{BLUE}[DEBUG] Episode title already correct: '{current_ep_title}'{RESET}")
            elif debug:
                print(f"{ORANGE}[DEBUG] S00E00 not found for '{original_title}'{RESET}")
    
    print(f"\n{GREEN}TV Plex metadata update summary:{RESET}")
    print(f"Sort titles updated: {updated_sort_titles}")
    print(f"Sort titles reset: {reset_sort_titles}")
    if edit_episode_titles:
        print(f"Episode titles updated: {updated_episode_titles}")


def update_plex_movie_metadata(plex_url, plex_token, movie_libraries, all_movies_with_content,
                               mdblist_movies_items, config, debug=False, retry_count=0, max_retries=4):
    """Update movie metadata directly in Plex"""
    append_dates = str(config.get("append_dates_to_sort_titles", "true")).lower() == "true"
    add_rank_to_sort_title = str(config.get("add_rank_to_sort_title", "false")).lower() == "true"
    
    if debug:
        print(f"{BLUE}[DEBUG] Plex movie metadata update settings:{RESET}")
        print(f"{BLUE}[DEBUG]   append_dates_to_sort_titles: {append_dates}{RESET}")
        print(f"{BLUE}[DEBUG]   add_rank_to_sort_title: {add_rank_to_sort_title}{RESET}")
        print(f"{BLUE}[DEBUG]   all_movies_with_content count: {len(all_movies_with_content)}{RESET}")
        print(f"{BLUE}[DEBUG]   mdblist_movies_items count: {len(mdblist_movies_items) if mdblist_movies_items else 0}{RESET}")
    
    if not append_dates and not add_rank_to_sort_title:
        if debug:
            print(f"{BLUE}[DEBUG] Both append_dates and add_rank disabled, skipping movie metadata updates{RESET}")
        return
    
    libraries = get_plex_libraries(plex_url, plex_token, debug)
    
    if not libraries:
        print(f"{RED}Could not fetch Plex libraries{RESET}")
        return
    
    if isinstance(movie_libraries, str):
        movie_library_names = [lib.strip() for lib in movie_libraries.split(',') if lib.strip()]
    else:
        movie_library_names = movie_libraries if movie_libraries else []
    
    if debug:
        print(f"{BLUE}[DEBUG] Configured movie libraries: {movie_library_names}{RESET}")
        print(f"{BLUE}[DEBUG] Available Plex libraries: {list(libraries.keys())}{RESET}")
    
    if not movie_library_names:
        print(f"{ORANGE}No movie libraries configured for Plex metadata updates{RESET}")
        return
    
    all_plex_items = []
    
    for lib_name in movie_library_names:
        if lib_name in libraries and libraries[lib_name]['type'] == 'movie':
            lib_key = libraries[lib_name]['key']
            items = get_plex_library_items(plex_url, plex_token, lib_key, debug)
            all_plex_items.extend(items)
            print(f"{GREEN}Found {len(items)} movies in Plex library: {lib_name}{RESET}")
        else:
            print(f"{ORANGE}Movie library '{lib_name}' not found in Plex or is not a movie library{RESET}")
            if debug:
                matching = [k for k in libraries.keys() if lib_name.lower() in k.lower()]
                if matching:
                    print(f"{BLUE}[DEBUG] Did you mean one of these? {matching}{RESET}")
    
    if not all_plex_items:
        print(f"{ORANGE}No movie items found in configured Plex libraries{RESET}")
        return
    
    valid_date_tmdb_ids = set()
    valid_rank_tmdb_ids = {}
    movies_with_content = {}
    
    if add_rank_to_sort_title and mdblist_movies_items:
        for item in mdblist_movies_items:
            tmdb_id = item.get('tmdb_id') or item.get('id')
            if item.get('rank') and tmdb_id:
                valid_rank_tmdb_ids[str(tmdb_id)] = item['rank']
        if debug:
            print(f"{BLUE}[DEBUG] Valid rank TMDB IDs: {valid_rank_tmdb_ids}{RESET}")
    
    for movie in all_movies_with_content:
        tmdb_id = movie.get('tmdbId')
        if tmdb_id:
            tmdb_id_str = str(tmdb_id)
            movies_with_content[tmdb_id_str] = movie
            
            if append_dates and tmdb_id_str not in valid_rank_tmdb_ids and movie.get('releaseDate'):
                valid_date_tmdb_ids.add(tmdb_id_str)
    
    if debug:
        print(f"{BLUE}[DEBUG] Movies with content TMDB IDs: {list(movies_with_content.keys())}{RESET}")
        print(f"{BLUE}[DEBUG] Valid date TMDB IDs: {valid_date_tmdb_ids}{RESET}")
    
    plex_items_by_tmdb = {}
    for plex_item in all_plex_items:
        tmdb_id = plex_item.get('tmdbId')
        if tmdb_id:
            plex_items_by_tmdb[str(tmdb_id)] = plex_item
    
    missing_items = []
    all_target_tmdb_ids = set(valid_date_tmdb_ids) | set(valid_rank_tmdb_ids.keys()) | set(movies_with_content.keys())
    
    for tmdb_id in all_target_tmdb_ids:
        if tmdb_id not in plex_items_by_tmdb:
            movie_title = "Unknown"
            if tmdb_id in movies_with_content:
                movie_title = movies_with_content[tmdb_id].get('title', 'Unknown')
            missing_items.append({'tmdb_id': tmdb_id, 'title': movie_title})
    
    if missing_items and retry_count < max_retries:
        print(f"{ORANGE}The following {len(missing_items)} item(s) are not yet present in Plex:{RESET}")
        for item in missing_items:
            print(f"  - {item['title']} (TMDB: {item['tmdb_id']})")
        print(f"{ORANGE}Waiting 1 minute before retry ({retry_count + 1}/{max_retries + 1})...{RESET}")
        time.sleep(60)
        return update_plex_movie_metadata(plex_url, plex_token, movie_libraries, all_movies_with_content,
                                          mdblist_movies_items, config, debug, retry_count + 1, max_retries)
    
    if missing_items:
        print(f"{RED}The following item(s) could not be found in Plex after {max_retries + 1} attempts:{RESET}")
        for item in missing_items:
            print(f"  - {item['title']} (TMDB: {item['tmdb_id']})")
    
    updated_sort_titles = 0
    reset_sort_titles = 0
    
    for plex_item in all_plex_items:
        tmdb_id = plex_item.get('tmdbId')
        rating_key = plex_item.get('ratingKey')
        current_sort_title = plex_item.get('titleSort', '')
        original_title = plex_item.get('title', '')
        
        has_modified_sort = False
        if current_sort_title and current_sort_title.startswith('!'):
            if len(current_sort_title) > 9 and current_sort_title[1:9].isdigit():
                has_modified_sort = True
            elif len(current_sort_title) > 3 and current_sort_title[1:3].isdigit():
                has_modified_sort = True
        
        if not tmdb_id:
            if has_modified_sort:
                if debug:
                    print(f"{BLUE}[DEBUG] Item '{original_title}' has modified sort title but no TMDB ID - resetting{RESET}")
                if reset_plex_sort_title(plex_url, plex_token, rating_key, original_title, debug):
                    reset_sort_titles += 1
                    print(f"{GREEN}Reset sort title for {original_title} (no TMDB ID){RESET}")
            continue
        
        tmdb_id_str = str(tmdb_id)
        
        should_have_rank = tmdb_id_str in valid_rank_tmdb_ids
        should_have_date = tmdb_id_str in valid_date_tmdb_ids
        
        if debug and (should_have_rank or should_have_date or has_modified_sort):
            print(f"{BLUE}[DEBUG] Processing '{original_title}' (TMDB: {tmdb_id_str}){RESET}")
            print(f"{BLUE}[DEBUG]   current_sort_title: '{current_sort_title}'{RESET}")
            print(f"{BLUE}[DEBUG]   has_modified_sort: {has_modified_sort}{RESET}")
            print(f"{BLUE}[DEBUG]   should_have_rank: {should_have_rank}{RESET}")
            print(f"{BLUE}[DEBUG]   should_have_date: {should_have_date}{RESET}")
        
        if should_have_rank:
            rank = valid_rank_tmdb_ids[tmdb_id_str]
            rank_str = f"{int(rank):02d}"
            sanitized_title = sanitize_sort_title(original_title)
            new_sort_title = f"!{rank_str} {sanitized_title}"
            
            if current_sort_title != new_sort_title:
                if debug:
                    print(f"{BLUE}[DEBUG] Will update sort title from '{current_sort_title}' to '{new_sort_title}'{RESET}")
                if update_plex_sort_title(plex_url, plex_token, rating_key, new_sort_title, debug):
                    updated_sort_titles += 1
                    print(f"{GREEN}Updated sort title for {original_title}: {new_sort_title}{RESET}")
        
        elif should_have_date:
            movie_data = movies_with_content.get(tmdb_id_str)
            if movie_data and movie_data.get('releaseDate'):
                date_str = movie_data['releaseDate'].replace('-', '')
                sanitized_title = sanitize_sort_title(original_title)
                new_sort_title = f"!{date_str} {sanitized_title}"
                
                if current_sort_title != new_sort_title:
                    if debug:
                        print(f"{BLUE}[DEBUG] Will update sort title from '{current_sort_title}' to '{new_sort_title}'{RESET}")
                    if update_plex_sort_title(plex_url, plex_token, rating_key, new_sort_title, debug):
                        updated_sort_titles += 1
                        print(f"{GREEN}Updated sort title for {original_title}: {new_sort_title}{RESET}")
        
        elif has_modified_sort:
            if debug:
                print(f"{BLUE}[DEBUG] Will reset sort title for '{original_title}'{RESET}")
            if reset_plex_sort_title(plex_url, plex_token, rating_key, original_title, debug):
                reset_sort_titles += 1
                print(f"{GREEN}Reset sort title for {original_title}{RESET}")
    
    print(f"\n{GREEN}Movie Plex metadata update summary:{RESET}")
    print(f"Sort titles updated: {updated_sort_titles}")
    print(f"Sort titles reset: {reset_sort_titles}")