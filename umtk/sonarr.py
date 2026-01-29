"""
Sonarr API integration for UMTK
"""

import requests
from datetime import datetime, timedelta, timezone

from .constants import GREEN, ORANGE, RED, BLUE, RESET
from .utils import convert_utc_to_local


def process_sonarr_url(base_url, api_key, timeout=90):
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
    
    last_error = None
    for path in api_paths:
        test_url = f"{base_url}{path}"
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
                "\n".join([f"- {base_url}{path}" for path in api_paths]) + \
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
        response = requests.get(url, headers=headers, timeout=timeout)
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
        response = requests.get(url, headers=headers, timeout=timeout)
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