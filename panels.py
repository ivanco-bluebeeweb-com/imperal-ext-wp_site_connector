import asyncio
from urllib.parse import urlparse

from imperal_sdk import ui
from app import ext
from wp_client import wp_get, wp_title
from models import VNEXT
import storage


def _site_card(record):
    site_id = record.get("id", "")
    url = record.get("url", "")
    name = urlparse(url).netloc or record.get("name", site_id)
    status = record.get("status", "connected")
    is_ok = status == "connected"
    return ui.ListItem(
        id=site_id,
        title=name,
        badge=ui.Badge(label="", color="green" if is_ok else "red"),
        actions=[
            {"icon": "RefreshCw", "on_click": ui.Call("refresh_site", site_id=site_id)},
            {"icon": "Trash2",    "on_click": ui.Call("forget_site",  site_id=site_id)},
        ],
        on_click=ui.Call("__panel__detail", site_id=site_id),
    )


@ext.panel("overview", slot="center", title="WP Sites")
async def overview(ctx, search="", status_filter="", **kwargs):
    """Single-panel monitoring overview: searchable, filterable 3-column grid of site cards with status Select filter."""
    rows = await storage.list_site_records(ctx)
    total = len(rows)

    def _matches_search(r, q):
        netloc = urlparse(r.get("url", "")).netloc.lower()
        name = r.get("name", "").lower()
        return q in name or q in netloc

    filtered = [
        r for r in rows
        if (not search or _matches_search(r, search.lower()))
        and (not status_filter or r.get("status", "connected") == status_filter)
    ]

    # Header
    header = ui.Stack(direction="h", justify="between", children=[
        ui.Text(f"{total} site{'s' if total != 1 else ''} connected", variant="heading"),
        ui.Button("+ Connect New Site", variant="primary",
                  on_click=ui.Call("__panel__connect_form")),
    ])

    # Filter bar
    filter_bar = ui.Stack(direction="h", gap=2, children=[
        ui.Input(
            placeholder="Search sites… (Enter to filter)",
            param_name="search",
            value=search,
            on_submit=ui.Call("__panel__overview", status_filter=status_filter),
        ),
        ui.Select(
            options=[
                {"value": "",          "label": "All"},
                {"value": "connected", "label": "Connected"},
                {"value": "error",     "label": "Error"},
            ],
            value=status_filter,
            placeholder="All",
            param_name="status_filter",
            on_change=ui.Call("__panel__overview", search=search),
        ),
    ])

    # Grid
    if not rows:
        grid = ui.Empty(message="No sites connected yet. Click + Connect New Site to get started.")
    elif not filtered:
        grid = ui.Empty(message="No sites match your filter.")
    else:
        connect_card = ui.Card(
            content=ui.Stack(direction="v", align="center", justify="center", gap=2, children=[
                ui.Text("Connect new site"),
            ]),
            on_click=ui.Call("__panel__connect_form"),
        )
        grid = ui.Grid(columns=3, gap=4,
                       children=[_site_card(r) for r in filtered] + [connect_card])

    return ui.Stack(gap=4, children=[header, filter_bar, grid])


def _items_or_none(r):
    if r is None or r.status_code != 200 or not isinstance(r.body, list):
        return None
    return r.body


def _content_tab(label, items):
    if items is None:
        return {"label": label, "content": ui.Alert(
            message="Could not load — check the connection.", type="error")}
    if not items:
        return {"label": label, "content": ui.Empty(message=f"No {label.lower()} found.")}
    if label == "Media":
        columns = [
            ui.DataColumn("title",     "Title", sortable=True),
            ui.DataColumn("mime_type", "Type",  sortable=True),
        ]
        rows = [
            {"title": wp_title(it), "mime_type": it.get("mime_type", "")}
            for it in items
        ]
    else:
        columns = [
            ui.DataColumn("title",  "Title",  sortable=True),
            ui.DataColumn("status", "Status", sortable=True),
            ui.DataColumn("date",   "Date",   sortable=True),
        ]
        rows = [
            {
                "title":  wp_title(it),
                "status": it.get("status", ""),
                "date":   (it.get("date", "") or "")[:10],
            }
            for it in items
        ]
    return {"label": label, "content": ui.DataTable(columns=columns, rows=rows)}


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

    health_stats = ui.Stats(columns=3, children=[
        ui.Stat(label="Reachable", value="Yes" if reachable else "No",
                color="green" if reachable else "red"),
        ui.Stat(label="Auth",      value="OK" if auth_ok else "Failed",
                color="green" if auth_ok else "red"),
        ui.Stat(label="SSL",       value="HTTPS" if ssl_valid else "HTTP",
                color="green" if ssl_valid else "red"),
    ])
    count_stats = ui.Stats(columns=3, children=[
        ui.Stat(label="Posts", value=_n(posts), color="blue"),
        ui.Stat(label="Pages", value=_n(pages), color="blue"),
        ui.Stat(label="Media", value=_n(media), color="blue"),
    ])
    tabs = [_content_tab("Posts", posts), _content_tab("Pages", pages), _content_tab("Media", media)]
    back_btn = ui.Button("← All sites", variant="secondary",
                         on_click=ui.Call("__panel__overview"))
    return ui.Page(title=name, subtitle=base_url, children=[
        back_btn,
        health_stats,
        count_stats,
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
