"""
MDBList API integration for UMTK
"""

import requests

from .constants import GREEN, ORANGE, RED, BLUE, RESET


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
                mediatype = item.get('mediatype')
                
                # Normalize the item to match expected format
                normalized_item = {
                    'title': item.get('title', 'Unknown'),
                    'year': item.get('release_year'),
                    'imdb_id': item.get('imdb_id'),
                    'mediatype': mediatype,
                    'rank': item.get('rank')  # Preserve rank
                }
                
                # Handle IDs differently for movies vs TV shows
                if mediatype == 'movie':
                    # For movies, use 'id' field as TMDB ID
                    normalized_item['tmdb_id'] = item.get('id')
                elif mediatype == 'show':
                    # For TV shows, prefer tvdb_id but fallback to tmdb_id (from 'id' field)
                    tvdb_id = item.get('tvdb_id')
                    tmdb_id = item.get('id')
                    
                    if tvdb_id:
                        normalized_item['tvdb_id'] = tvdb_id
                        if debug:
                            print(f"{BLUE}[DEBUG] TV show '{item.get('title')}' using TVDB ID: {tvdb_id}{RESET}")
                    elif tmdb_id:
                        # Use TMDB ID as fallback
                        normalized_item['tmdb_id'] = tmdb_id
                        if debug:
                            print(f"{ORANGE}[DEBUG] TV show '{item.get('title')}' has no TVDB ID, using TMDB ID: {tmdb_id}{RESET}")
                    else:
                        if debug:
                            print(f"{ORANGE}[DEBUG] TV show '{item.get('title')}' has no TVDB or TMDB ID{RESET}")
                
                # Only add items that have at least one required ID
                if mediatype == 'movie' and normalized_item.get('tmdb_id'):
                    validated_items.append(normalized_item)
                elif mediatype == 'show' and (normalized_item.get('tvdb_id') or normalized_item.get('tmdb_id')):
                    validated_items.append(normalized_item)
                elif debug:
                    print(f"{ORANGE}[DEBUG] Skipping item without required ID: {item.get('title')} (mediatype: {mediatype}){RESET}")
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