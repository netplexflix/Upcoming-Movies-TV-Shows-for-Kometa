"""Flask routes and config metadata for UMTK Web UI."""

import os
import yaml
import requests
from datetime import datetime, timedelta
from flask import render_template, jsonify, request

import webui
from umtk.constants import VERSION
from umtk.updater import get_update_status


class _QuotedDumper(yaml.SafeDumper):
    """YAML dumper that always quotes string values."""
    pass


def _quoted_str(dumper, data):
    return dumper.represent_scalar('tag:yaml.org,2002:str', data, style="'")


_QuotedDumper.add_representer(str, _quoted_str)


# ── Section header comments for config files ───────────────────────────────
# These are re-inserted when saving to preserve the visual structure.

UMTK_SECTION_HEADERS = {
    'enable_umtk': '################################################################################\n##########                         GENERAL:                           ##########\n################################################################################',
    'radarr_url': '################################################################################\n##########                   RADARR CONFIGURATION:                    ##########\n################################################################################',
    'sonarr_url': '################################################################################\n##########                   SONARR CONFIGURATION:                    ##########\n################################################################################',
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
    'collection_trending_shows': '################################################################################\n##########                TRENDING SHOWS COLLECTION:                  ##########\n################################################################################',
    'backdrop_trending_shows_request_needed': '################################################################################\n##########           TRENDING SHOWS OVERLAY REQUEST NEEDED:           ##########\n################################################################################',
    'backdrop_trending_top_10_movies': '################################################################################\n##########               TRENDING MOVIES TOP 10 OVERLAY:              ##########\n################################################################################',
    'backdrop_trending_top_10_tv': '################################################################################\n##########              TRENDING SHOWS TOP 10 OVERLAY:                ##########\n################################################################################',
}

# ── Config option metadata ─────────────────────────────────────────────────

CONNECTION_OPTIONS = [
    {"key": "sonarr_url", "type": "string", "default": "http://localhost:8989", "label": "Sonarr URL", "description": "URL of your Sonarr instance", "section": "Sonarr"},
    {"key": "sonarr_api_key", "type": "string", "default": "", "label": "Sonarr API Key", "description": "Your Sonarr API key", "section": "Sonarr", "sensitive": True},
    {"key": "sonarr_timeout", "type": "int", "default": 90, "label": "Sonarr Timeout", "description": "Connection timeout in seconds", "section": "Sonarr"},
    {"key": "radarr_url", "type": "string", "default": "http://localhost:7878", "label": "Radarr URL", "description": "URL of your Radarr instance", "section": "Radarr"},
    {"key": "radarr_api_key", "type": "string", "default": "", "label": "Radarr API Key", "description": "Your Radarr API key", "section": "Radarr", "sensitive": True},
    {"key": "radarr_timeout", "type": "int", "default": 90, "label": "Radarr Timeout", "description": "Connection timeout in seconds", "section": "Radarr"},
    {"key": "plex_url", "type": "string", "default": "http://localhost:32400", "label": "Plex URL", "description": "URL of your Plex Media Server", "section": "Plex"},
    {"key": "plex_token", "type": "string", "default": "", "label": "Plex Token", "description": "Your Plex authentication token", "section": "Plex", "sensitive": True},
    {"key": "movie_libraries", "type": "string", "default": "Movies", "label": "Movie Libraries", "description": "Comma-separated Plex movie library names", "section": "Plex"},
    {"key": "tv_libraries", "type": "string", "default": "TV Shows", "label": "TV Libraries", "description": "Comma-separated Plex TV library names", "section": "Plex"},
]

UMTK_OPTIONS = [
    # General
    {"key": "enable_umtk", "type": "bool", "default": True, "label": "Enable UMTK", "description": "Enable Upcoming Movies & TV Shows processing", "section": "General"},
    {"key": "movies", "type": "select", "default": 2, "label": "Movie Method", "description": "Choose how to handle upcoming movies", "options": [{"value": 0, "label": "Disabled"}, {"value": 1, "label": "Download trailers"}, {"value": 2, "label": "Placeholder"}], "section": "General"},
    {"key": "tv", "type": "select", "default": 2, "label": "TV Method", "description": "Choose how to handle upcoming TV shows", "options": [{"value": 0, "label": "Disabled"}, {"value": 1, "label": "Download trailers"}, {"value": 2, "label": "Placeholder"}], "section": "General"},
    {"key": "method_fallback", "type": "bool", "default": True, "label": "Method Fallback", "description": "Try placeholder if trailer download fails", "section": "General"},
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
    {"key": "exclude_radarr_tags", "type": "string", "default": "exclude, private", "label": "Exclude Radarr Tags", "description": "Comma-separated tags to exclude from processing", "section": "Movies"},
    {"key": "umtk_root_movies", "type": "string", "default": "", "label": "UMTK Root Movies", "description": "Custom root path for movie folders. Mount this in your Docker Compose", "section": "Movies"},
    # TV Shows
    {"key": "future_days_upcoming_shows", "type": "int", "default": 30, "label": "Future Days (Shows)", "description": "Days ahead to look for upcoming shows", "section": "TV Shows"},
    {"key": "recent_days_new_show", "type": "int", "default": 7, "label": "Recent Days (New Show)", "description": "Days back to look for newly premiered shows", "section": "TV Shows"},
    {"key": "future_only_tv", "type": "bool", "default": False, "label": "Future Only (TV)", "description": "Only show TV not yet aired", "section": "TV Shows"},
    {"key": "exclude_sonarr_tags", "type": "string", "default": "exclude, private", "label": "Exclude Sonarr Tags", "description": "Comma-separated tags to exclude from processing", "section": "TV Shows"},
    {"key": "umtk_root_tv", "type": "string", "default": "", "label": "UMTK Root TV", "description": "Custom root path for TV folders. Mount this in your Docker Compose", "section": "TV Shows"},
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
]

TSSK_OPTIONS = [
    {"key": "enable_tssk", "type": "bool", "default": False, "label": "Enable TSSK", "description": "Enable TV Show Status processing", "section": "General", "config_file": "umtk"},
    {"key": "use_tvdb", "type": "bool", "default": False, "label": "Use TVDB", "description": "Use TheTVDB instead of TMDB for Tv Show status", "section": "General"},
    {"key": "skip_unmonitored", "type": "bool", "default": True, "label": "Skip Unmonitored", "description": "Skip unmonitored shows/episodes", "section": "General"},
    {"key": "ignore_finales_tags", "type": "string", "default": "ignorefinales", "label": "Ignore Finales Tags", "description": "Comma-separated Sonarr tags to exclude from finale detection", "section": "General"},
    {"key": "edit_sort_titles", "type": "bool", "default": True, "label": "Edit Sort Titles", "description": "Update Plex sort titles for upcoming seasons (Requires Plex Connection)", "section": "General"},
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


def _get_config_value(config, key, default=None):
    """Get a value from config with type coercion."""
    val = config.get(key)
    if val is None:
        return default
    return val


def _test_connection(url, api_key=None, token=None, timeout=10):
    """Test a connection to a service. Returns (success, message, response_time_ms)."""
    import time
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
        return False, str(e), 0


def _resolve_arr_api_url(base_url, api_key, service='radarr'):
    """Resolve the working API v3 URL for a *arr service."""
    base = base_url.rstrip('/')
    if base.startswith('http'):
        protocol_end = base.find('://') + 3
        next_slash = base.find('/', protocol_end)
        if next_slash != -1:
            base = base[:next_slash]
    for path in ['/api/v3', f'/{service}/api/v3']:
        try:
            resp = requests.get(f"{base}{path}/health",
                                headers={"X-Api-Key": api_key}, timeout=5)
            if resp.status_code == 200:
                return f"{base}{path}"
        except Exception:
            continue
    return None


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
            result.append({**opt, "value": val})
        return jsonify(result)

    @app.route("/api/config/connections", methods=["POST"])
    def api_save_connections():
        config = _load_yaml(webui._config_path)
        data = request.get_json()
        for key, value in data.items():
            config[key] = value
        _save_yaml(webui._config_path, config)
        return jsonify({"ok": True})

    # ── Config: UMTK ──────────────────────────────────────────────────
    @app.route("/api/config/umtk")
    def api_config_umtk():
        config = _load_yaml(webui._config_path)
        result = {"options": [], "blocks": {}}
        for opt in UMTK_OPTIONS:
            val = _get_config_value(config, opt["key"], opt["default"])
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
        for key, value in options.items():
            config[key] = value
        for key, value in blocks.items():
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
            # Check if this option should go to UMTK config
            opt_meta = next((o for o in TSSK_OPTIONS if o["key"] == key), None)
            if opt_meta and opt_meta.get("config_file") == "umtk":
                umtk_config[key] = value
            else:
                tssk_config[key] = value
        for key, value in blocks.items():
            tssk_config[key] = value
        _save_yaml(webui._config_path, umtk_config)
        _save_yaml(webui._tssk_config_path, tssk_config)
        return jsonify({"ok": True})

    # ── Connection tests ──────────────────────────────────────────────
    @app.route("/api/test/plex", methods=["POST"])
    def api_test_plex():
        data = request.get_json() or {}
        url = data.get("plex_url", "")
        token = data.get("plex_token", "")
        if not url or not token:
            return jsonify({"success": False, "message": "URL and token required"})
        ok, msg, ms = _test_connection(url, token=token)
        return jsonify({"success": ok, "message": msg, "response_time": ms})

    @app.route("/api/test/radarr", methods=["POST"])
    def api_test_radarr():
        data = request.get_json() or {}
        url = data.get("radarr_url", "")
        key = data.get("radarr_api_key", "")
        if not url or not key:
            return jsonify({"success": False, "message": "URL and API key required"})
        ok, msg, ms = _test_connection(url, api_key=key)
        return jsonify({"success": ok, "message": msg, "response_time": ms})

    @app.route("/api/test/sonarr", methods=["POST"])
    def api_test_sonarr():
        data = request.get_json() or {}
        url = data.get("sonarr_url", "")
        key = data.get("sonarr_api_key", "")
        if not url or not key:
            return jsonify({"success": False, "message": "URL and API key required"})
        ok, msg, ms = _test_connection(url, api_key=key)
        return jsonify({"success": ok, "message": msg, "response_time": ms})

    # ── Dashboard: upcoming content ──────────────────────────────────
    @app.route("/api/dashboard/upcoming")
    def api_dashboard_upcoming():
        config = _load_yaml(webui._config_path)
        items = []
        now = datetime.now()
        start = now.strftime('%Y-%m-%d')
        end_date = now + timedelta(days=30)
        end = end_date.strftime('%Y-%m-%d')
        include_in_cinemas = str(config.get('include_inCinemas', 'false')).lower() == 'true'

        # ── Sonarr calendar ──
        sonarr_url = config.get('sonarr_url', '')
        sonarr_key = config.get('sonarr_api_key', '')
        if sonarr_url and sonarr_key:
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
                            sid = series.get('id')
                            if not sid:
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
                                    '_air': air
                                }

                        for entry in series_map.values():
                            del entry['_air']
                            items.append(entry)
            except Exception:
                pass

        # ── Radarr movies ──
        radarr_url = config.get('radarr_url', '')
        radarr_key = config.get('radarr_api_key', '')
        if radarr_url and radarr_key:
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
        config = _load_yaml(webui._config_path)
        services = []

        plex_url = config.get('plex_url', '')
        plex_token = config.get('plex_token', '')
        if plex_url and plex_token:
            ok, msg, ms = _test_connection(plex_url, token=plex_token, timeout=5)
            services.append({'name': 'Plex', 'online': ok, 'message': msg, 'responseTime': ms})
        else:
            services.append({'name': 'Plex', 'online': False, 'message': 'Not configured', 'responseTime': 0})

        radarr_url = config.get('radarr_url', '')
        radarr_key = config.get('radarr_api_key', '')
        if radarr_url and radarr_key:
            ok, msg, ms = _test_connection(radarr_url, api_key=radarr_key, timeout=5)
            services.append({'name': 'Radarr', 'online': ok, 'message': msg, 'responseTime': ms})
        else:
            services.append({'name': 'Radarr', 'online': False, 'message': 'Not configured', 'responseTime': 0})

        sonarr_url = config.get('sonarr_url', '')
        sonarr_key = config.get('sonarr_api_key', '')
        if sonarr_url and sonarr_key:
            ok, msg, ms = _test_connection(sonarr_url, api_key=sonarr_key, timeout=5)
            services.append({'name': 'Sonarr', 'online': ok, 'message': msg, 'responseTime': ms})
        else:
            services.append({'name': 'Sonarr', 'online': False, 'message': 'Not configured', 'responseTime': 0})

        return jsonify(services)

    # ── Log ────────────────────────────────────────────────────────────
    @app.route("/api/log")
    def api_log():
        """Return the last N lines from the log file, filtering out HTTP request noise."""
        import re
        limit = request.args.get("limit", 500, type=int)
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
