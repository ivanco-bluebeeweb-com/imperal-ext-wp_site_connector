from datetime import datetime, timezone

from app import chat
from imperal_sdk import ActionResult
from models import ConnectSiteParams, SiteIdParams, Site
from wp_client import normalize_base_url, site_id_from_url, wp_get, wp_error_message
import storage


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@chat.function(
    "connect_site",
    description="Connect a WordPress site by URL, username, and Application Password. Creates under Users → Profile → Application Passwords in WordPress admin.",
    action_type="write",
    data_model=Site,
    effects=["wp.connect"],
    event="wp-site-connector.connect_site",
)
async def connect_site(ctx, params: ConnectSiteParams) -> ActionResult:
    """Validate WP credentials via /users/me, then persist the site record and its Application Password."""
    try:
        base_url = normalize_base_url(params.url)
    except ValueError:
        return ActionResult.error("Site URL must start with https://", retryable=False)

    site_id = site_id_from_url(base_url)
    try:
        r = await wp_get(ctx, base_url, "/wp-json/wp/v2/users/me",
                         username=params.username, app_password=params.app_password)
    except Exception as e:
        await ctx.log(f"connect_site http error: {e}", level="error")
        return ActionResult.error("Could not reach the site — check the URL and try again.", retryable=True)

    if r.status_code != 200:
        return ActionResult.error(wp_error_message(r.status_code),
                                  retryable=r.status_code >= 500 or r.status_code == 429)

    body = r.body if isinstance(r.body, dict) else {}
    from urllib.parse import urlparse
    name = urlparse(base_url).netloc or base_url
    record = {"id": site_id, "name": name, "url": base_url, "username": params.username,
              "status": "connected", "last_checked": _now()}
    await storage.save_site_record(ctx, record)
    await storage.set_credential(ctx, site_id, params.app_password)
    site = Site(id=site_id, title=name, kind="wp_site", url=base_url,
                username=params.username, status="connected")
    return ActionResult.success(site, summary=f"Connected {name}", refresh_panels=["overview"])


# forget_site IS a @chat.function with action_type="destructive": the web-kernel shows the
# KAV confirmation card automatically. It takes only site_id — no credential in args.
@chat.function(
    "forget_site",
    description="Disconnect a WordPress site and delete its stored credential.",
    action_type="destructive",
    data_model=Site,
    effects=["wp.disconnect"],
    event="wp-site-connector.forget_site",
)
async def forget_site(ctx, params: SiteIdParams) -> ActionResult:
    """Remove the site record and its stored Application Password after user confirmation."""
    record = await storage.get_site_record(ctx, params.site_id)
    if not record:
        return ActionResult.error("No connected site with that id.", retryable=False)
    await storage.delete_site_record(ctx, params.site_id)
    await storage.delete_credential(ctx, params.site_id)
    site = Site(id=params.site_id, title=record.get("name", params.site_id), kind="wp_site",
                url=record.get("url", ""), username=record.get("username", ""), status="disconnected")
    return ActionResult.success(
        site, summary=f"Disconnected {record.get('name', params.site_id)}", refresh_panels=["overview"])
