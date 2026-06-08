"""
Radarr API integration for UMTK
"""

import requests

from .constants import GREEN, ORANGE, RED, BLUE, RESET
from .utils import request_with_retry


def process_radarr_url(base_url, api_key, timeout=90):
    """Process and validate Radarr URL"""
    base_url = base_url.rstrip('/')

    # Tolerate a pasted .../api/v3 suffix so we don't probe /api/v3/api/v3
    if base_url.endswith('/api/v3'):
        base_url = base_url[:-len('/api/v3')]

    # Host = base stripped to scheme+host, used for fallback guesses
    host = base_url
    if base_url.startswith('http'):
        protocol_end = base_url.find('://') + 3
        next_slash = base_url.find('/', protocol_end)
        if next_slash != -1:
            host = base_url[:next_slash]

    # Try the full configured URL first (preserves reverse-proxy subpaths like
    # /radarr2), then fall back to host-stripped guesses. De-duplicate so a bare
    # host doesn't get probed twice.
    candidates = []
    for url in (f"{base_url}/api/v3", f"{host}/api/v3", f"{host}/radarr/api/v3"):
        if url not in candidates:
            candidates.append(url)

    for test_url in candidates:
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
                        "\n".join([f"- {url}" for url in candidates]) +
                        f"\nPlease verify your URL and API key and ensure Radarr is running.{RESET}")


def get_radarr_movies(radarr_url, api_key, timeout=90):
    """Get all movies from Radarr"""
    try:
        print(f"{BLUE}Fetching movies from Radarr...{RESET}", flush=True)
        url = f"{radarr_url}/movie"
        headers = {"X-Api-Key": api_key}
        response = request_with_retry('GET', url, headers=headers, timeout=timeout)
        response.raise_for_status()
        movies_data = response.json()
        print(f"{GREEN}Done ✓ ({len(movies_data)} movies){RESET}")
        return movies_data
    except requests.exceptions.RequestException as e:
        print(f" {RED}✗{RESET}")
        print(f"{RED}Error connecting to Radarr: {str(e)}{RESET}")
        import sys
        sys.exit(1)