"""Flask routes and config metadata for UMTK Web UI."""

import ipaddress
import os
import socket
import sys
import subprocess
import time
from urllib.parse import urlparse
import yaml
import requests
from datetime import datetime, timedelta
from flask import render_template, jsonify, request

# Placeholder used to mask sensitive values in API responses.
# If this exact value is sent back on save, it is ignored (the real value is kept).
MASKED_VALUE = "********"

import webui
from umtk.constants import VERSION
from umtk.updater import get_update_status
from umtk.config_loader import ensure_trending_requested_blocks


class _QuotedDumper(yaml.SafeDumper):
    """YAML dumper that always quotes string values."""
    pass


def _quoted_str(dumper, data):
    return dumper.represent_scalar('tag:yaml.org,2002:str', data, style="'")


_QuotedDumper.add_representer(str, _quoted_str)


# ── Section header comments for config files ───────────────────────────────
# These are re-inserted when saving to preserve the visual structure.

UMTK_SECTION_HEADERS = {
    'webui_auth_enabled': '################################################################################\n##########                           WEBUI:                           ##########\n################################################################################',
    'enable_umtk': '################################################################################\n##########                         GENERAL:                           ##########\n################################################################################',
    'schedule_type': '################################################################################\n##########                         SCHEDULER:                         ##########\n################################################################################',
    'instance_output_mode': '################################################################################\n##########              INSTANCE OUTPUT MODE:                         ##########\n################################################################################',
    'radarr_instances': '################################################################################\n##########                   RADARR INSTANCES:                        ##########\n################################################################################',
    'sonarr_instances': '################################################################################\n##########                   SONARR INSTANCES:                        ##########\n################################################################################',
    'plex_url': '################################################################################\n##########                    PLEX CONFIGURATION:                     ##########\n################################################################################',
    'future_days_upcoming_movies': '################################################################################\n##########                         MOVIES:                            ##########\n################################################################################',
    'future_days_upcoming_shows': '################################################################################\n##########                         TV SHOWS:                          ##########\n################################################################################',
    'trending_movies': '################################################################################\n##########                        TRENDING:                           ##########\n################################################################################',
    'collection_upcoming_movies': '################################################################################\n##########                UPCOMING MOVIES COLLECTION:                 ##########\n################################################################################',
    'backdrop_upcoming_movies_future': '################################################################################\n##########              UPCOMING MOVIES OVERLAY FUTURE:               ##########\n################################################################################',
    'backdrop_upcoming_movies_released': '################################################################################\n##########             UPCOMING MOVIES OVERLAY RELEASED:              ##########\n################################################################################',
    'collection_upcoming_shows': '################################################################################\n##########                UPCOMING SHOWS COLLECTION:                  ##########\n################################################################################',
    'backdrop_upcoming_shows': '################################################################################\n##########               UPCOMING SHOWS OVERLAY FUTURE:               ##########\n################################################################################',
    'backdrop_upcoming_shows_aired': '################################################################################\n##########                UPCOMING SHOWS OVERLAY AIRED:               ##########\n################################################################################',
    'collection_new_show': '################################################################################\n##########                    NEW SHOW COLLECTION:                    ##########\n################################################################################',
    'backdrop_new_show': '################################################################################\n##########                    NEW SHOWS OVERLAY:                      ##########\n################################################################################',
    'collection_trending_movies': '################################################################################\n##########                TRENDING MOVIES COLLECTION:                 ##########\n################################################################################',
    'backdrop_trending_movies_request_needed': '################################################################################\n##########           TRENDING MOVIES OVERLAY REQUEST NEEDED:          ##########\n################################################################################',
    'backdrop_trending_movies_requested': '################################################################################\n##########              TRENDING MOVIES OVERLAY REQUESTED:            ##########\n################################################################################',
    'collection_trending_shows': '################################################################################\n##########                TRENDING SHOWS COLLECTION:                  ##########\n################################################################################',
    'backdrop_trending_shows_request_needed': '################################################################################\n##########           TRENDING SHOWS OVERLAY REQUEST NEEDED:           ##########\n################################################################################',
    'backdrop_trending_shows_requested': '################################################################################\n##########              TRENDING SHOWS OVERLAY REQUESTED:             ##########\n################################################################################',
    'backdrop_trending_top_10_movies': '################################################################################\n##########               TRENDING MOVIES TOP 10 OVERLAY:              ##########\n################################################################################',
    'backdrop_trending_top_10_tv': '################################################################################\n##########              TRENDING SHOWS TOP 10 OVERLAY:                ##########\n################################################################################',
}

# ── Config option metadata ─────────────────────────────────────────────────

CONNECTION_OPTIONS = [
    # WebUI (rendered first; toggle & change-password UI handled with custom JS)
    {"key": "webui_auth_enabled", "type": "bool", "default": True, "label": "Password Protection", "description": "Require a password to access the WebUI.", "section": "WebUI"},
    {"key": "instance_output_mode", "type": "select", "default": "combined", "label": "Instance Output Mode", "description": "Combined: merge all instances into single YML files. Split: separate YML files per instance.", "section": "Instances", "options": [{"value": "combined", "label": "Combined"}, {"value": "split", "label": "Split"}]},
    {"key": "cross_instance_availability", "type": "bool", "default": False, "label": "Cross-Instance Availability", "description": "If enabled, an item already downloaded in ANY instance is treated as available in all instances, so no 'coming soon' placeholder/overlay is created for instances where it's still missing. Only affects multi-instance setups.", "section": "Instances"},
    {"key": "plex_url", "type": "string", "default": "http://localhost:32400", "label": "Plex URL", "description": "URL of your Plex Media Server", "section": "Plex"},
    {"key": "plex_token", "type": "string", "default": "", "label": "Plex Token", "description": "Your Plex authentication token", "section": "Plex", "sensitive": True},
    {"key": "movie_libraries", "type": "string", "default": "Movies", "label": "Movie Libraries", "description": "Comma-separated Plex movie library names", "section": "Plex"},
    {"key": "tv_libraries", "type": "string", "default": "TV Shows", "label": "TV Libraries", "description": "Comma-separated Plex TV library names", "section": "Plex"},
    {"key": "plex_library_scan", "type": "bool", "default": False, "label": "Trigger Library Scan", "description": "After a run, tell Plex to scan the movie/TV libraries so newly written placeholders or trailers are picked up. Enable if your Plex isn't set to auto-scan.", "section": "Plex"},
    # Scheduler
    {"key": "schedule_type", "type": "select", "default": "cron", "label": "Schedule Type", "description": "", "section": "Scheduler", "options": [{"value": "hours", "label": "Every X hours"}, {"value": "cron", "label": "Cron expression"}]},
    {"key": "schedule_hours", "type": "int", "default": 24, "label": "Hours Interval", "description": "Run every X hours", "section": "Scheduler"},
    {"key": "schedule_cron", "type": "string", "default": "0 2 * * *", "label": "Cron Expression", "description": "Standard 5-field cron expression. For help: crontab.guru", "description_html": 'Standard 5-field cron expression. For help: <a href="https://crontab.guru/" target="_blank" rel="noopener">crontab.guru</a>', "section": "Scheduler"},
]

UMTK_OPTIONS = [
    # General
    {"key": "enable_umtk", "type": "bool", "default": True, "label": "Enable UMTK", "description": "Enable Upcoming Movies & TV Shows processing", "section": "General"},
    {"key": "movies", "type": "select", "default": 2, "label": "Movie Method", "description": "Choose how to handle upcoming movies", "options": [{"value": 0, "label": "Disabled"}, {"value": 1, "label": "Download trailers"}, {"value": 2, "label": "Placeholder"}], "section": "General"},
    {"key": "tv", "type": "select", "default": 2, "label": "TV Method", "description": "Choose how to handle upcoming TV shows", "options": [{"value": 0, "label": "Disabled"}, {"value": 1, "label": "Download trailers"}, {"value": 2, "label": "Placeholder"}], "section": "General"},
    {"key": "method_fallback", "type": "bool", "default": True, "label": "Method Fallback", "description": "Try placeholder if trailer download fails", "section": "General"},
    {"key": "preferred_language", "type": "select", "default": "original", "label": "Preferred Language", "description": "Preferred language for trailer downloads (appends language to YouTube search and boosts matching results)", "section": "General", "options": [
        {"value": "original", "label": "Original"},
        {"value": "english", "label": "English"},
        {"value": "german", "label": "German"},
        {"value": "french", "label": "French"},
        {"value": "spanish", "label": "Spanish"},
        {"value": "italian", "label": "Italian"},
        {"value": "japanese", "label": "Japanese"},
        {"value": "korean", "label": "Korean"},
        {"value": "portuguese", "label": "Portuguese"},
        {"value": "russian", "label": "Russian"},
        {"value": "chinese", "label": "Chinese"},
    ]},
    {"key": "utc_offset", "type": "float", "default": 0, "label": "UTC Offset", "description": "Your timezone offset from UTC (e.g. +1, -5)", "section": "General"},
    {"key": "debug", "type": "bool", "default": False, "label": "Debug Mode", "description": "Enable verbose debug logging", "section": "General"},
    {"key": "cleanup", "type": "bool", "default": True, "label": "Cleanup", "description": "Remove outdated trailers/placeholders", "section": "General"},
    {"key": "simplify_next_week_dates", "type": "bool", "default": True, "label": "Simplify Dates", "description": "Use 'today'/'tomorrow'/weekday names for near dates", "section": "General"},
    {"key": "skip_channels", "type": "string_list", "default": [], "label": "Skip Channels", "description": "YouTube channels to skip when searching trailers", "section": "General"},
    # Movies
    {"key": "future_days_upcoming_movies", "type": "int", "default": 30, "label": "Future Days (Movies)", "description": "Days ahead to look for upcoming movies", "section": "Movies"},
    {"key": "past_days_upcoming_movies", "type": "int", "default": 0, "label": "Past Days (Movies)", "description": "Days back to include released movies (0=no limit)", "section": "Movies"},
    {"key": "include_inCinemas", "type": "bool", "default": False, "label": "Include In Cinemas", "description": "Include movies currently in cinemas", "section": "Movies"},
    {"key": "future_only", "type": "bool", "default": False, "label": "Future Only (Movies)", "description": "Only show movies not yet released", "section": "Movies"},
    # TV Shows
    {"key": "future_days_upcoming_shows", "type": "int", "default": 30, "label": "Future Days (Shows)", "description": "Days ahead to look for upcoming shows", "section": "TV Shows"},
    {"key": "recent_days_new_show", "type": "int", "default": 7, "label": "Recent Days (New Show)", "description": "Days back to look for newly premiered shows", "section": "TV Shows"},
    {"key": "future_only_tv", "type": "bool", "default": False, "label": "Future Only (TV)", "description": "Only show TV not yet aired", "section": "TV Shows"},
    # Plex Metadata
    {"key": "append_dates_to_sort_titles", "type": "bool", "default": True, "label": "Append Dates to Sort Titles", "description": "Add release dates to Plex sort titles", "section": "Plex Metadata"},
    {"key": "add_rank_to_sort_title", "type": "bool", "default": True, "label": "Add Rank to Sort Title", "description": "Add trending rank to Plex sort titles", "section": "Plex Metadata"},
    {"key": "edit_S00E00_episode_title", "type": "bool", "default": True, "label": "Edit S00E00 Episode Title", "description": "Update special episode titles in Plex", "section": "Plex Metadata"},
    {"key": "metadata_retry_limit", "type": "int", "default": 4, "label": "Metadata Retry Limit", "description": "Number of API retry attempts for Plex metadata", "section": "Plex Metadata"},
    # Trending
    {"key": "trending_movies", "type": "select", "default": 0, "label": "Trending Movies Method", "description": "Choose how to handle trending movies", "options": [{"value": 0, "label": "Disabled"}, {"value": 1, "label": "Download trailers"}, {"value": 2, "label": "Placeholder"}], "section": "Trending"},
    {"key": "trending_tv", "type": "select", "default": 0, "label": "Trending TV Method", "description": "Choose how to handle trending TV shows", "options": [{"value": 0, "label": "Disabled"}, {"value": 1, "label": "Download trailers"}, {"value": 2, "label": "Placeholder"}], "section": "Trending"},
    {"key": "label_request_needed", "type": "bool", "default": True, "label": "Label Request Needed", "description": "Label trending items not in library as 'Request Needed'", "section": "Trending"},
    {"key": "mdblist_api_key", "type": "string", "default": "", "label": "MDBList API Key", "description": "Your MDBList API key for trending lists", "section": "Trending", "sensitive": True},
    {"key": "mdblist_movies", "type": "string", "default": "", "label": "MDBList Movies URL", "description": "MDBList trending movies list URL", "section": "Trending"},
    {"key": "mdblist_movies_limit", "type": "int", "default": 10, "label": "MDBList Movies Limit", "description": "Number of trending movies to include", "section": "Trending"},
    {"key": "mdblist_tv", "type": "string", "default": "", "label": "MDBList TV URL", "description": "MDBList trending TV list URL", "section": "Trending"},
    {"key": "mdblist_tv_limit", "type": "int", "default": 10, "label": "MDBList TV Limit", "description": "Number of trending TV shows to include", "section": "Trending"},
    {"key": "trending_root_movies", "type": "string", "default": "", "label": "Trending Root Movies", "description": "Root folder for trending movies not in any Radarr library", "section": "Trending"},
    {"key": "trending_root_tv", "type": "string", "default": "", "label": "Trending Root TV", "description": "Root folder for trending shows not in any Sonarr library", "section": "Trending"},
]

TSSK_OPTIONS = [
    {"key": "enable_tssk", "type": "bool", "default": False, "label": "Enable TSSK", "description": "Enable TV Show Status processing", "section": "General", "config_file": "umtk"},
    {"key": "use_tvdb", "type": "bool", "default": False, "label": "Use TVDB", "description": "Use TheTVDB instead of TMDB for Tv Show status", "section": "General"},
    {"key": "skip_unmonitored", "type": "bool", "default": True, "label": "Skip Unmonitored", "description": "Skip unmonitored shows/episodes", "section": "General"},
    {"key": "ignore_finales_tags", "type": "string", "default": "ignorefinales", "label": "Ignore Finales Tags", "description": "Comma-separated Sonarr tags to exclude from finale detection", "section": "General"},
    # Sort title edits
    {"key": "edit_sort_titles", "type": "bool", "default": True, "label": "Edit Sort Titles", "description": "Add air date in front of sort titles for chronological sorting (requires Plex connection).", "section": "Sort Titles"},
    {"key": "edit_sort_titles_new_season_soon", "type": "bool", "default": True, "label": "New Season Soon", "description": "Edit sort titles for shows in the New Season Soon category.", "section": "Sort Titles"},
    {"key": "edit_sort_titles_upcoming_episode", "type": "bool", "default": False, "label": "Upcoming Episode", "description": "Edit sort titles for shows in the Upcoming Episode category.", "section": "Sort Titles"},
    {"key": "edit_sort_titles_upcoming_finale", "type": "bool", "default": False, "label": "Upcoming Finale", "description": "Edit sort titles for shows in the Upcoming Finale category.", "section": "Sort Titles"},
    # Process flags
    {"key": "process_new_shows", "type": "bool", "default": True, "label": "New Shows", "description": "Process recently added new shows", "section": "Process Categories"},
    {"key": "process_new_season_soon", "type": "bool", "default": True, "label": "New Season Soon", "description": "Process shows with upcoming new seasons", "section": "Process Categories"},
    {"key": "process_new_season_started", "type": "bool", "default": True, "label": "New Season Started", "description": "Process shows with recently started seasons", "section": "Process Categories"},
    {"key": "process_upcoming_episode", "type": "bool", "default": True, "label": "Upcoming Episode", "description": "Process upcoming regular episodes", "section": "Process Categories"},
    {"key": "process_upcoming_finale", "type": "bool", "default": True, "label": "Upcoming Finale", "description": "Process upcoming season finales", "section": "Process Categories"},
    {"key": "process_season_finale", "type": "bool", "default": True, "label": "Season Finale", "description": "Process recently aired season finales", "section": "Process Categories"},
    {"key": "process_final_episode", "type": "bool", "default": True, "label": "Final Episode", "description": "Process recently aired final episodes", "section": "Process Categories"},
    {"key": "process_returning_shows", "type": "bool", "default": True, "label": "Returning Shows", "description": "Process returning (continuing) shows", "section": "Process Categories"},
    {"key": "process_ended_shows", "type": "bool", "default": True, "label": "Ended Shows", "description": "Process ended shows", "section": "Process Categories"},
    {"key": "process_canceled_shows", "type": "bool", "default": True, "label": "Canceled Shows", "description": "Process canceled shows", "section": "Process Categories"},
    # Timeframes
    {"key": "recent_days_new_show", "type": "int", "default": 7, "label": "Recent Days (New Show)", "description": "Days to look back for new shows", "section": "Timeframes"},
    {"key": "future_days_new_season", "type": "int", "default": 31, "label": "Future Days (New Season)", "description": "Days ahead for upcoming new seasons", "section": "Timeframes"},
    {"key": "recent_days_new_season_started", "type": "int", "default": 7, "label": "Recent Days (Season Started)", "description": "Days to look back for started seasons", "section": "Timeframes"},
    {"key": "future_days_upcoming_episode", "type": "int", "default": 31, "label": "Future Days (Episode)", "description": "Days ahead for upcoming episodes", "section": "Timeframes"},
    {"key": "future_days_upcoming_finale", "type": "int", "default": 31, "label": "Future Days (Finale)", "description": "Days ahead for upcoming finales", "section": "Timeframes"},
    {"key": "recent_days_season_finale", "type": "int", "default": 7, "label": "Recent Days (Season Finale)", "description": "Days to look back for season finales", "section": "Timeframes"},
    {"key": "recent_days_final_episode", "type": "int", "default": 7, "label": "Recent Days (Final Episode)", "description": "Days to look back for final episodes", "section": "Timeframes"},
]


# ── Allowed-key whitelists (derived from option metadata above) ───────────
_ALLOWED_CONNECTION_KEYS = {o["key"] for o in CONNECTION_OPTIONS}
_ALLOWED_CONNECTION_KEYS.update({'radarr_instances', 'sonarr_instances'})
_ALLOWED_UMTK_KEYS = {o["key"] for o in UMTK_OPTIONS}
_ALLOWED_TSSK_KEYS = {o["key"] for o in TSSK_OPTIONS}
_ALLOWED_BLOCK_PREFIXES = ('collection_', 'backdrop_', 'text_')

# ── Helper functions ───────────────────────────────────────────────────────

def _load_yaml(path):
    """Load a YAML file and return the dict (or empty dict)."""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
            return data if data else {}
    except FileNotFoundError:
        return {}
    except Exception:
        return {}


def _save_yaml(path, data):
    """Save dict to YAML file atomically, re-inserting section headers."""
    tmp_path = path + '.tmp'
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(tmp_path, 'w', encoding='utf-8') as f:
            # Determine which headers to use based on file
            headers = UMTK_SECTION_HEADERS if 'tssk' not in os.path.basename(path).lower() else {}

            for key, value in data.items():
                if key in headers:
                    f.write(headers[key] + '\n')
                yaml.dump({key: value}, f, Dumper=_QuotedDumper, default_flow_style=False, allow_unicode=True, sort_keys=False)
                f.write('\n')

        os.replace(tmp_path, path)
    except Exception as e:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise e


def _safe_error(e):
    """Return a sanitized error message suitable for API responses."""
    msg = str(e)
    if any(kw in msg.lower() for kw in ('traceback', 'errno', '/app/', '/usr/', '\\users\\')):
        return "An internal error occurred"
    return msg[:200]


def _get_config_value(config, key, default=None):
    """Get a value from config with type coercion."""
    val = config.get(key)
    if val is None:
        return default
    return val


def _is_url_safe(url):
    """Validate that a URL is safe to request (SSRF protection).

    Allows private-network IPs (needed for local Plex/Radarr/Sonarr) but
    blocks link-local (169.254.x.x / cloud metadata), loopback IPv6 tricks,
    and non-HTTP schemes.  Returns (safe: bool, reason: str).
    """
    try:
        parsed = urlparse(url)
    except Exception:
        return False, "Invalid URL"

    if parsed.scheme not in ("http", "https"):
        return False, "Only http/https URLs are allowed"

    hostname = parsed.hostname
    if not hostname:
        return False, "No hostname in URL"

    # Resolve hostname to IP(s) to catch DNS rebinding to dangerous addresses
    try:
        infos = socket.getaddrinfo(hostname, parsed.port or 80,
                                   proto=socket.IPPROTO_TCP)
        addrs = {info[4][0] for info in infos}
    except socket.gaierror:
        # Can't resolve — let the actual request fail with a clear error
        return True, ""

    for addr_str in addrs:
        try:
            addr = ipaddress.ip_address(addr_str)
        except ValueError:
            continue
        # Block link-local (169.254.0.0/16, fe80::/10) — covers cloud metadata
        if addr.is_link_local:
            return False, "Link-local addresses are not allowed"
        # Block IPv6-mapped IPv4 link-local (::ffff:169.254.x.x)
        if hasattr(addr, 'ipv4_mapped') and addr.ipv4_mapped and addr.ipv4_mapped.is_link_local:
            return False, "Link-local addresses are not allowed"

    return True, ""


def _test_connection(url, api_key=None, token=None, timeout=10):
    """Test a connection to a service. Returns (success, message, response_time_ms)."""
    # SSRF guard — validate URL before making any request
    safe, reason = _is_url_safe(url)
    if not safe:
        return False, reason, 0

    try:
        start = time.time()
        headers = {}
        if api_key:
            # Radarr/Sonarr - try /api/v3/health
            test_url = url.rstrip('/') + '/api/v3/health'
            headers['X-Api-Key'] = api_key
        elif token:
            # Plex - try identity endpoint
            test_url = url.rstrip('/') + '/identity'
            headers['X-Plex-Token'] = token
        else:
            return False, "No credentials provided", 0

        resp = requests.get(test_url, headers=headers, timeout=timeout)
        elapsed = int((time.time() - start) * 1000)

        if resp.status_code == 200:
            return True, f"Connected ({elapsed}ms)", elapsed
        else:
            return False, f"HTTP {resp.status_code}", elapsed
    except requests.exceptions.ConnectionError:
        return False, "Connection refused", 0
    except requests.exceptions.Timeout:
        return False, "Connection timed out", 0
    except Exception as e:
        return False, _safe_error(e), 0


def _resolve_arr_api_url(base_url, api_key, service='radarr'):
    """Resolve the working API v3 URL for a *arr service."""
    safe, reason = _is_url_safe(base_url)
    if not safe:
        return None
    base = base_url.rstrip('/')

    # Tolerate a pasted .../api/v3 suffix so we don't probe /api/v3/api/v3
    if base.endswith('/api/v3'):
        base = base[:-len('/api/v3')]

    # Host = base stripped to scheme+host, used for fallback guesses
    host = base
    if base.startswith('http'):
        protocol_end = base.find('://') + 3
        next_slash = base.find('/', protocol_end)
        if next_slash != -1:
            host = base[:next_slash]

    # Try the full configured URL first (preserves reverse-proxy subpaths like
    # /radarr2), then fall back to host-stripped guesses. De-duplicate so a bare
    # host doesn't get probed twice.
    candidates = []
    for url in (f"{base}/api/v3", f"{host}/api/v3", f"{host}/{service}/api/v3"):
        if url not in candidates:
            candidates.append(url)

    for test_url in candidates:
        try:
            resp = requests.get(f"{test_url}/health",
                                headers={"X-Api-Key": api_key}, timeout=5)
            if resp.status_code == 200:
                return test_url
        except Exception:
            continue
    return None


# ── yt-dlp version info ────────────────────────────────────────────────────
_ytdlp_info_cache = {"data": None, "timestamp": 0}
_YTDLP_CACHE_TTL = 300  # 5 minutes


def _get_ytdlp_info():
    """Get yt-dlp version info and check for updates. Cached for 5 minutes."""
    now = time.time()
    if _ytdlp_info_cache["data"] and (now - _ytdlp_info_cache["timestamp"]) < _YTDLP_CACHE_TTL:
        return _ytdlp_info_cache["data"]

    installed_version = None
    try:
        result = subprocess.run(
            ["yt-dlp", "--version"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            installed_version = result.stdout.strip()
    except Exception:
        pass

    if not installed_version:
        info = {
            "name": "yt-dlp", "service": "ytdlp", "online": False,
            "message": "Not installed", "responseTime": 0,
            "version": None, "latestVersion": None, "updateAvailable": False,
        }
        _ytdlp_info_cache["data"] = info
        _ytdlp_info_cache["timestamp"] = now
        return info

    latest_version = None
    update_available = False
    try:
        resp = requests.get(
            "https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest",
            timeout=5
        )
        resp.raise_for_status()
        latest_version = resp.json().get("tag_name", "").lstrip("v")
        if latest_version and installed_version:
            try:
                installed_parts = tuple(int(x) for x in installed_version.split('.'))
                latest_parts = tuple(int(x) for x in latest_version.split('.'))
                update_available = latest_parts > installed_parts
            except Exception:
                update_available = latest_version != installed_version
    except Exception:
        pass

    info = {
        "name": "yt-dlp", "service": "ytdlp", "online": True,
        "message": f"v{installed_version}", "responseTime": 0,
        "version": installed_version, "latestVersion": latest_version,
        "updateAvailable": update_available,
    }
    _ytdlp_info_cache["data"] = info
    _ytdlp_info_cache["timestamp"] = now
    return info


# ── Route registration ─────────────────────────────────────────────────────

def register_routes(app):
    """Register all Flask routes."""

    @app.route("/")
    def index():
        return render_template("index.html", version=VERSION)

    # ── Status ─────────────────────────────────────────────────────────
    @app.route("/api/status")
    def api_status():
        if webui._scheduler_state:
            return jsonify(webui._scheduler_state.get_status_dict())
        return jsonify({"status": "unknown", "has_cron": False})

    @app.route("/api/scheduler/run-now", methods=["POST"])
    def api_run_now():
        if webui._scheduler_state:
            webui._scheduler_state.request_run()
            return jsonify({"ok": True})
        return jsonify({"ok": False, "error": "No scheduler"}), 400

    @app.route("/api/scheduler/stop", methods=["POST"])
    def api_stop():
        if webui._scheduler_state:
            webui._scheduler_state.request_stop()
            return jsonify({"ok": True})
        return jsonify({"ok": False, "error": "No scheduler"}), 400

    @app.route("/api/scheduler/start", methods=["POST"])
    def api_start():
        if webui._scheduler_state:
            webui._scheduler_state.request_resume()
            return jsonify({"ok": True})
        return jsonify({"ok": False, "error": "No scheduler"}), 400

    # ── Version ────────────────────────────────────────────────────────
    @app.route("/api/update")
    def api_update():
        return jsonify(get_update_status())

    # ── Config: Connections ────────────────────────────────────────────
    @app.route("/api/config/connections")
    def api_config_connections():
        config = _load_yaml(webui._config_path)
        result = []
        for opt in CONNECTION_OPTIONS:
            val = _get_config_value(config, opt["key"], opt["default"])
            if opt.get("sensitive") and val:
                val = MASKED_VALUE
            result.append({**opt, "value": val})
        return jsonify(result)

    @app.route("/api/config/connections", methods=["POST"])
    def api_save_connections():
        config = _load_yaml(webui._config_path)
        data = request.get_json()
        sensitive_keys = {o["key"] for o in CONNECTION_OPTIONS if o.get("sensitive")}
        for key, value in data.items():
            if key not in _ALLOWED_CONNECTION_KEYS:
                continue
            # webui_auth_enabled is managed via /api/auth/set-enabled (which
            # requires password confirmation); ignore any value sent here.
            if key == "webui_auth_enabled":
                continue
            # Don't overwrite real credentials with the mask placeholder
            if key in sensitive_keys and value == MASKED_VALUE:
                continue
            # Coerce schedule_hours to int (UI may send a string)
            if key == "schedule_hours":
                try:
                    value = int(value)
                except (TypeError, ValueError):
                    return jsonify({"ok": False, "error": "Hours Interval must be a whole number"}), 400
                if value < 1:
                    return jsonify({"ok": False, "error": "Hours Interval must be >= 1"}), 400
            config[key] = value

        # Validate the schedule before persisting so an invalid cron expression
        # never reaches disk.
        sched_type = (config.get("schedule_type") or "cron").strip().lower()
        sched_hours = config.get("schedule_hours", 24) or 24
        sched_cron = (config.get("schedule_cron") or "").strip()
        if sched_type == "cron":
            try:
                from croniter import croniter
                if not sched_cron or not croniter.is_valid(sched_cron):
                    return jsonify({"ok": False, "error": f"Invalid cron expression: {sched_cron or '(empty)'}"}), 400
            except ImportError:
                return jsonify({"ok": False, "error": "croniter package not installed"}), 400

        _save_yaml(webui._config_path, config)

        # Push the new schedule into the live scheduler so the next run is
        # recomputed without a container restart.
        if webui._scheduler_state is not None:
            ok, err = webui._scheduler_state.update_schedule(sched_type, int(sched_hours), sched_cron)
            if not ok:
                return jsonify({"ok": False, "error": err}), 400

        return jsonify({"ok": True})

    # ── Config: UMTK ──────────────────────────────────────────────────
    @app.route("/api/config/umtk")
    def api_config_umtk():
        config = _load_yaml(webui._config_path)
        ensure_trending_requested_blocks(config)
        result = {"options": [], "blocks": {}}
        for opt in UMTK_OPTIONS:
            val = _get_config_value(config, opt["key"], opt["default"])
            if opt.get("sensitive") and val:
                val = MASKED_VALUE
            result["options"].append({**opt, "value": val})
        # Include collection/overlay blocks as raw dicts
        for key, value in config.items():
            if any(key.startswith(p) for p in ['collection_', 'backdrop_', 'text_']):
                result["blocks"][key] = value if isinstance(value, dict) else {}
        return jsonify(result)

    @app.route("/api/config/umtk", methods=["POST"])
    def api_save_umtk():
        config = _load_yaml(webui._config_path)
        data = request.get_json()
        options = data.get("options", {})
        blocks = data.get("blocks", {})
        sensitive_keys = {o["key"] for o in UMTK_OPTIONS if o.get("sensitive")}
        for key, value in options.items():
            if key not in _ALLOWED_UMTK_KEYS:
                continue
            if key in sensitive_keys and value == MASKED_VALUE:
                continue
            config[key] = value
        for key, value in blocks.items():
            if not any(key.startswith(p) for p in _ALLOWED_BLOCK_PREFIXES):
                continue
            if not isinstance(value, dict):
                continue
            config[key] = value
        _save_yaml(webui._config_path, config)
        return jsonify({"ok": True})

    # ── Config: TSSK ──────────────────────────────────────────────────
    @app.route("/api/config/tssk")
    def api_config_tssk():
        umtk_config = _load_yaml(webui._config_path)
        tssk_config = _load_yaml(webui._tssk_config_path)
        result = {"options": [], "blocks": {}}
        for opt in TSSK_OPTIONS:
            if opt.get("config_file") == "umtk":
                val = _get_config_value(umtk_config, opt["key"], opt["default"])
            else:
                val = _get_config_value(tssk_config, opt["key"], opt["default"])
            result["options"].append({**opt, "value": val})
        # Include collection/overlay blocks from TSSK config
        for key, value in tssk_config.items():
            if any(key.startswith(p) for p in ['collection_', 'backdrop_', 'text_']):
                result["blocks"][key] = value if isinstance(value, dict) else {}
        return jsonify(result)

    @app.route("/api/config/tssk", methods=["POST"])
    def api_save_tssk():
        umtk_config = _load_yaml(webui._config_path)
        tssk_config = _load_yaml(webui._tssk_config_path)
        data = request.get_json()
        options = data.get("options", {})
        blocks = data.get("blocks", {})
        for key, value in options.items():
            if key not in _ALLOWED_TSSK_KEYS:
                continue
            # Check if this option should go to UMTK config
            opt_meta = next((o for o in TSSK_OPTIONS if o["key"] == key), None)
            if opt_meta and opt_meta.get("config_file") == "umtk":
                umtk_config[key] = value
            else:
                tssk_config[key] = value
        for key, value in blocks.items():
            if not any(key.startswith(p) for p in _ALLOWED_BLOCK_PREFIXES):
                continue
            if not isinstance(value, dict):
                continue
            tssk_config[key] = value
        _save_yaml(webui._config_path, umtk_config)
        _save_yaml(webui._tssk_config_path, tssk_config)
        return jsonify({"ok": True})

    # ── Config: Instances ─────────────────────────────────────────────
    @app.route("/api/config/legacy_roots")
    def api_config_legacy_roots():
        """Report whether the user's config still uses the pre-per-instance
        global umtk_root_movies / umtk_root_tv keys. The WebUI uses this to
        show a one-time migration banner."""
        config = _load_yaml(webui._config_path) or {}
        return jsonify({
            "has_legacy_root_keys": bool(config.get('umtk_root_movies') or config.get('umtk_root_tv')),
            "legacy_root_movies": config.get('umtk_root_movies') or '',
            "legacy_root_tv": config.get('umtk_root_tv') or '',
        })

    @app.route("/api/config/instances")
    def api_config_instances():
        config = _load_yaml(webui._config_path)
        # Apply normalization to handle legacy flat format
        from umtk.config_loader import normalize_instances
        config = normalize_instances(config)
        # Mask API keys
        for inst_list in [config.get('radarr_instances', []), config.get('sonarr_instances', [])]:
            for inst in inst_list:
                if inst.get('api_key'):
                    inst['api_key'] = MASKED_VALUE
        return jsonify({
            "radarr_instances": config.get('radarr_instances', []),
            "sonarr_instances": config.get('sonarr_instances', []),
        })

    @app.route("/api/config/instances", methods=["POST"])
    def api_save_instances():
        config = _load_yaml(webui._config_path)
        data = request.get_json() or {}

        # Read existing instances to preserve masked API keys
        from umtk.config_loader import normalize_instances
        existing = normalize_instances(dict(config))

        for inst_type in ['radarr_instances', 'sonarr_instances']:
            new_instances = data.get(inst_type, [])
            old_instances = existing.get(inst_type, [])
            old_by_name = {inst.get('name', ''): inst for inst in old_instances}

            # Validate
            names_seen = set()
            for inst in new_instances:
                name = (inst.get('name') or '').strip()
                if not name:
                    return jsonify({"ok": False, "error": f"All {inst_type.replace('_', ' ')} must have a name"}), 400
                if name in names_seen:
                    return jsonify({"ok": False, "error": f"Duplicate instance name: {name}"}), 400
                names_seen.add(name)
                if not inst.get('url', '').strip():
                    return jsonify({"ok": False, "error": f"Instance '{name}' is missing a URL"}), 400
                # Resolve masked API keys
                if inst.get('api_key') == MASKED_VALUE:
                    old = old_by_name.get(name, {})
                    inst['api_key'] = old.get('api_key', '')
                # Coerce timeout
                try:
                    inst['timeout'] = int(inst.get('timeout', 90))
                except (TypeError, ValueError):
                    inst['timeout'] = 90

            config[inst_type] = new_instances

        # Remove legacy flat keys if present (migrated to instances)
        for old_key in ['radarr_url', 'radarr_api_key', 'radarr_timeout',
                        'sonarr_url', 'sonarr_api_key', 'sonarr_timeout',
                        'exclude_radarr_tags', 'exclude_sonarr_tags']:
            config.pop(old_key, None)

        _save_yaml(webui._config_path, config)
        return jsonify({"ok": True})

    # ── Connection tests ──────────────────────────────────────────────
    def _resolve_masked(data, key):
        """If the value is the mask placeholder, return the real value from config."""
        val = data.get(key, "")
        if val == MASKED_VALUE:
            config = _load_yaml(webui._config_path)
            return config.get(key, "")
        return val

    @app.route("/api/test/instance", methods=["POST"])
    def api_test_instance():
        """Test a specific Radarr/Sonarr instance connection."""
        data = request.get_json() or {}
        url = (data.get("url") or "").strip()
        api_key = (data.get("api_key") or "").strip()
        inst_name = data.get("name", "")

        if not url or not api_key:
            return jsonify({"success": False, "message": "URL and API key required"})

        # If API key is masked, look it up from saved config
        if api_key == MASKED_VALUE and inst_name:
            config = _load_yaml(webui._config_path)
            from umtk.config_loader import normalize_instances
            config = normalize_instances(config)
            for inst_list in [config.get('radarr_instances', []), config.get('sonarr_instances', [])]:
                for inst in inst_list:
                    if inst.get('name') == inst_name:
                        api_key = inst.get('api_key', '')
                        break

        ok, msg, ms = _test_connection(url, api_key=api_key)
        return jsonify({"success": ok, "message": msg, "response_time": ms})

    @app.route("/api/test/plex", methods=["POST"])
    def api_test_plex():
        data = request.get_json() or {}
        url = data.get("plex_url", "")
        token = _resolve_masked(data, "plex_token")
        if not url or not token:
            return jsonify({"success": False, "message": "URL and token required"})
        ok, msg, ms = _test_connection(url, token=token)
        return jsonify({"success": ok, "message": msg, "response_time": ms})

    @app.route("/api/test/radarr", methods=["POST"])
    def api_test_radarr():
        data = request.get_json() or {}
        url = data.get("radarr_url", "")
        key = _resolve_masked(data, "radarr_api_key")
        if not url or not key:
            return jsonify({"success": False, "message": "URL and API key required"})
        ok, msg, ms = _test_connection(url, api_key=key)
        return jsonify({"success": ok, "message": msg, "response_time": ms})

    @app.route("/api/test/sonarr", methods=["POST"])
    def api_test_sonarr():
        data = request.get_json() or {}
        url = data.get("sonarr_url", "")
        key = _resolve_masked(data, "sonarr_api_key")
        if not url or not key:
            return jsonify({"success": False, "message": "URL and API key required"})
        ok, msg, ms = _test_connection(url, api_key=key)
        return jsonify({"success": ok, "message": msg, "response_time": ms})

    @app.route("/api/test/mdblist", methods=["POST"])
    def api_test_mdblist():
        data = request.get_json() or {}
        api_key = _resolve_masked(data, "mdblist_api_key").strip()
        movies_url = data.get("mdblist_movies", "").strip()
        tv_url = data.get("mdblist_tv", "").strip()

        if not api_key:
            return jsonify({"success": False, "message": "API key required"})

        try:
            start = time.time()
            resp = requests.get(
                "https://api.mdblist.com/user",
                params={"apikey": api_key},
                timeout=10
            )
            elapsed = int((time.time() - start) * 1000)

            if resp.status_code == 401:
                return jsonify({"success": False, "message": "Invalid API key"})
            elif resp.status_code != 200:
                return jsonify({"success": False, "message": f"API returned HTTP {resp.status_code}"})

            messages = [f"API key valid ({elapsed}ms)"]

            for label, url in [("Movies list", movies_url), ("TV list", tv_url)]:
                if not url:
                    continue
                parts = url.rstrip('/').split('/')
                if len(parts) < 2:
                    messages.append(f"{label}: invalid URL format")
                    continue
                list_id = parts[-1]
                username = parts[-2]
                try:
                    r = requests.get(
                        f"https://api.mdblist.com/lists/{username}/{list_id}/items",
                        params={"apikey": api_key, "limit": 1},
                        timeout=10
                    )
                    if r.status_code == 200:
                        messages.append(f"{label} OK")
                    else:
                        messages.append(f"{label}: HTTP {r.status_code}")
                except Exception:
                    messages.append(f"{label}: connection failed")

            return jsonify({"success": True, "message": " | ".join(messages)})

        except requests.exceptions.ConnectionError:
            return jsonify({"success": False, "message": "Connection refused"})
        except requests.exceptions.Timeout:
            return jsonify({"success": False, "message": "Connection timed out"})
        except Exception as e:
            return jsonify({"success": False, "message": _safe_error(e)})

    # ── Dashboard: upcoming content ──────────────────────────────────
    @app.route("/api/dashboard/upcoming")
    def api_dashboard_upcoming():
        from umtk.config_loader import normalize_instances
        config = normalize_instances(_load_yaml(webui._config_path))
        items = []
        seen_tv = set()
        seen_movies = set()
        now = datetime.now()
        start = now.strftime('%Y-%m-%d')
        end_date = now + timedelta(days=30)
        end = end_date.strftime('%Y-%m-%d')
        include_in_cinemas = str(config.get('include_inCinemas', 'false')).lower() == 'true'

        # ── Sonarr calendar (all instances) ──
        for instance in config.get('sonarr_instances', []):
            sonarr_url = instance.get('url', '')
            sonarr_key = instance.get('api_key', '')
            if not sonarr_url or not sonarr_key:
                continue
            try:
                api_url = _resolve_arr_api_url(sonarr_url, sonarr_key, 'sonarr')
                if api_url:
                    resp = requests.get(
                        f"{api_url}/calendar",
                        params={'start': start, 'end': end, 'includeSeries': 'true'},
                        headers={"X-Api-Key": sonarr_key},
                        timeout=15
                    )
                    if resp.status_code == 200:
                        episodes = resp.json()
                        series_map = {}
                        for ep in episodes:
                            if ep.get('hasFile', False):
                                continue
                            series = ep.get('series', {})
                            tvdb_id = series.get('tvdbId')
                            sid = series.get('id')
                            if not sid:
                                continue
                            if tvdb_id and tvdb_id in seen_tv:
                                continue

                            sn = ep.get('seasonNumber', 0)
                            en = ep.get('episodeNumber', 0)
                            ft = ep.get('finaleType')

                            if sn == 1 and en == 1:
                                priority, label = 4, 'Show Premiere'
                            elif en == 1:
                                priority, label = 3, f'Season {sn} Premiere'
                            elif ft in ('season', 'series'):
                                priority, label = 2, f'Season {sn} Finale'
                            else:
                                priority, label = 1, 'Next Episode'

                            air_utc = ep.get('airDateUtc', '')
                            if air_utc:
                                air = datetime.fromisoformat(air_utc.replace('Z', '+00:00')).astimezone().strftime('%Y-%m-%d')
                            else:
                                air = ep.get('airDate', '')
                            if sid not in series_map or air < series_map[sid]['_air']:
                                poster = ''
                                for img in series.get('images', []):
                                    if img.get('coverType') == 'poster':
                                        poster = img.get('remoteUrl') or ''
                                        break
                                series_map[sid] = {
                                    'type': 'tv',
                                    'title': series.get('title', ''),
                                    'date': air,
                                    'label': label,
                                    'posterUrl': poster,
                                    '_air': air,
                                    '_tvdb': tvdb_id
                                }

                        for entry in series_map.values():
                            if entry.get('_tvdb'):
                                seen_tv.add(entry['_tvdb'])
                            del entry['_air']
                            entry.pop('_tvdb', None)
                            items.append(entry)
            except Exception:
                pass

        # ── Radarr movies (all instances) ──
        for instance in config.get('radarr_instances', []):
            radarr_url = instance.get('url', '')
            radarr_key = instance.get('api_key', '')
            if not radarr_url or not radarr_key:
                continue
            try:
                api_url = _resolve_arr_api_url(radarr_url, radarr_key, 'radarr')
                if api_url:
                    resp = requests.get(
                        f"{api_url}/movie",
                        headers={"X-Api-Key": radarr_key},
                        timeout=15
                    )
                    if resp.status_code == 200:
                        movies = resp.json()
                        for movie in movies:
                            if not movie.get('monitored', False) or movie.get('hasFile', False):
                                continue

                            tmdb_id = movie.get('tmdbId')
                            if tmdb_id and tmdb_id in seen_movies:
                                continue

                            release_date = None
                            if include_in_cinemas:
                                dates = [d[:10] for d in [
                                    movie.get('digitalRelease'),
                                    movie.get('physicalRelease'),
                                    movie.get('inCinemas')
                                ] if d]
                                if dates:
                                    dates.sort()
                                    release_date = dates[0]
                            else:
                                dr = movie.get('digitalRelease')
                                pr = movie.get('physicalRelease')
                                if dr:
                                    release_date = dr[:10]
                                elif pr:
                                    release_date = pr[:10]

                            if not release_date:
                                continue

                            try:
                                rd = datetime.strptime(release_date, '%Y-%m-%d')
                                if rd.date() < now.date() or rd > end_date:
                                    continue
                            except ValueError:
                                continue

                            if tmdb_id:
                                seen_movies.add(tmdb_id)

                            poster = ''
                            for img in movie.get('images', []):
                                if img.get('coverType') == 'poster':
                                    poster = img.get('remoteUrl') or ''
                                    break

                            items.append({
                                'type': 'movie',
                                'title': movie.get('title', ''),
                                'date': release_date,
                                'label': 'Expected',
                                'posterUrl': poster
                            })
            except Exception:
                pass

        items.sort(key=lambda x: x.get('date', ''))
        return jsonify({"items": items, "today": now.strftime('%Y-%m-%d')})

    # ── Dashboard: service status ────────────────────────────────────
    @app.route("/api/dashboard/services")
    def api_dashboard_services():
        from umtk.config_loader import normalize_instances
        config = normalize_instances(_load_yaml(webui._config_path))
        services = []

        plex_url = config.get('plex_url', '')
        plex_token = config.get('plex_token', '')
        if plex_url and plex_token:
            ok, msg, ms = _test_connection(plex_url, token=plex_token, timeout=5)
            services.append({'name': 'Plex', 'online': ok, 'message': msg, 'responseTime': ms})
        else:
            services.append({'name': 'Plex', 'online': False, 'message': 'Not configured', 'responseTime': 0})

        radarr_instances = config.get('radarr_instances', [])
        if radarr_instances:
            for instance in radarr_instances:
                inst_url = instance.get('url', '')
                inst_key = instance.get('api_key', '')
                inst_name = instance.get('name', 'Radarr')
                if inst_url and inst_key:
                    ok, msg, ms = _test_connection(inst_url, api_key=inst_key, timeout=5)
                    services.append({'name': inst_name, 'online': ok, 'message': msg, 'responseTime': ms})
                else:
                    services.append({'name': inst_name, 'online': False, 'message': 'Not configured', 'responseTime': 0})
        else:
            services.append({'name': 'Radarr', 'online': False, 'message': 'Not configured', 'responseTime': 0})

        sonarr_instances = config.get('sonarr_instances', [])
        if sonarr_instances:
            for instance in sonarr_instances:
                inst_url = instance.get('url', '')
                inst_key = instance.get('api_key', '')
                inst_name = instance.get('name', 'Sonarr')
                if inst_url and inst_key:
                    ok, msg, ms = _test_connection(inst_url, api_key=inst_key, timeout=5)
                    services.append({'name': inst_name, 'online': ok, 'message': msg, 'responseTime': ms})
                else:
                    services.append({'name': inst_name, 'online': False, 'message': 'Not configured', 'responseTime': 0})
        else:
            services.append({'name': 'Sonarr', 'online': False, 'message': 'Not configured', 'responseTime': 0})

        services.append(_get_ytdlp_info())

        return jsonify(services)

    # ── yt-dlp update ──────────────────────────────────────────────────
    @app.route("/api/ytdlp/update", methods=["POST"])
    def api_ytdlp_update():
        """Update yt-dlp via pip."""
        try:
            import glob as _glob
            site_pkg = os.path.join(os.path.dirname(os.__file__), 'site-packages')
            for bad in _glob.glob(os.path.join(site_pkg, '~t-dlp*')):
                import shutil
                shutil.rmtree(bad, ignore_errors=True)

            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", "--upgrade", "yt-dlp[default]"],
                capture_output=True, text=True, timeout=120
            )
            if result.returncode == 0:
                _ytdlp_info_cache["timestamp"] = 0
                ver_result = subprocess.run(
                    ["yt-dlp", "--version"],
                    capture_output=True, text=True, timeout=5
                )
                new_version = ver_result.stdout.strip() if ver_result.returncode == 0 else "unknown"
                return jsonify({"ok": True, "version": new_version})
            else:
                return jsonify({"ok": False, "error": (result.stderr or "pip upgrade failed")[-200:]})
        except subprocess.TimeoutExpired:
            return jsonify({"ok": False, "error": "Update timed out (120s)"})
        except Exception as e:
            return jsonify({"ok": False, "error": _safe_error(e)})

    # ── Log ────────────────────────────────────────────────────────────
    @app.route("/api/log")
    def api_log():
        """Return the last N lines from the log file, filtering out HTTP request noise."""
        import re
        limit = min(request.args.get("limit", 500, type=int), 5000)
        project_root = os.path.dirname(os.path.dirname(__file__))
        log_paths = [
            os.path.join(project_root, "logs", "umtk.log"),
            os.path.join("logs", "umtk.log"),
            os.path.join("/app", "logs", "umtk.log"),
        ]
        # Pattern to match werkzeug HTTP access log lines
        _http_log_re = re.compile(r'^\d+\.\d+\.\d+\.\d+\s+-\s+-\s+\[.*?\]\s+"(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)\s+/api/')
        for log_path in log_paths:
            if os.path.exists(log_path):
                try:
                    with open(log_path, 'r', encoding='utf-8', errors='replace') as f:
                        lines = f.readlines()
                    filtered = [l for l in lines if not _http_log_re.match(l)]
                    return jsonify({"lines": filtered[-limit:]})
                except Exception:
                    pass
        return jsonify({"lines": []})
