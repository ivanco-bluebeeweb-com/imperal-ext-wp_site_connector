from datetime import datetime, timezone

from app import ext, chat
from imperal_sdk import ActionResult
from models import SiteIdParams, Site
from wp_client import normalize_base_url, site_id_from_url, wp_get, wp_error_message
import storage


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# connect_site is an @ext.tool, NOT a @chat.function: the intent classifier cannot
# select it, so the Application Password (a form field) never enters LLM context.
# The connection panel form dispatches to it by name.
@ext.tool(
    "connect_site",
    description="Validate and store a WordPress site connection (panel connection-form action; not LLM-visible).",
)
async def connect_site(ctx, url: str = "", username: str = "", app_password: str = "") -> dict:
    """Validate WP credentials via /users/me, then persist the site record and its Application Password."""
    try:
        base_url = normalize_base_url(url)
    except ValueError:
        return {"status": "error", "error": "Site URL must start with https://"}

    site_id = site_id_from_url(base_url)
    try:
        r = await wp_get(ctx, base_url, "/wp-json/wp/v2/users/me",
                         username=username, app_password=app_password)
    except Exception as e:
        await ctx.log(f"connect_site http error: {e}", level="error")
        return {"status": "error", "error": "Could not reach the site — check the URL and try again."}

    if r.status_code != 200:
        return {"status": "error", "error": wp_error_message(r.status_code)}

    name = (r.json() or {}).get("name") or base_url
    record = {"id": site_id, "name": name, "url": base_url, "username": username,
              "status": "connected", "last_checked": _now()}
    await storage.save_site_record(ctx, record)
    await storage.set_credential(ctx, site_id, app_password)
    return {"status": "success", "site_id": site_id, "name": name}


# forget_site IS a @chat.function with action_type="destructive": the web-kernel shows the
# KAV confirmation card automatically. It takes only site_id — no credential in args.
@chat.function(
    "forget_site",
    description="Disconnect a WordPress site and delete its stored credential.",
    action_type="destructive",
    data_model=Site,
    effects=["wp.disconnect"],
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
        site, summary=f"Disconnected {record.get('name', params.site_id)}", refresh_panels=["dashboard"])
