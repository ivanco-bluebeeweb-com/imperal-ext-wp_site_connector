import asyncio

from imperal_sdk import ui
from app import ext
from wp_client import wp_get, wp_title
from models import VNEXT
import storage


@ext.panel("dashboard", slot="left", title="WordPress Sites")
async def dashboard(ctx, **kwargs):
    """Left panel: connected sites with status badges and a Connect button."""
    rows = await storage.list_site_records(ctx)
    items = [
        ui.ListItem(
            id=r["id"],
            title=r.get("name", r["id"]),
            subtitle=r.get("url", ""),
            badge=ui.Badge(r.get("status", "connected"),
                           color="green" if r.get("status") == "connected" else "red"),
            on_click=ui.Call("__panel__detail", site_id=r["id"]),
        )
        for r in rows
    ]
    body = ui.List(items=items) if items else ui.Empty(message="No sites connected yet.")
    root = ui.Stack(children=[
        ui.Button("+ Connect site", variant="primary", full_width=True,
                  on_click=ui.Call("__panel__connect_form")),
        body,
    ])
    # Load center panel on mount so center_overlay has a slot to open on top of.
    if rows:
        root.props["auto_action"] = ui.Call("__panel__detail", site_id=rows[0]["id"])
    else:
        root.props["auto_action"] = ui.Call("__panel__detail")
    return root


def _items_or_none(r):
    if r is None or r.status_code != 200 or not isinstance(r.body, list):
        return None
    return r.body


def _content_tab(label, items):
    if items is None:
        return {"label": label, "content": ui.Empty(message="Could not load — check the connection.")}
    if not items:
        return {"label": label, "content": ui.Empty(message=f"No {label.lower()} found.")}
    return {"label": label, "content": ui.List(items=[
        ui.ListItem(id=str(it.get("id")), title=wp_title(it), subtitle=it.get("status", ""))
        for it in items
    ])}


def _health_card(reachable, auth_ok, ssl_valid, counts):
    lines = [
        ui.Text(f"Reachable: {'yes' if reachable else 'no'}"),
        ui.Text(f"Auth: {'ok' if auth_ok else 'failed'}"),
        ui.Text(f"SSL: {'valid' if ssl_valid else 'no'}"),
        ui.Text("Posts: {p} · Pages: {g} · Media: {m} (up to 100)".format(
            p=counts.get("posts", 0), g=counts.get("pages", 0), m=counts.get("media", 0))),
        ui.Text(f"Plugin updates: {VNEXT}"),
        ui.Text(f"PHP version: {VNEXT}"),
    ]
    return ui.Card(title="Health (read-only)", content=ui.Stack(children=lines))


@ext.panel("detail", slot="center", title="Site")
async def detail(ctx, site_id=None, **kwargs):
    """Center panel: site header + read-only health card + content tabs (Posts/Pages/Media)."""
    if not site_id:
        return ui.Empty(message="Select a site to view its content.")
    record = await storage.get_site_record(ctx, site_id) or {}
    name = record.get("name", site_id)
    base_url = record.get("url")
    pw = await storage.get_credential(ctx, site_id)
    if not base_url or not pw:
        return ui.Stack(children=[ui.Section(children=[
            ui.Empty(message="Credential missing — reconnect this site.")], title=name)])

    username = record.get("username", "")

    async def _get(path, per_page):
        try:
            return await wp_get(ctx, base_url, path, username=username, app_password=pw,
                                params={"per_page": per_page})
        except Exception:
            return None

    me, posts_r, pages_r, media_r = await asyncio.gather(
        _get("/wp-json/wp/v2/users/me", 1),
        _get("/wp-json/wp/v2/posts", 100),
        _get("/wp-json/wp/v2/pages", 100),
        _get("/wp-json/wp/v2/media", 100),
    )
    posts, pages, media = _items_or_none(posts_r), _items_or_none(pages_r), _items_or_none(media_r)
    counts = {
        "posts": len(posts) if posts is not None else 0,
        "pages": len(pages) if pages is not None else 0,
        "media": len(media) if media is not None else 0,
    }
    health = _health_card(
        reachable=me is not None,
        auth_ok=me is not None and me.status_code == 200,
        ssl_valid=base_url.startswith("https://"),
        counts=counts,
    )
    tabs = [_content_tab("Posts", posts), _content_tab("Pages", pages), _content_tab("Media", media)]
    return ui.Stack(children=[
        ui.Section(children=[health], title=name),
        ui.Tabs(tabs=tabs),
    ])


def _field(label, help_text, input_node):
    return ui.Stack(children=[
        ui.Tooltip(content=help_text, children=ui.Text(label)),
        input_node,
    ])


@ext.panel("connect_form", slot="center", title="Connect a WordPress site", center_overlay=True)
async def connect_form(ctx, **kwargs):
    """Center overlay: connection form. Submits the Application Password to the connect_site tool."""
    return ui.Form(action="connect_site", submit_label="Connect", children=[
        _field("Site URL", "The site's full address, e.g. https://example.com",
               ui.Input(param_name="url", placeholder="https://example.com")),
        _field("Username", "The WordPress username that created the Application Password",
               ui.Input(param_name="username", placeholder="admin")),
        _field("Application Password", "Create this under Users → Profile → Application Passwords in WordPress",
               ui.Password(param_name="app_password")),
    ])
