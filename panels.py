import asyncio
from urllib.parse import urlparse

from imperal_sdk import ui
from app import ext
from wp_client import wp_get, wp_title
import storage


# ── Left sidebar ──────────────────────────────────────────────────────────────

@ext.panel(
    "sidebar",
    slot="left",
    title="WP Sites",
    default_width=280,
    min_width=200,
    max_width=400,
    refresh="on_event:wp-site-connector.connect_site,wp-site-connector.forget_site,wp-site-connector.refresh_site,wp-site-connector.refresh_all_sites",
)
async def sidebar(ctx, active_site_id="", **kwargs):
    """Left panel: Connect Site + Refresh All buttons, divider, site list."""
    rows = await storage.list_site_records(ctx)

    top_bar = ui.Stack(direction="h", gap=2, children=[
        ui.Button(
            "Connect Site",
            icon="Plus",
            variant="primary",
            on_click=ui.Call("__panel__center", view="connect", site_id=""),
        ),
        ui.Button(
            "Refresh All",
            icon="RefreshCw",
            variant="secondary",
            disabled=not rows,
            on_click=ui.Call("refresh_all_sites"),
        ),
    ])

    if not rows:
        site_list = ui.Empty(message="No sites connected yet.")
    else:
        items = [
            ui.ListItem(
                id=r["id"],
                title=urlparse(r.get("url", "")).netloc or r.get("name", r["id"]),
                subtitle=r.get("status", "connected"),
                badge=ui.Badge(color="green" if r.get("status") == "connected" else "red"),
                selected=(active_site_id == r["id"]),
                on_click=ui.Call("__panel__center", view="", site_id=r["id"], active_tab="posts"),
                actions=[
                    {"icon": "RefreshCw",
                     "on_click": ui.Call("refresh_site", site_id=r["id"])},
                    {"icon": "Trash2",
                     "on_click": ui.Call("forget_site", site_id=r["id"]),
                     "confirm": f"Remove {urlparse(r.get('url', '')).netloc or r['id']}?"},
                ],
            )
            for r in rows
        ]
        site_list = ui.List(items=items)

    root = ui.Stack(children=[top_bar, ui.Divider(), site_list], gap=3)

    if not active_site_id and rows:
        root.props["auto_action"] = ui.Call(
            "__panel__center", view="", site_id=rows[0]["id"], active_tab="posts"
        )

    return root


# ── Single center panel ────────────────────────────────────────────────────────

@ext.panel("center", slot="center", center_overlay=True, title="WP Site Connector")
async def center(ctx, view="", site_id="", active_tab="posts", **kwargs):
    """Single center overlay: connect form or site detail."""
    if view == "connect":
        return _render_connect_form()
    if site_id:
        return await _render_detail(ctx, site_id, active_tab)
    return ui.Empty(message="Select a site from the list to view its dashboard.")


# ── Connect form ──────────────────────────────────────────────────────────────

def _field(label, help_text, input_node):
    return ui.Stack(children=[
        ui.Tooltip(content=help_text, children=ui.Text(label)),
        input_node,
    ])


def _render_connect_form():
    return ui.Stack(children=[
        ui.Form(action="connect_site", submit_label="Connect", children=[
            _field("Site URL",
                   "The site's full address, e.g. https://example.com",
                   ui.Input(param_name="url", placeholder="https://example.com")),
            _field("Username",
                   "The WordPress username that created the Application Password",
                   ui.Input(param_name="username", placeholder="admin")),
            _field("Application Password",
                   "Create this under Users → Profile → Application Passwords in WordPress",
                   ui.Password(param_name="app_password")),
        ]),
        ui.Button("Cancel", variant="ghost",
                  on_click=ui.Call("__panel__center", view="", site_id="")),
    ], gap=4)


# ── Content tables ────────────────────────────────────────────────────────────

def _render_content_table(items, tab):
    if items is None:
        if tab == "orders":
            return ui.Alert(message="WooCommerce not installed or insufficient permissions.",
                            type="info")
        return ui.Alert(message="Could not load — check the connection.", type="error")
    if not items:
        labels = {
            "posts": "posts", "pages": "pages", "media": "media files",
            "comments": "comments", "scheduled": "scheduled posts",
            "users": "users", "orders": "orders",
        }
        return ui.Empty(message=f"No {labels.get(tab, tab)} found.")

    if tab == "media":
        cols = [ui.DataColumn("title", "Title", sortable=True),
                ui.DataColumn("type",  "Type",  sortable=True)]
        rows = [{"title": wp_title(it), "type": it.get("mime_type", "")} for it in items]

    elif tab == "comments":
        cols = [ui.DataColumn("author",  "Author",  sortable=True),
                ui.DataColumn("snippet", "Comment", sortable=False),
                ui.DataColumn("status",  "Status",  sortable=True),
                ui.DataColumn("date",    "Date",    sortable=True)]
        rows = [
            {
                "author":  it.get("author_name", ""),
                "snippet": (it.get("content", {}).get("rendered", "") or "")
                           .replace("<p>", "").replace("</p>", "")[:60],
                "status":  it.get("status", ""),
                "date":    (it.get("date", "") or "")[:10],
            }
            for it in items
        ]

    elif tab == "scheduled":
        cols = [ui.DataColumn("title",  "Title",    sortable=True),
                ui.DataColumn("date",   "Scheduled", sortable=True)]
        rows = [{"title": wp_title(it), "date": (it.get("date", "") or "")[:16].replace("T", " ")}
                for it in items]

    elif tab == "users":
        cols = [ui.DataColumn("name",       "Name",       sortable=True),
                ui.DataColumn("role",        "Role",       sortable=True),
                ui.DataColumn("registered",  "Registered", sortable=True)]
        rows = [
            {
                "name":       it.get("name", ""),
                "role":       ", ".join(it.get("roles", [])),
                "registered": (it.get("registered_date", "") or "")[:10],
            }
            for it in items
        ]

    elif tab == "orders":
        cols = [ui.DataColumn("id",     "#",      sortable=True),
                ui.DataColumn("status", "Status", sortable=True),
                ui.DataColumn("total",  "Total",  sortable=True),
                ui.DataColumn("date",   "Date",   sortable=True)]
        rows = [
            {
                "id":     str(it.get("id", "")),
                "status": it.get("status", ""),
                "total":  f"{it.get('total', '')} {it.get('currency', '')}".strip(),
                "date":   (it.get("date_created", "") or "")[:10],
            }
            for it in items
        ]

    else:  # posts, pages
        cols = [ui.DataColumn("title",  "Title",  sortable=True),
                ui.DataColumn("status", "Status", sortable=True),
                ui.DataColumn("date",   "Date",   sortable=True)]
        rows = [{"title": wp_title(it), "status": it.get("status", ""),
                 "date": (it.get("date", "") or "")[:10]}
                for it in items]

    return ui.DataTable(columns=cols, rows=rows)


# ── Site detail ───────────────────────────────────────────────────────────────

async def _render_detail(ctx, site_id, active_tab="posts"):
    record = await storage.get_site_record(ctx, site_id) or {}
    if not record:
        return ui.Empty(message="Site not found — it may have been removed.")

    base_url = record.get("url", "")
    pw = await storage.get_credential(ctx, site_id)
    if not base_url or not pw:
        return ui.Alert(message="Credential missing — reconnect this site.", type="error")

    username = record.get("username", "")
    name = urlparse(base_url).netloc or record.get("name", site_id)

    async def _get(path, params=None):
        try:
            r = await wp_get(ctx, base_url, path, username=username, app_password=pw,
                             params=params or {"per_page": 20})
            return r.body if r.status_code == 200 and isinstance(r.body, list) else None
        except Exception:
            return None

    async def _get_orders():
        try:
            r = await wp_get(ctx, base_url, "/wp-json/wc/v3/orders",
                             username=username, app_password=pw,
                             params={"per_page": 20, "orderby": "date", "order": "desc"})
            if r.status_code in (404, 401, 403):
                return None  # WC not installed or no permission
            return r.body if r.status_code == 200 and isinstance(r.body, list) else None
        except Exception:
            return None

    # Health from stored record; updated by Refresh button.
    reachable = record.get("status") == "connected"
    ssl_valid = base_url.startswith("https://")

    # Serve from cache; fetch all in parallel on first load.
    cached = await storage.get_content_cache(ctx, site_id)
    if cached:
        posts_data     = cached.get("posts")
        pages_data     = cached.get("pages")
        media_data     = cached.get("media")
        comments_data  = cached.get("comments")
        scheduled_data = cached.get("scheduled")
        users_data     = cached.get("users")
        orders_data    = cached.get("orders")
    else:
        (posts_data, pages_data, media_data,
         comments_data, scheduled_data, users_data, orders_data) = await asyncio.gather(
            _get("/wp-json/wp/v2/posts"),
            _get("/wp-json/wp/v2/pages"),
            _get("/wp-json/wp/v2/media"),
            _get("/wp-json/wp/v2/comments",
                 {"per_page": 20, "orderby": "date", "order": "desc"}),
            _get("/wp-json/wp/v2/posts",
                 {"per_page": 20, "status": "future", "orderby": "date", "order": "asc"}),
            _get("/wp-json/wp/v2/users",
                 {"per_page": 20, "orderby": "registered", "order": "desc"}),
            _get_orders(),
        )
        await storage.set_content_cache(
            ctx, site_id,
            posts=posts_data, pages=pages_data, media=media_data,
            comments=comments_data, scheduled=scheduled_data,
            users=users_data, orders=orders_data,
        )

    content_map = {
        "posts": posts_data, "pages": pages_data, "media": media_data,
        "comments": comments_data, "scheduled": scheduled_data,
        "users": users_data, "orders": orders_data,
    }
    items = content_map.get(active_tab)

    health_stats = ui.Stats(columns=3, children=[
        ui.Stat(label="Reachable", value="Yes" if reachable else "No",
                color="green" if reachable else "red"),
        ui.Stat(label="Auth",      value="OK" if reachable else "Failed",
                color="green" if reachable else "red"),
        ui.Stat(label="SSL",       value="HTTPS" if ssl_valid else "HTTP",
                color="green" if ssl_valid else "red"),
    ])

    def _tab_btn(label, key):
        return ui.Button(
            label,
            variant="secondary" if active_tab == key else "ghost",
            size="sm",
            on_click=ui.Call("__panel__center", view="", site_id=site_id, active_tab=key),
        )

    tabs = ["posts", "pages", "media", "comments", "scheduled", "users"]
    if orders_data is not None:  # only show Orders tab if WooCommerce is installed
        tabs.append("orders")

    tab_labels = {
        "posts": "Posts", "pages": "Pages", "media": "Media",
        "comments": "Comments", "scheduled": "Scheduled",
        "users": "Users", "orders": "Orders",
    }
    tab_bar = ui.Stack(
        children=[_tab_btn(tab_labels[k], k) for k in tabs],
        direction="h", gap=1, sticky=True,
    )

    return ui.Page(title=name, subtitle=base_url, children=[
        health_stats,
        tab_bar,
        _render_content_table(items, active_tab),
    ])
