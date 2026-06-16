from imperal_sdk import ActionResult, sdl
from app import chat
from models import _NoParams, Site
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
