"""Sonarr API interaction functions for TSSK"""

import requests

from .constants import GREEN, BLUE, ORANGE, RED, RESET


def process_sonarr_url(base_url, api_key, timeout=90):
    """Process and validate Sonarr URL, trying different API paths"""
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


def get_sonarr_series_and_tags(sonarr_url, api_key, timeout=90):
    """Fetch all series and tags from Sonarr"""
    try:
        # Fetch series
        print(f"{BLUE}Fetching series from Sonarr...{RESET}", flush=True)
        series_url = f"{sonarr_url}/series"
        headers = {"X-Api-Key": api_key}
        series_response = requests.get(series_url, headers=headers, timeout=timeout)
        series_response.raise_for_status()
        series_data = series_response.json()
        print(f"{GREEN}Done ✓ ({len(series_data)} series){RESET}")

        # Fetch tags
        print(f"{BLUE}Fetching tags from Sonarr...{RESET}", flush=True)
        tags_url = f"{sonarr_url}/tag"
        tags_response = requests.get(tags_url, headers=headers, timeout=timeout)
        tags_response.raise_for_status()
        tags_data = tags_response.json()
        print(f"{GREEN}Done ✓ ({len(tags_data)} tags){RESET}\n")

        # Create tag mapping
        tag_mapping = {}
        for tag in tags_data:
            tag_mapping[tag.get('id')] = tag.get('label', '').lower()
        
        return series_data, tag_mapping
        
    except requests.exceptions.RequestException as e:
        print(f"{ORANGE}Warning: Error connecting to Sonarr: {str(e)}{RESET}")
        print(f"{ORANGE}Continuing with empty series list...{RESET}")
        return [], {}


def get_sonarr_episodes(sonarr_url, api_key, series_id, timeout=90):
    """Fetch all episodes for a specific series from Sonarr"""
    try:
        url = f"{sonarr_url}/episode?seriesId={series_id}"
        headers = {"X-Api-Key": api_key}
        response = requests.get(url, headers=headers, timeout=timeout)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"{ORANGE}Warning: Error fetching episodes for series {series_id}: {str(e)}{RESET}")
        print(f"{ORANGE}Skipping this series and continuing...{RESET}")
        return []


def has_ignore_finale_tag(series, ignore_finales_tags, tag_mapping):
    """Check if a series has any of the ignore finale tags"""
    if not ignore_finales_tags or not tag_mapping:
        return False
    
    series_tags = series.get('tags', [])
    if not series_tags:
        return False
    
    ignore_tags_lower = [tag.strip().lower() for tag in ignore_finales_tags]

    for tag_id in series_tags:
        tag_name = tag_mapping.get(tag_id, '').lower()
        if tag_name in ignore_tags_lower:
            return True
    
    return False