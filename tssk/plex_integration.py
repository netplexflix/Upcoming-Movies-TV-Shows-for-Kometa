"""Plex API integration for TSSK - direct sort title management"""

import requests

from .constants import GREEN, ORANGE, BLUE, RED, RESET
from .utils import sanitize_show_title, debug_print


TSSK_SUFFIX = "(TSSK)"


def get_plex_libraries(plex_url, plex_token, config):
    """Get all Plex libraries and their keys"""
    try:
        url = f"{plex_url.rstrip('/')}/library/sections"
        headers = {
            "X-Plex-Token": plex_token,
            "Accept": "application/json"
        }

        debug_print(f"{BLUE}[DEBUG] Fetching Plex libraries from: {url}{RESET}", config)

        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()

        data = response.json()
        libraries = {}

        for directory in data.get('MediaContainer', {}).get('Directory', []):
            lib_name = directory.get('title')
            lib_key = directory.get('key')
            lib_type = directory.get('type')
            if lib_name and lib_key:
                libraries[lib_name] = {'key': lib_key, 'type': lib_type}
                debug_print(f"{BLUE}[DEBUG] Found Plex library: {lib_name} (key: {lib_key}, type: {lib_type}){RESET}", config)

        return libraries
    except requests.exceptions.RequestException as e:
        print(f"{RED}Error fetching Plex libraries: {str(e)}{RESET}")
        return {}


def get_plex_library_items(plex_url, plex_token, library_key, config):
    """Get all items from a Plex library with their sort titles and external IDs"""
    try:
        url = f"{plex_url.rstrip('/')}/library/sections/{library_key}/all?includeGuids=1"
        headers = {
            "X-Plex-Token": plex_token,
            "Accept": "application/json"
        }

        debug_print(f"{BLUE}[DEBUG] Fetching Plex library items from: {url}{RESET}", config)

        response = requests.get(url, headers=headers, timeout=60)
        response.raise_for_status()

        data = response.json()
        items = []

        metadata_list = data.get('MediaContainer', {}).get('Metadata', [])

        debug_print(f"{BLUE}[DEBUG] Raw response contains {len(metadata_list)} items{RESET}", config)

        for item in metadata_list:
            item_data = {
                'ratingKey': item.get('ratingKey'),
                'title': item.get('title'),
                'titleSort': item.get('titleSort', ''),
                'year': item.get('year'),
                'guid': item.get('guid', ''),
            }

            guids = item.get('Guid', [])

            for guid_entry in guids:
                guid_id = guid_entry.get('id', '')
                if guid_id.startswith('tvdb://'):
                    item_data['tvdbId'] = guid_id.replace('tvdb://', '')
                elif guid_id.startswith('tmdb://'):
                    item_data['tmdbId'] = guid_id.replace('tmdb://', '')
                elif guid_id.startswith('imdb://'):
                    item_data['imdbId'] = guid_id.replace('imdb://', '')

            main_guid = item.get('guid', '')
            if 'tvdb://' in main_guid and 'tvdbId' not in item_data:
                item_data['tvdbId'] = main_guid.split('tvdb://')[1].split('?')[0].split('/')[0]
            elif 'tmdb://' in main_guid and 'tmdbId' not in item_data:
                item_data['tmdbId'] = main_guid.split('tmdb://')[1].split('?')[0].split('/')[0]
            elif 'imdb://' in main_guid and 'imdbId' not in item_data:
                item_data['imdbId'] = main_guid.split('imdb://')[1].split('?')[0].split('/')[0]

            items.append(item_data)

        return items
    except requests.exceptions.RequestException as e:
        print(f"{RED}Error fetching Plex library items: {str(e)}{RESET}")
        return []


def update_plex_sort_title(plex_url, plex_token, rating_key, new_sort_title, config):
    """Update the sort title of a Plex item (locked)"""
    try:
        url = f"{plex_url.rstrip('/')}/library/metadata/{rating_key}"
        headers = {
            "X-Plex-Token": plex_token
        }
        params = {
            "titleSort.value": new_sort_title,
            "titleSort.locked": 1
        }

        debug_print(f"{BLUE}[DEBUG] Updating sort title - URL: {url}, params: {params}{RESET}", config)

        response = requests.put(url, headers=headers, params=params, timeout=30)
        response.raise_for_status()

        return True
    except requests.exceptions.RequestException as e:
        print(f"{RED}Error updating sort title: {str(e)}{RESET}")
        return False


def reset_plex_sort_title(plex_url, plex_token, rating_key, original_title, config):
    """Reset the sort title of a Plex item to its original title (unlocked)"""
    try:
        url = f"{plex_url.rstrip('/')}/library/metadata/{rating_key}"
        headers = {
            "X-Plex-Token": plex_token
        }
        clean_title = sanitize_show_title(original_title)
        params = {
            "titleSort.value": clean_title,
            "titleSort.locked": 0
        }

        debug_print(f"{BLUE}[DEBUG] Resetting sort title - URL: {url}, params: {params}{RESET}", config)

        response = requests.put(url, headers=headers, params=params, timeout=30)
        response.raise_for_status()

        return True
    except requests.exceptions.RequestException as e:
        print(f"{RED}Error resetting sort title: {str(e)}{RESET}")
        return False


def update_plex_sort_titles(plex_url, plex_token, tv_libraries, matched_shows, all_series, config):
    """Update sort titles in Plex for matched shows, reset sort titles for shows no longer matching.

    Sort titles set by TSSK use the format: !{YYYYMMDD} {CleanTitle} (TSSK)
    The (TSSK) suffix allows UMTK to distinguish TSSK-managed sort titles and skip resetting them.
    """
    if not plex_url or not plex_token:
        debug_print(f"{BLUE}[DEBUG] Plex URL or token not configured, skipping sort title updates{RESET}", config)
        return

    libraries = get_plex_libraries(plex_url, plex_token, config)
    if not libraries:
        print(f"{RED}Could not fetch Plex libraries{RESET}")
        return

    if isinstance(tv_libraries, str):
        tv_library_names = [lib.strip() for lib in tv_libraries.split(',') if lib.strip()]
    else:
        tv_library_names = tv_libraries if tv_libraries else []

    debug_print(f"{BLUE}[DEBUG] Configured TV libraries: {tv_library_names}{RESET}", config)

    if not tv_library_names:
        print(f"{ORANGE}No TV libraries configured for Plex sort title updates{RESET}")
        return

    # Fetch all items from configured TV libraries
    all_plex_items = []
    for lib_name in tv_library_names:
        if lib_name in libraries and libraries[lib_name]['type'] == 'show':
            lib_key = libraries[lib_name]['key']
            items = get_plex_library_items(plex_url, plex_token, lib_key, config)
            all_plex_items.extend(items)
            print(f"{GREEN}Found {len(items)} shows in Plex library: {lib_name}{RESET}")
        else:
            print(f"{ORANGE}TV library '{lib_name}' not found in Plex or is not a show library{RESET}")

    if not all_plex_items:
        print(f"{ORANGE}No TV items found in configured Plex libraries{RESET}")
        return

    # Build set of TVDB IDs that should have modified sort titles
    valid_tvdb_ids = {}
    for show in matched_shows:
        tvdb_id = show.get('tvdbId')
        air_date = show.get('airDate')
        title = show.get('title', '')
        if tvdb_id and air_date and title:
            valid_tvdb_ids[str(tvdb_id)] = show

    debug_print(f"{BLUE}[DEBUG] Valid TVDB IDs for sort title: {list(valid_tvdb_ids.keys())}{RESET}", config)

    # Build Plex item index by TVDB ID
    plex_items_by_tvdb = {}
    for plex_item in all_plex_items:
        tvdb_id = plex_item.get('tvdbId')
        if tvdb_id:
            plex_items_by_tvdb[str(tvdb_id)] = plex_item

    updated_sort_titles = 0
    reset_sort_titles = 0

    for plex_item in all_plex_items:
        tvdb_id = plex_item.get('tvdbId')
        rating_key = plex_item.get('ratingKey')
        current_sort_title = plex_item.get('titleSort', '')
        original_title = plex_item.get('title', '')

        # Check if this item has a TSSK-modified sort title
        has_tssk_sort = (current_sort_title and
                         current_sort_title.rstrip().endswith(TSSK_SUFFIX))

        if not tvdb_id:
            continue

        tvdb_id_str = str(tvdb_id)
        should_have_date = tvdb_id_str in valid_tvdb_ids

        if should_have_date or has_tssk_sort:
            debug_print(f"{BLUE}[DEBUG] Processing '{original_title}' (TVDB: {tvdb_id_str}){RESET}", config)
            debug_print(f"{BLUE}[DEBUG]   current_sort_title: '{current_sort_title}'{RESET}", config)
            debug_print(f"{BLUE}[DEBUG]   has_tssk_sort: {has_tssk_sort}{RESET}", config)
            debug_print(f"{BLUE}[DEBUG]   should_have_date: {should_have_date}{RESET}", config)

        if should_have_date:
            show_data = valid_tvdb_ids[tvdb_id_str]
            date_str = show_data['airDate'].replace('-', '')
            clean_title = sanitize_show_title(show_data['title'])
            new_sort_title = f"!{date_str} {clean_title} {TSSK_SUFFIX}"

            if current_sort_title != new_sort_title:
                debug_print(f"{BLUE}[DEBUG] Will update sort title from '{current_sort_title}' to '{new_sort_title}'{RESET}", config)
                if update_plex_sort_title(plex_url, plex_token, rating_key, new_sort_title, config):
                    updated_sort_titles += 1
                    print(f"{GREEN}Updated sort title for {original_title}: {new_sort_title}{RESET}")

        elif has_tssk_sort:
            # Show has a TSSK sort title but is no longer in the matched list - reset it
            debug_print(f"{BLUE}[DEBUG] Will reset sort title for '{original_title}'{RESET}", config)
            if reset_plex_sort_title(plex_url, plex_token, rating_key, original_title, config):
                reset_sort_titles += 1
                print(f"{GREEN}Reset sort title for {original_title}{RESET}")

    print(f"\n{GREEN}TSSK Plex sort title update summary:{RESET}")
    print(f"Sort titles updated: {updated_sort_titles}")
    print(f"Sort titles reset: {reset_sort_titles}")
