import asyncio

from imperal_sdk import ui
from app import ext
from wp_client import wp_get, wp_title
from models import VNEXT
import storage


def _site_card(record):
    site_id = record.get("id", "")
    name = record.get("name", site_id)
    url = record.get("url", "")
    status = record.get("status", "connected")
    is_ok = status == "connected"
    return ui.Card(
        title=name,
        subtitle=url,
        content=ui.Badge("Connected" if is_ok else "Error",
                         color="green" if is_ok else "red"),
        footer=ui.Button("View", variant="secondary",
                         on_click=ui.Call("__panel__detail", site_id=site_id)),
    )


@ext.panel("overview", slot="center", title="WP Sites")
async def overview(ctx, search="", status_filter="", **kwargs):
    """Single-panel monitoring overview: searchable, filterable 2-column grid of site cards."""
    rows = await storage.list_site_records(ctx)
    total = len(rows)

    filtered = [
        r for r in rows
        if (not search or search.lower() in r.get("name", "").lower())
        and (not status_filter or r.get("status", "") == status_filter)
    ]

    # Header
    header = ui.Stack(direction="h", justify="between", children=[
        ui.Text(f"{total} site{'s' if total != 1 else ''} connected"),
        ui.Button("+ Connect New Site", variant="primary",
                  on_click=ui.Call("__panel__connect_form")),
    ])

    # Filter bar
    def _filter_btn(label, value):
        active = (value == "" and not status_filter) or (value and status_filter == value)
        return ui.Button(
            label,
            variant="primary" if active else "secondary",
            on_click=ui.Call("__panel__overview", search=search, status_filter=value),
        )

    filter_bar = ui.Stack(direction="h", gap=2, children=[
        ui.Input(
            placeholder="Search sites… (Enter to filter)",
            param_name="search",
            value=search,
            on_submit=ui.Call("__panel__overview", status_filter=status_filter),
        ),
        ui.Stack(direction="h", gap=1, children=[
            _filter_btn("All", ""),
            _filter_btn("Connected", "connected"),
            _filter_btn("Error", "error"),
        ]),
    ])

    # Grid
    if not rows:
        grid = ui.Empty(message="No sites connected yet. Click + Connect New Site to get started.")
    elif not filtered:
        grid = ui.Empty(message="No sites match your filter.")
    else:
        pairs = [filtered[i:i + 2] for i in range(0, len(filtered), 2)]
        grid = ui.Stack(children=[
            ui.Stack(direction="h", gap=3, children=[_site_card(r) for r in pair])
            for pair in pairs
        ])

    return ui.Stack(gap=4, children=[header, filter_bar, grid])


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

    back_btn = ui.Button("← All sites", variant="secondary",
                         on_click=ui.Call("__panel__overview"))
    return ui.Stack(children=[
        back_btn,
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
