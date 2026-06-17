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


@ext.panel("detail", slot="center", title="Site")
async def detail(ctx, site_id=None, **kwargs):
    """Center panel: site dashboard — health status, content counts, and content tabs."""
    if not site_id:
        return ui.Empty(message="Select a site to view its dashboard.")
    record = await storage.get_site_record(ctx, site_id) or {}
    name = record.get("name", site_id)
    base_url = record.get("url", "")
    pw = await storage.get_credential(ctx, site_id)
    if not base_url or not pw:
        return ui.Section(title=name, children=[
            ui.Empty(message="Credential missing — reconnect this site.")
        ])

    username = record.get("username", "")

    async def _get(path, per_page):
        try:
            return await wp_get(ctx, base_url, path, username=username, app_password=pw,
                                params={"per_page": per_page})
        except Exception:
            return None

    me, posts_r, pages_r, media_r = await asyncio.gather(
        _get("/wp-json/wp/v2/users/me", 1),
        _get("/wp-json/wp/v2/posts", 20),
        _get("/wp-json/wp/v2/pages", 20),
        _get("/wp-json/wp/v2/media", 20),
    )
    reachable = me is not None
    auth_ok = me is not None and me.status_code == 200
    ssl_valid = base_url.startswith("https://")
    posts, pages, media = _items_or_none(posts_r), _items_or_none(pages_r), _items_or_none(media_r)

    def _n(lst): return len(lst) if lst is not None else "?"

    # Status badges row
    status_row = ui.Stack(direction="h", gap=2, children=[
        ui.Badge("Reachable" if reachable else "Unreachable",
                 color="green" if reachable else "red"),
        ui.Badge("Auth OK" if auth_ok else "Auth failed",
                 color="green" if auth_ok else "red"),
        ui.Badge("HTTPS" if ssl_valid else "No SSL",
                 color="green" if ssl_valid else "red"),
    ])
    counts_row = ui.Stack(direction="h", gap=3, children=[
        ui.Badge(f"{_n(posts)}", value="posts", color="gray"),
        ui.Badge(f"{_n(pages)}", value="pages", color="gray"),
        ui.Badge(f"{_n(media)}", value="media", color="gray"),
    ])
    health_card = ui.Card(
        title="Status",
        subtitle=base_url,
        content=ui.Stack(children=[status_row, counts_row]),
    )

    tabs = [_content_tab("Posts", posts), _content_tab("Pages", pages), _content_tab("Media", media)]

    return ui.Stack(children=[
        ui.Section(title=name, children=[
            health_card,
            ui.Button("Disconnect", variant="secondary",
                      on_click=ui.Call("forget_site", site_id=site_id)),
        ]),
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
