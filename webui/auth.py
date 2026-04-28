"""Authentication module for UMTK Web UI.

Provides password-based authentication with session cookies.
- First-run setup: user sets a password via the web UI
- Password hash stored in config.yml (AUTH_PASSWORD_HASH)
- Flask session secret stored in config.yml (AUTH_SECRET_KEY)
- Simple rate limiting on login attempts
"""

import secrets
import time
import threading

from werkzeug.security import generate_password_hash, check_password_hash
from flask import session, request, jsonify

# ── Rate limiter for login attempts ──────────────────────────────────────
_login_attempts_lock = threading.Lock()
_login_attempts = {}  # ip -> list of timestamps
_MAX_ATTEMPTS = 5
_WINDOW_SECONDS = 300  # 5 minutes


def _is_rate_limited(ip):
    """Check if an IP has exceeded the login attempt limit."""
    now = time.time()
    with _login_attempts_lock:
        attempts = _login_attempts.get(ip, [])
        # Prune old attempts outside the window
        attempts = [t for t in attempts if now - t < _WINDOW_SECONDS]
        _login_attempts[ip] = attempts
        return len(attempts) >= _MAX_ATTEMPTS


def _record_attempt(ip):
    """Record a failed login attempt."""
    with _login_attempts_lock:
        attempts = _login_attempts.get(ip, [])
        attempts.append(time.time())
        _login_attempts[ip] = attempts


# ── Config helpers ────────────────────────────────────────────────────────

def get_or_create_secret_key(config, save_func):
    """Return the Flask secret key, generating one if it doesn't exist."""
    key = config.get('AUTH_SECRET_KEY')
    if key:
        return key
    key = secrets.token_hex(32)
    config['AUTH_SECRET_KEY'] = key
    save_func(config)
    return key


def is_setup_required(config):
    """True if no password has been set yet (first-run state)."""
    return not config.get('AUTH_PASSWORD_HASH')


def is_auth_enabled(config):
    """True if WebUI password enforcement is enabled. Defaults to True for
    backwards compatibility with configs that don't have the key."""
    val = config.get('webui_auth_enabled')
    if val is None:
        return True
    return bool(val)


def set_password(config, password, save_func):
    """Hash and store a new password in config."""
    config['AUTH_PASSWORD_HASH'] = generate_password_hash(password)
    save_func(config)


def verify_password(config, password):
    """Check a password against the stored hash."""
    stored_hash = config.get('AUTH_PASSWORD_HASH', '')
    if not stored_hash:
        return False
    return check_password_hash(stored_hash, password)


# ── Auth route endpoints ──────────────────────────────────────────────────
# These are exempt from the before_request auth check.
AUTH_EXEMPT_PATHS = {
    '/api/auth/status',
    '/api/auth/login',
    '/api/auth/setup',
    '/api/auth/logout',
    '/api/auth/change-password',
    '/api/auth/set-enabled',
}


def register_auth_routes(app, load_config, save_config):
    """Register authentication API endpoints.

    Args:
        app: Flask app instance
        load_config: callable that returns the current config dict
        save_config: callable(config) that persists the config dict
    """

    @app.route("/api/auth/status")
    def api_auth_status():
        config = load_config()
        return jsonify({
            "setup_required": is_setup_required(config),
            "authenticated": session.get('authenticated', False),
            "auth_enabled": is_auth_enabled(config),
        })

    @app.route("/api/auth/setup", methods=["POST"])
    def api_auth_setup():
        config = load_config()
        if not is_setup_required(config):
            return jsonify({"error": "Password already set"}), 403

        data = request.get_json() or {}
        password = data.get("password", "")
        if not password or len(password) < 4:
            return jsonify({"error": "Password must be at least 4 characters"}), 400

        set_password(config, password, save_config)
        session['authenticated'] = True
        return jsonify({"ok": True})

    @app.route("/api/auth/login", methods=["POST"])
    def api_auth_login():
        ip = request.remote_addr or "unknown"

        if _is_rate_limited(ip):
            return jsonify({"error": "Too many attempts. Try again later."}), 429

        data = request.get_json() or {}
        password = data.get("password", "")

        config = load_config()
        if verify_password(config, password):
            session['authenticated'] = True
            return jsonify({"ok": True})

        _record_attempt(ip)
        return jsonify({"error": "Invalid password"}), 401

    @app.route("/api/auth/logout", methods=["POST"])
    def api_auth_logout():
        session.clear()
        return jsonify({"ok": True})

    @app.route("/api/auth/change-password", methods=["POST"])
    def api_auth_change_password():
        ip = request.remote_addr or "unknown"
        if _is_rate_limited(ip):
            return jsonify({"error": "Too many attempts. Try again later."}), 429

        data = request.get_json() or {}
        current_pw = data.get("current_password", "")
        new_pw = data.get("new_password", "")

        if not new_pw or len(new_pw) < 4:
            return jsonify({"error": "New password must be at least 4 characters"}), 400

        config = load_config()
        if is_setup_required(config):
            return jsonify({"error": "No password set. Use setup instead."}), 400

        if not verify_password(config, current_pw):
            _record_attempt(ip)
            return jsonify({"error": "Current password is incorrect"}), 401

        set_password(config, new_pw, save_config)
        return jsonify({"ok": True})

    @app.route("/api/auth/set-enabled", methods=["POST"])
    def api_auth_set_enabled():
        ip = request.remote_addr or "unknown"
        if _is_rate_limited(ip):
            return jsonify({"error": "Too many attempts. Try again later."}), 429

        data = request.get_json() or {}
        enabled = bool(data.get("enabled", True))
        current_pw = data.get("current_password", "")

        config = load_config()
        if is_setup_required(config):
            return jsonify({"error": "No password set. Complete setup first."}), 400

        if not verify_password(config, current_pw):
            _record_attempt(ip)
            return jsonify({"error": "Password is incorrect"}), 401

        config['webui_auth_enabled'] = enabled
        save_config(config)
        return jsonify({"ok": True, "auth_enabled": enabled})

    @app.before_request
    def enforce_auth():
        """Require authentication on all /api/* routes except auth endpoints."""
        path = request.path

        # Static files and index page are always accessible
        if not path.startswith('/api/'):
            return None

        # Auth endpoints are exempt
        if path in AUTH_EXEMPT_PATHS:
            return None

        # CSRF check: all POST requests must include the custom header
        if request.method == 'POST':
            if request.headers.get('X-Requested-With') != 'UMTK':
                return jsonify({"error": "Invalid request"}), 403

        # Skip session auth if password protection is disabled
        config = load_config()
        if not is_auth_enabled(config):
            return None

        # Check session authentication
        if not session.get('authenticated'):
            return jsonify({"error": "unauthorized"}), 401

        return None
