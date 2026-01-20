"""
Radarr API integration for UMTK
"""

import requests

from .constants import GREEN, ORANGE, RED, BLUE, RESET


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
        import sys
        sys.exit(1)