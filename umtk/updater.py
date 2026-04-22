"""Version checking for UMTK via GitHub releases API."""

import requests
from .constants import VERSION


def check_for_updates() -> None:
    """Check GitHub for newer versions (console output)."""
    try:
        print("Checking for updates...", end=" ", flush=True)
        url = "https://api.github.com/repos/netplexflix/Upcoming-Movies-TV-Shows-for-Kometa/releases/latest"
        resp = requests.get(url, timeout=5)
        resp.raise_for_status()
        latest = resp.json().get("tag_name", "").lstrip("v")
        if not latest:
            print("Could not determine latest version")
            return

        def parse_version(v):
            return tuple(int(x) for x in v.split('.'))

        try:
            if parse_version(latest) > parse_version(VERSION):
                print("UPDATE AVAILABLE!")
                print(f"\n{'=' * 60}")
                print(f"Current version: {VERSION}")
                print(f"Latest version:  {latest}")
                print(f"Download: https://github.com/netplexflix/Upcoming-Movies-TV-Shows-for-Kometa/releases")
                print(f"{'=' * 60}\n")
            else:
                print(f"Up to date (v{VERSION})")
        except Exception:
            if latest != VERSION:
                print(f"Update may be available (current: {VERSION}, latest: {latest})")
            else:
                print(f"Up to date (v{VERSION})")
    except requests.exceptions.RequestException:
        print("Failed (network error)")
    except Exception:
        print("Failed (error)")


def get_update_status() -> dict:
    """Return update status as a dict for the web UI."""
    try:
        url = "https://api.github.com/repos/netplexflix/Upcoming-Movies-TV-Shows-for-Kometa/releases/latest"
        resp = requests.get(url, timeout=5)
        resp.raise_for_status()
        latest = resp.json().get("tag_name", "").lstrip("v")
        if not latest:
            return {"status": "unknown", "current": VERSION, "latest": None}

        def parse_version(v):
            return tuple(int(x) for x in v.split('.'))

        try:
            current = parse_version(VERSION)
            remote = parse_version(latest)
            if remote > current:
                status = "update_available"
            elif current > remote:
                status = "develop_build"
            else:
                status = "up_to_date"
        except Exception:
            status = "update_available" if latest != VERSION else "up_to_date"

        return {
            "status": status,
            "current": VERSION,
            "latest": latest,
        }
    except Exception:
        return {"status": "error", "current": VERSION, "latest": None}
