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
        on_click=ui.Call("__panel__center", view="connect", site_id=""),
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

    root = ui.Stack(children=[connect_btn, ui.Divider(), site_list], gap=3)

    if not active_site_id and rows:
        root.props["auto_action"] = ui.Call(
            "__panel__center", view="", site_id=rows[0]["id"], active_tab="posts"
        )

    return root


# ── Single center panel — branches on `view` and `active_tab` kwargs ──────────

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
        ui.Button(
            "Cancel",
            variant="ghost",
            on_click=ui.Call("__panel__center", view="", site_id=""),
        ),
    ], gap=4)


# ── Site detail with manual tab switching ─────────────────────────────────────


def _render_content_table(items, tab):
    if items is None:
        return ui.Alert(message="Could not load — check the connection.", type="error")
    if not items:
        return ui.Empty(message=f"No {tab} found.")
    if tab == "media":
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
    return ui.DataTable(columns=columns, rows=rows)


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

    async def _get(path, per_page):
        try:
            return await wp_get(ctx, base_url, path, username=username, app_password=pw,
                                params={"per_page": per_page})
        except Exception:
            return None

    def _body(r):
        return r.body if r and r.status_code == 200 and isinstance(r.body, list) else None

    # Health stats come from the stored record (updated by the Refresh button).
    reachable = record.get("status") == "connected"
    auth_ok = reachable
    ssl_valid = base_url.startswith("https://")

    # Content: serve from cache on tab switch; fetch all in parallel on first load.
    cached = await storage.get_content_cache(ctx, site_id)
    if cached:
        posts_data = cached.get("posts")
        pages_data = cached.get("pages")
        media_data = cached.get("media")
    else:
        posts_r, pages_r, media_r = await asyncio.gather(
            _get("/wp-json/wp/v2/posts", 20),
            _get("/wp-json/wp/v2/pages", 20),
            _get("/wp-json/wp/v2/media", 20),
        )
        posts_data = _body(posts_r)
        pages_data = _body(pages_r)
        media_data = _body(media_r)
        await storage.set_content_cache(ctx, site_id, posts_data, pages_data, media_data)

    items = {"posts": posts_data, "pages": pages_data, "media": media_data}.get(active_tab)

    health_stats = ui.Stats(columns=3, children=[
        ui.Stat(label="Reachable", value="Yes" if reachable else "No",
                color="green" if reachable else "red"),
        ui.Stat(label="Auth",      value="OK" if auth_ok else "Failed",
                color="green" if auth_ok else "red"),
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

    tab_bar = ui.Stack(
        children=[_tab_btn("Posts", "posts"), _tab_btn("Pages", "pages"), _tab_btn("Media", "media")],
        direction="h", gap=1, sticky=True,
    )

    return ui.Page(title=name, subtitle=base_url, children=[
        health_stats,
        tab_bar,
        _render_content_table(items, active_tab),
    ])
