"""
Sonarr API integration for UMTK
"""

import requests
from datetime import datetime, timedelta, timezone

from .constants import GREEN, ORANGE, RED, BLUE, RESET
from .utils import convert_utc_to_local, request_with_retry


def process_sonarr_url(base_url, api_key, timeout=90):
    """Process and validate Sonarr URL"""
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
    # /sonarr2), then fall back to host-stripped guesses. De-duplicate so a bare
    # host doesn't get probed twice.
    candidates = []
    for url in (f"{base_url}/api/v3", f"{host}/api/v3", f"{host}/sonarr/api/v3"):
        if url not in candidates:
            candidates.append(url)

    last_error = None
    for test_url in candidates:
        try:
            headers = {"X-Api-Key": api_key}
            response = requests.get(f"{test_url}/health", headers=headers, timeout=timeout)
            if response.status_code == 200:
                print(f"{GREEN}Successfully connected to Sonarr at: {test_url}{RESET}")
                return test_url
            else:
                print(f"{ORANGE}Testing URL {test_url} - Failed: HTTP {response.status_code}{RESET}")
        except requests.exceptions.RequestException as e:
            print(f"{ORANGE}Testing URL {test_url} - Failed: {str(e)}{RESET}")
            last_error = e
            continue

    error_msg = f"Unable to establish connection to Sonarr. Tried the following URLs:\n" + \
                "\n".join([f"- {url}" for url in candidates]) + \
                f"\nPlease verify your URL and API key and ensure Sonarr is running."
    if last_error:
        error_msg += f"\nLast error: {str(last_error)}"
    
    raise ConnectionError(f"{RED}{error_msg}{RESET}")


def get_sonarr_series(sonarr_url, api_key, timeout=90):
    """Get all series from Sonarr"""
    try:
        print(f"{BLUE}Fetching series from Sonarr...{RESET}", flush=True)
        url = f"{sonarr_url}/series"
        headers = {"X-Api-Key": api_key}
        response = request_with_retry('GET', url, headers=headers, timeout=timeout)
        response.raise_for_status()
        series_data = response.json()
        print(f"{GREEN}Done ✓ ({len(series_data)} series){RESET}")
        return series_data
    except requests.exceptions.Timeout as e:
        print(f" {RED}✗{RESET}")
        print(f"{RED}Timeout connecting to Sonarr (exceeded {timeout}s): {str(e)}{RESET}")
        raise
    except requests.exceptions.ConnectionError as e:
        print(f" {RED}✗{RESET}")
        print(f"{RED}Connection error to Sonarr: {str(e)}{RESET}")
        raise
    except requests.exceptions.RequestException as e:
        print(f" {RED}✗{RESET}")
        print(f"{RED}Error connecting to Sonarr: {str(e)}{RESET}")
        raise


def get_sonarr_episodes(sonarr_url, api_key, series_id, timeout=90):
    """Get episodes for a specific series"""
    try:
        url = f"{sonarr_url}/episode?seriesId={series_id}"
        headers = {"X-Api-Key": api_key}
        response = request_with_retry('GET', url, headers=headers, timeout=timeout)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.Timeout as e:
        print(f"{RED}Timeout fetching episodes from Sonarr (exceeded {timeout}s): {str(e)}{RESET}")
        raise
    except requests.exceptions.ConnectionError as e:
        print(f"{RED}Connection error fetching episodes from Sonarr: {str(e)}{RESET}")
        raise
    except requests.exceptions.RequestException as e:
        print(f"{RED}Error fetching episodes from Sonarr: {str(e)}{RESET}")
        raise