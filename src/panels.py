from imperal_sdk import ui
from app import ext
from wp_client import wp_get
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
    return ui.Stack(children=[
        ui.Button("+ Connect site", variant="primary", full_width=True,
                  on_click=ui.Call("__panel__connect_form")),
        body,
    ])


async def _fetch_items(ctx, site_id, path):
    record = await storage.get_site_record(ctx, site_id)
    pw = await storage.get_credential(ctx, site_id) if record else None
    if not record or not pw:
        return None
    try:
        r = await wp_get(ctx, record["url"], path, username=record["username"],
                         app_password=pw, params={"per_page": 20})
    except Exception:
        return None
    if r.status_code != 200 or not isinstance(r.body, list):
        return None
    return r.body


def _title(item):
    t = item.get("title")
    return t.get("rendered") if isinstance(t, dict) else (t or str(item.get("id")))


def _content_tab(label, items):
    if items is None:
        return {"label": label, "content": ui.Empty(message="Could not load — check the connection.")}
    if not items:
        return {"label": label, "content": ui.Empty(message=f"No {label.lower()} found.")}
    return {"label": label, "content": ui.List(items=[
        ui.ListItem(id=str(it.get("id")), title=_title(it), subtitle=it.get("status", ""))
        for it in items
    ])}


@ext.panel("detail", slot="center", title="Site")
async def detail(ctx, site_id=None, **kwargs):
    """Center panel: selected site header, health refresh, and content tabs."""
    if not site_id:
        return ui.Empty(message="Select a site to view its content.")
    record = await storage.get_site_record(ctx, site_id) or {}
    tabs = [
        _content_tab("Posts", await _fetch_items(ctx, site_id, "/wp-json/wp/v2/posts")),
        _content_tab("Pages", await _fetch_items(ctx, site_id, "/wp-json/wp/v2/pages")),
        _content_tab("Media", await _fetch_items(ctx, site_id, "/wp-json/wp/v2/media")),
    ]
    return ui.Stack(children=[
        ui.Section(children=[
            ui.Button("Refresh health", on_click=ui.Call("get_site_health", site_id=site_id)),
        ], title=record.get("name", site_id)),
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
               ui.Input(param_name="url", type="url", placeholder="https://example.com")),
        _field("Username", "The WordPress username that created the Application Password",
               ui.Input(param_name="username", placeholder="admin")),
        _field("Application Password", "Create this under Users → Profile → Application Passwords in WordPress",
               ui.Password(param_name="app_password")),
    ])
