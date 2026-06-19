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
    refresh="on_event:wp-site-connector.connect_site,wp-site-connector.forget_site,wp-site-connector.refresh_site",
)
async def sidebar(ctx, active_site_id="", **kwargs):
    """Left panel: Connect Site button + divider + list of connected sites."""
    rows = await storage.list_site_records(ctx)

    connect_btn = ui.Button(
        "Connect Site",
        icon="Plus",
        variant="primary",
        full_width=True,
        on_click=ui.Call("__panel__connect_form"),
    )

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
                on_click=ui.Call("__panel__detail", site_id=r["id"]),
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

    root = ui.Stack(children=[connect_btn, ui.Divider(), site_list], gap=3)

    # Auto-open the first site on first load. Guard: only when no site is active.
    if not active_site_id and rows:
        root.props["auto_action"] = ui.Call("__panel__detail", site_id=rows[0]["id"])

    return root


# ── Site detail (center overlay) ──────────────────────────────────────────────

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


@ext.panel("detail", slot="center", center_overlay=True, title="Site")
async def detail(ctx, site_id="", **kwargs):
    """Center overlay: site dashboard — health status, content counts, and content tabs."""
    if not site_id:
        return ui.Empty(message="Select a site from the list to view its dashboard.")

    record = await storage.get_site_record(ctx, site_id) or {}
    if not record:
        return ui.Empty(message="Site not found — it may have been removed.")

    base_url = record.get("url", "")
    pw = await storage.get_credential(ctx, site_id)
    if not base_url or not pw:
        return ui.Alert(
            message="Credential missing — reconnect this site.",
            type="error",
        )

    username = record.get("username", "")
    name = urlparse(base_url).netloc or record.get("name", site_id)

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
    posts = _items_or_none(posts_r)
    pages = _items_or_none(pages_r)
    media = _items_or_none(media_r)

    def _n(lst):
        return len(lst) if lst is not None else "?"

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

    return ui.Page(title=name, subtitle=base_url, children=[
        health_stats,
        count_stats,
        ui.Tabs(tabs=tabs),
    ])


# ── Connect form (center overlay) ─────────────────────────────────────────────

def _field(label, help_text, input_node):
    return ui.Stack(children=[
        ui.Tooltip(content=help_text, children=ui.Text(label)),
        input_node,
    ])


@ext.panel("connect_form", slot="center", title="Connect a WordPress site")
async def connect_form(ctx, **kwargs):
    """Center overlay: connection form. Captures URL + username + Application Password."""
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
        ui.Button(
            "Cancel",
            variant="ghost",
            on_click=ui.Call("__panel__detail"),
        ),
    ], gap=4)
