import asyncio

from imperal_sdk import ActionResult, sdl
from app import chat
from models import (_NoParams, Site, ListContentParams, ListMediaParams,
                    Post, Page, MediaItem, SiteIdParams, SiteHealth)
from wp_client import wp_get, wp_error_message, wp_title, now_iso
import storage


@chat.function("list_sites", description="List the WordPress sites the user has connected.",
               action_type="read", data_model=sdl.EntityList[Site])
async def list_sites(ctx, params: _NoParams) -> ActionResult:
    """Return all connected WordPress sites as an entity list."""
    rows = await storage.list_site_records(ctx)
    sites = [
        Site(id=r["id"], title=r.get("name", r["id"]), kind="wp_site",
             url=r.get("url", ""), username=r.get("username", ""),
             status=r.get("status", "connected"), last_checked=r.get("last_checked"))
        for r in rows
    ]
    return ActionResult.success(sdl.EntityList[Site](items=sites), summary=f"{len(sites)} site(s) connected")


async def _authed(ctx, site_id):
    record = await storage.get_site_record(ctx, site_id)
    if not record:
        return None, "No connected site with that id."
    pw = await storage.get_credential(ctx, site_id)
    if not pw:
        return None, "Stored credential is missing — reconnect the site."
    return (record["url"], record["username"], pw), None


async def _fetch(ctx, site_id, path, params):
    auth, err = await _authed(ctx, site_id)
    if err:
        return None, ActionResult.error(err, retryable=False)
    base_url, username, pw = auth
    try:
        r = await wp_get(ctx, base_url, path, username=username, app_password=pw, params=params)
    except Exception as e:
        await ctx.log(f"{path} http error: {e}", level="error")
        return None, ActionResult.error("Could not reach the site — try again.", retryable=True)
    if r.status_code != 200:
        retry = r.status_code >= 500 or r.status_code == 429
        return None, ActionResult.error(wp_error_message(r.status_code), retryable=retry)
    # HTTPResponse.body is already-parsed JSON (list for WP collection endpoints).
    # HTTPResponse.json() raises on list bodies, so read .body directly.
    return (r.body if isinstance(r.body, list) else []), None


@chat.function("list_posts", description="List recent posts on a connected WordPress site.",
               action_type="read", data_model=sdl.EntityList[Post])
async def list_posts(ctx, params: ListContentParams) -> ActionResult:
    """Return recent posts from the site's REST API as an entity list."""
    q = {"per_page": params.limit}
    if params.search:
        q["search"] = params.search
    data, err = await _fetch(ctx, params.site_id, "/wp-json/wp/v2/posts", q)
    if err:
        return err
    items = [Post(id=str(p["id"]), title=wp_title(p), kind="wp_post",
                  status=p.get("status", ""), link=p.get("link", ""), date=p.get("date")) for p in data]
    return ActionResult.success(sdl.EntityList[Post](items=items), summary=f"{len(items)} post(s)")


@chat.function("list_pages", description="List pages on a connected WordPress site.",
               action_type="read", data_model=sdl.EntityList[Page])
async def list_pages(ctx, params: ListContentParams) -> ActionResult:
    """Return pages from the site's REST API as an entity list."""
    q = {"per_page": params.limit}
    if params.search:
        q["search"] = params.search
    data, err = await _fetch(ctx, params.site_id, "/wp-json/wp/v2/pages", q)
    if err:
        return err
    items = [Page(id=str(p["id"]), title=wp_title(p), kind="wp_page",
                  status=p.get("status", ""), link=p.get("link", ""), date=p.get("date")) for p in data]
    return ActionResult.success(sdl.EntityList[Page](items=items), summary=f"{len(items)} page(s)")


@chat.function("list_media", description="List media library items on a connected WordPress site.",
               action_type="read", data_model=sdl.EntityList[MediaItem])
async def list_media(ctx, params: ListMediaParams) -> ActionResult:
    """Return media items from the site's REST API as an entity list."""
    data, err = await _fetch(ctx, params.site_id, "/wp-json/wp/v2/media", {"per_page": params.limit})
    if err:
        return err
    items = [MediaItem(id=str(m["id"]), title=wp_title(m), kind="wp_media",
                       url=m.get("source_url", ""), mime_type=m.get("mime_type", "")) for m in data]
    return ActionResult.success(sdl.EntityList[MediaItem](items=items), summary=f"{len(items)} media item(s)")


@chat.function("get_site_health", description="Report read-only health for a connected WordPress site.",
               action_type="read", data_model=SiteHealth)
async def get_site_health(ctx, params: SiteIdParams) -> ActionResult:
    """Report best-effort read-only health: reachability, auth, SSL, and content counts."""
    auth, err = await _authed(ctx, params.site_id)
    if err:
        return ActionResult.error(err, retryable=False)
    base_url, username, pw = auth

    async def _call(path, per_page=1):
        try:
            return await wp_get(ctx, base_url, path, username=username, app_password=pw,
                                params={"per_page": per_page})
        except Exception:
            return None

    me, posts_r, pages_r, media_r = await asyncio.gather(
        _call("/wp-json/wp/v2/users/me"),
        _call("/wp-json/wp/v2/posts", 100),
        _call("/wp-json/wp/v2/pages", 100),
        _call("/wp-json/wp/v2/media", 100),
    )

    def _count(r):
        return len(r.body) if r and r.status_code == 200 and isinstance(r.body, list) else 0

    reachable = me is not None
    auth_ok = me is not None and me.status_code == 200
    counts = {"posts": _count(posts_r), "pages": _count(pages_r), "media": _count(media_r)}
    health = SiteHealth(
        id=params.site_id, title=params.site_id, kind="wp_site_health",
        reachable=reachable, auth_ok=auth_ok, ssl_valid=base_url.startswith("https://"),
        content_counts=counts,
    )
    status = "✅" if auth_ok else ("⚠️" if reachable else "❌")
    return ActionResult.success(
        health,
        summary=f"{status} {params.site_id}: {counts['posts']} posts · {counts['pages']} pages · {counts['media']} media",
    )


@chat.function(
    "refresh_site",
    description="Re-check connectivity and auth for a connected WordPress site and update its stored status.",
    action_type="write",
    data_model=Site,
    effects=["wp.health_check"],
    event="wp-site-connector.refresh_site",
)
async def refresh_site(ctx, params: SiteIdParams) -> ActionResult:
    """Ping the site REST API, update stored status, and refresh the overview panel."""
    auth, err = await _authed(ctx, params.site_id)
    if err:
        return ActionResult.error(err, retryable=False)
    base_url, username, pw = auth
    try:
        r = await wp_get(ctx, base_url, "/wp-json/wp/v2/users/me",
                         username=username, app_password=pw)
    except Exception as e:
        await ctx.log(f"refresh_site http error: {e}", level="error")
        return ActionResult.error("Could not reach the site — try again.", retryable=True)
    status = "connected" if 200 <= r.status_code < 300 else "error"
    record = await storage.get_site_record(ctx, params.site_id) or {}
    await storage.save_site_record(ctx, {**record, "status": status, "last_checked": now_iso()})
    await storage.clear_content_cache(ctx, params.site_id)
    name = record.get("name", params.site_id)
    site = Site(id=params.site_id, title=name, kind="wp_site",
                url=base_url, username=username, status=status)
    icon = "✅" if status == "connected" else "❌"
    return ActionResult.success(
        site,
        summary=f"{icon} {name}: {status}",
        refresh_panels=["sidebar", "center"],
    )
