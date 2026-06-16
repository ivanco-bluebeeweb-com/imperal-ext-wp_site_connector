import base64
import re
from urllib.parse import urlparse

_ERROR_MESSAGES = {
    401: "WordPress rejected the credentials — reconnect the site with a fresh Application Password.",
    403: "That WordPress user lacks permission for this request.",
    404: "WordPress REST API not found — is this a WordPress site and is the REST API enabled?",
    429: "WordPress is rate-limiting requests — try again shortly.",
}


def basic_auth_header(username: str, app_password: str) -> dict:
    token = base64.b64encode(f"{username}:{app_password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def normalize_base_url(url: str) -> str:
    parsed = urlparse(url.strip())
    if parsed.scheme != "https":
        raise ValueError("Site URL must use https://")
    return f"{parsed.scheme}://{parsed.netloc}".rstrip("/")


def site_id_from_url(url: str) -> str:
    host = urlparse(url.strip()).netloc.lower()
    host = re.sub(r"^www\.", "", host)
    return re.sub(r"[^a-z0-9]+", "-", host).strip("-")


def wp_error_message(status_code: int) -> str:
    if status_code in _ERROR_MESSAGES:
        return _ERROR_MESSAGES[status_code]
    if 500 <= status_code < 600:
        return "WordPress returned a server error — try again shortly."
    return f"WordPress request failed (HTTP {status_code})."


async def wp_get(ctx, base_url, path, *, username, app_password, params=None):
    headers = basic_auth_header(username, app_password)
    return await ctx.http.get(f"{base_url}{path}", headers=headers, params=params)
