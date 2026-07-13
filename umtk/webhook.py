#file: umtk/webhook.py

import logging
import threading
from pathlib import Path
from urllib.parse import quote

import requests

logger = logging.getLogger(__name__)


def _apply_path_map(value: str, path_from: str, path_to: str) -> str:
    """Normalise separators and rewrite a leading *path_from* to *path_to*.

    Media servers and scan tools (autoscan, autopulse, Plex, ...) expect
    forward-slash paths, so separators are always normalised. The optional
    remap is used when UMTK writes media under a different mount point than
    the media server (common with Docker volume mappings).
    """
    norm = value.replace("\\", "/")
    if path_from:
        src = path_from.replace("\\", "/")
        if norm.startswith(src):
            return path_to + norm[len(src):]
    return norm


def _build_tokens(new_path: Path, path_from: str, path_to: str) -> dict:
    new_s = _apply_path_map(str(new_path), path_from, path_to)
    dir_s = _apply_path_map(str(new_path.parent), path_from, path_to)
    return {
        "{path}": new_s,
        "{path_enc}": quote(new_s),
        "{dir}": dir_s,
        "{dir_enc}": quote(dir_s),
        "{filename}": new_path.name,
        "{name_noext}": new_path.stem,
    }


def _substitute(template: str, tokens: dict) -> str:
    if not template:
        return template
    out = template
    for token, value in tokens.items():
        out = out.replace(token, value)
    return out


def _parse_headers(lines) -> dict:
    headers = {}
    for line in lines or []:
        if not line or ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        if key:
            headers[key] = value.strip()
    return headers


def _send(method: str, url: str, *, data, headers, auth, timeout) -> None:
    try:
        resp = requests.request(
            method, url, data=data, headers=headers or None,
            auth=auth, timeout=timeout,
        )
        if resp.status_code >= 400:
            logger.warning(
                "Webhook returned HTTP %d for %s: %s",
                resp.status_code, url, resp.text[:200],
            )
        else:
            logger.info("Webhook sent (%s %d): %s",
                        method, resp.status_code, url)
    except requests.exceptions.RequestException as exc:
        logger.warning("Webhook request failed for %s: %s", url, exc)
    except Exception as exc:
        logger.warning("Webhook error for %s: %s", url, exc)


def send_file_webhook(config, new_path: Path) -> None:
    """Fire the configured webhook for a placeholder/trailer file event.

    Called once per newly written placeholder or downloaded trailer, and once
    per placeholder/trailer removed during cleanup, so an external scan tool
    (autoscan, autopulse, ...) can pick the change up in Plex. On removal the
    path passed is the file or folder that was deleted.

    Fire-and-forget: the HTTP call runs on a daemon thread so a slow or
    unreachable endpoint never stalls the processing loop, and any error
    is logged rather than raised.
    """
    if not config.get("webhook_enabled", False):
        return

    tokens = _build_tokens(
        new_path,
        config.get("webhook_path_from", "") or "",
        config.get("webhook_path_to", "") or "",
    )

    url = _substitute(config.get("webhook_url", "") or "", tokens).strip()
    if not url:
        return

    method = (config.get("webhook_method", "POST") or "POST").upper()
    if method not in ("GET", "POST"):
        method = "POST"

    content_type = (config.get("webhook_content_type", "form") or "form").lower()
    body_tmpl = config.get("webhook_body", "") or ""
    data = None
    headers = _parse_headers(config.get("webhook_headers", []))

    if content_type != "none" and body_tmpl:
        data = _substitute(body_tmpl, tokens)
        # Only set a Content-Type if the user hasn't supplied one.
        if not any(k.lower() == "content-type" for k in headers):
            if content_type == "json":
                headers["Content-Type"] = "application/json"
            elif content_type == "form":
                headers["Content-Type"] = "application/x-www-form-urlencoded"

    auth = None
    user = config.get("webhook_auth_user", "") or ""
    if user:
        auth = (user, config.get("webhook_auth_pass", "") or "")

    try:
        timeout = int(config.get("webhook_timeout_seconds", 10) or 10)
    except (TypeError, ValueError):
        timeout = 10

    thread = threading.Thread(
        target=_send, args=(method, url),
        kwargs={"data": data, "headers": headers,
                "auth": auth, "timeout": timeout},
        daemon=True,
    )
    thread.start()
