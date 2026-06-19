import asyncio
from urllib.parse import urlparse

from imperal_sdk import ui
from app import ext
from wp_client import wp_get, wp_title
import storage
import wp_cli

# WordPress built-in types and taxonomies — skip these when showing custom ones
_BUILTIN_TYPES = {
    "post", "page", "attachment", "revision", "nav_menu_item",
    "custom_css", "customize_changeset", "oembed_cache", "user_request",
    "wp_block", "wp_template", "wp_template_part", "wp_navigation",
    "wp_global_styles",
}
_BUILTIN_TAXES = {"nav_menu", "link_category", "post_format"}


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
    if view == "connect":
        return _render_connect_form()
    if view == "add_ssh" and site_id:
        await storage.set_pending_ssh_site(ctx, site_id)
        return _render_add_ssh_form(site_id)
    if site_id:
        return await _render_detail(ctx, site_id, active_tab)
    return ui.Empty(message="Select a site from the list to view its dashboard.")


# ── Connect form ──────────────────────────────────────────────────────────────

def _field(label, help_text, input_node):
    return ui.Stack(children=[
        ui.Tooltip(content=help_text, children=ui.Text(label)),
        input_node,
    ])


def _render_add_ssh_form(site_id):
    return ui.Stack(children=[
        ui.Form(action="add_ssh", submit_label="Connect via SSH", children=[
            _field("SSH Host",
                   "Hostname or IP address of the server, e.g. mysite.com or 192.168.1.1",
                   ui.Input(param_name="ssh_host", placeholder="mysite.com")),
            _field("SSH Port",
                   "SSH port number (default is 22)",
                   ui.Input(param_name="ssh_port", placeholder="22")),
            _field("SSH User",
                   "SSH username, e.g. root, ubuntu, deploy",
                   ui.Input(param_name="ssh_user", placeholder="ubuntu")),
            _field("WordPress Path",
                   "Absolute path to WordPress on the server, e.g. /var/www/html",
                   ui.Input(param_name="wp_path", placeholder="/var/www/html")),
            _field("Private Key",
                   "Paste your SSH private key (PEM format, begins with -----BEGIN). Leave empty to use password instead.",
                   ui.TextArea(param_name="ssh_key", placeholder="-----BEGIN RSA PRIVATE KEY-----\n...", rows=6)),
            _field("SSH Password",
                   "SSH password. Leave empty if using a private key above.",
                   ui.Password(param_name="ssh_password")),
        ]),
        ui.Button("Cancel", variant="ghost",
                  on_click=ui.Call("__panel__center", view="", site_id=site_id)),
    ], gap=4)


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
        return ui.Empty(message=f"No {tab.replace('cpt:', '').replace('tax:', '')} found.")

    # Taxonomy terms
    if tab.startswith("tax:"):
        cols = [ui.DataColumn("name",  "Term",  sortable=True),
                ui.DataColumn("count", "Posts", sortable=True),
                ui.DataColumn("slug",  "Slug",  sortable=True)]
        rows = [{"name": it.get("name", ""), "count": str(it.get("count", 0)),
                 "slug": it.get("slug", "")} for it in items]
        return ui.DataTable(columns=cols, rows=rows)

    # Media
    if tab == "media":
        cols = [ui.DataColumn("title", "Title", sortable=True),
                ui.DataColumn("type",  "Type",  sortable=True)]
        rows = [{"title": wp_title(it), "type": it.get("mime_type", "")} for it in items]
        return ui.DataTable(columns=cols, rows=rows)

    # Comments
    if tab == "comments":
        cols = [ui.DataColumn("author",  "Author",  sortable=True),
                ui.DataColumn("snippet", "Comment", sortable=False),
                ui.DataColumn("status",  "Status",  sortable=True),
                ui.DataColumn("date",    "Date",    sortable=True)]
        rows = [{"author": it.get("author_name", ""),
                 "snippet": (it.get("content", {}).get("rendered", "") or "")
                             .replace("<p>", "").replace("</p>", "")[:60],
                 "status": it.get("status", ""),
                 "date":   (it.get("date", "") or "")[:10]} for it in items]
        return ui.DataTable(columns=cols, rows=rows)

    # Scheduled posts
    if tab == "scheduled":
        cols = [ui.DataColumn("title", "Title",     sortable=True),
                ui.DataColumn("date",  "Scheduled", sortable=True)]
        rows = [{"title": wp_title(it),
                 "date": (it.get("date", "") or "")[:16].replace("T", " ")} for it in items]
        return ui.DataTable(columns=cols, rows=rows)

    # Users
    if tab == "users":
        cols = [ui.DataColumn("name",       "Name",       sortable=True),
                ui.DataColumn("role",        "Role",       sortable=True),
                ui.DataColumn("registered",  "Registered", sortable=True)]
        rows = [{"name": it.get("name", ""), "role": ", ".join(it.get("roles", [])),
                 "registered": (it.get("registered_date", "") or "")[:10]} for it in items]
        return ui.DataTable(columns=cols, rows=rows)

    # WooCommerce orders
    if tab == "orders":
        cols = [ui.DataColumn("id",     "#",      sortable=True),
                ui.DataColumn("status", "Status", sortable=True),
                ui.DataColumn("total",  "Total",  sortable=True),
                ui.DataColumn("date",   "Date",   sortable=True)]
        rows = [{"id": str(it.get("id", "")), "status": it.get("status", ""),
                 "total": f"{it.get('total', '')} {it.get('currency', '')}".strip(),
                 "date": (it.get("date_created", "") or "")[:10]} for it in items]
        return ui.DataTable(columns=cols, rows=rows)

    # Posts, pages, custom post types (cpt:*)
    cols = [ui.DataColumn("title",  "Title",  sortable=True),
            ui.DataColumn("status", "Status", sortable=True),
            ui.DataColumn("date",   "Date",   sortable=True)]
    rows = [{"title": wp_title(it), "status": it.get("status", ""),
             "date": (it.get("date", "") or "")[:10]} for it in items]
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

    async def _list(path, params=None):
        """Fetch a list endpoint; returns list or None on error."""
        try:
            r = await wp_get(ctx, base_url, path, username=username, app_password=pw,
                             params=params or {"per_page": 20})
            return r.body if r.status_code == 200 and isinstance(r.body, list) else None
        except Exception:
            return None

    async def _dict(path):
        """Fetch a dict endpoint (types, taxonomies); returns dict or {}.
        Uses r.json() — r.body is only parsed for list endpoints in this SDK."""
        try:
            r = await wp_get(ctx, base_url, path, username=username, app_password=pw)
            if r.status_code != 200:
                return {}
            try:
                data = r.json()
                return data if isinstance(data, dict) else {}
            except Exception:
                return r.body if isinstance(r.body, dict) else {}
        except Exception:
            return {}

    async def _orders():
        try:
            r = await wp_get(ctx, base_url, "/wp-json/wc/v3/orders",
                             username=username, app_password=pw,
                             params={"per_page": 20, "orderby": "date", "order": "desc"})
            if r.status_code in (404, 401, 403):
                return None
            return r.body if r.status_code == 200 and isinstance(r.body, list) else None
        except Exception:
            return None

    # Health from stored record; updated by Refresh button.
    reachable = record.get("status") == "connected"
    ssl_valid = base_url.startswith("https://")
    ssh_cred = await storage.get_ssh_cred(ctx, site_id)
    has_ssh = ssh_cred is not None

    cached = await storage.get_content_cache(ctx, site_id)
    # Treat cache as stale if CPT discovery hasn't run yet (older cache format)
    cache_needs_discovery = cached is None or "_cpt_meta" not in cached.get("dynamic", {})

    if cached and not cache_needs_discovery:
        posts_data     = cached.get("posts")
        pages_data     = cached.get("pages")
        media_data     = cached.get("media")
        comments_data  = cached.get("comments")
        scheduled_data = cached.get("scheduled")
        users_data     = cached.get("users")
        orders_data    = cached.get("orders")
        dynamic        = cached.get("dynamic", {})
    elif cached and cache_needs_discovery:
        # Reuse existing standard data; only re-run CPT/taxonomy discovery
        posts_data     = cached.get("posts")
        pages_data     = cached.get("pages")
        media_data     = cached.get("media")
        comments_data  = cached.get("comments")
        scheduled_data = cached.get("scheduled")
        users_data     = cached.get("users")
        orders_data    = cached.get("orders")

        types_dict, taxes_dict = await asyncio.gather(
            _dict("/wp-json/wp/v2/types"),
            _dict("/wp-json/wp/v2/taxonomies"),
        )
        custom_cpts = {s: i for s, i in types_dict.items()
                       if s not in _BUILTIN_TYPES and i.get("rest_base")}
        custom_taxes = {s: i for s, i in taxes_dict.items()
                        if s not in _BUILTIN_TAXES and i.get("rest_base")}

        cpt_slugs = list(custom_cpts.keys())
        tax_slugs = list(custom_taxes.keys())
        cpt_results, tax_results = await asyncio.gather(
            asyncio.gather(*[_list(f"/wp-json/wp/v2/{custom_cpts[s]['rest_base']}") for s in cpt_slugs]),
            asyncio.gather(*[_list(f"/wp-json/wp/v2/{custom_taxes[s]['rest_base']}",
                                   {"per_page": 50, "orderby": "count", "order": "desc"})
                             for s in tax_slugs]),
        ) if (cpt_slugs or tax_slugs) else ([], [])

        dynamic = {
            "_cpt_meta": {s: {"name": custom_cpts[s].get("name", s),
                               "rest_base": custom_cpts[s].get("rest_base")}
                          for s in cpt_slugs},
            "_tax_meta": {s: {"name": custom_taxes[s].get("name", s),
                               "rest_base": custom_taxes[s].get("rest_base")}
                          for s in tax_slugs},
        }
        for slug, items in zip(cpt_slugs, cpt_results):
            dynamic[f"cpt:{slug}"] = items or []
        for slug, items in zip(tax_slugs, tax_results):
            dynamic[f"tax:{slug}"] = items or []

        await storage.set_content_cache(
            ctx, site_id,
            posts=posts_data, pages=pages_data, media=media_data,
            comments=comments_data, scheduled=scheduled_data,
            users=users_data, orders=orders_data,
            dynamic=dynamic,
        )
    else:
        # Discover custom post types and taxonomies first
        types_dict, taxes_dict = await asyncio.gather(
            _dict("/wp-json/wp/v2/types"),
            _dict("/wp-json/wp/v2/taxonomies"),
        )

        custom_cpts = {
            slug: info for slug, info in types_dict.items()
            if slug not in _BUILTIN_TYPES and info.get("rest_base")
        }
        custom_taxes = {
            slug: info for slug, info in taxes_dict.items()
            if slug not in _BUILTIN_TAXES and info.get("rest_base")
        }

        # Fetch everything in parallel
        standard_tasks = [
            _list("/wp-json/wp/v2/posts"),
            _list("/wp-json/wp/v2/pages"),
            _list("/wp-json/wp/v2/media"),
            _list("/wp-json/wp/v2/comments",
                  {"per_page": 20, "orderby": "date", "order": "desc"}),
            _list("/wp-json/wp/v2/posts",
                  {"per_page": 20, "status": "future", "orderby": "date", "order": "asc"}),
            _list("/wp-json/wp/v2/users",
                  {"per_page": 20, "orderby": "registered", "order": "desc"}),
            _orders(),
        ]
        cpt_slugs = list(custom_cpts.keys())
        cpt_tasks = [_list(f"/wp-json/wp/v2/{custom_cpts[s]['rest_base']}") for s in cpt_slugs]
        tax_slugs = list(custom_taxes.keys())
        tax_tasks = [_list(f"/wp-json/wp/v2/{custom_taxes[s]['rest_base']}",
                           {"per_page": 50, "orderby": "count", "order": "desc"})
                     for s in tax_slugs]

        results = await asyncio.gather(*standard_tasks, *cpt_tasks, *tax_tasks)

        (posts_data, pages_data, media_data,
         comments_data, scheduled_data, users_data, orders_data) = results[:7]

        cpt_results = results[7:7 + len(cpt_slugs)]
        tax_results = results[7 + len(cpt_slugs):]

        dynamic = {
            "_cpt_meta": {s: {"name": custom_cpts[s].get("name", s),
                               "rest_base": custom_cpts[s].get("rest_base")}
                          for s in cpt_slugs},
            "_tax_meta": {s: {"name": custom_taxes[s].get("name", s),
                               "rest_base": custom_taxes[s].get("rest_base")}
                          for s in tax_slugs},
        }
        for slug, items in zip(cpt_slugs, cpt_results):
            dynamic[f"cpt:{slug}"] = items or []
        for slug, items in zip(tax_slugs, tax_results):
            dynamic[f"tax:{slug}"] = items or []

        await storage.set_content_cache(
            ctx, site_id,
            posts=posts_data, pages=pages_data, media=media_data,
            comments=comments_data, scheduled=scheduled_data,
            users=users_data, orders=orders_data,
            dynamic=dynamic,
        )

    # Build content map
    content_map = {
        "posts": posts_data, "pages": pages_data, "media": media_data,
        "comments": comments_data, "scheduled": scheduled_data,
        "users": users_data, "orders": orders_data,
    }
    cpt_meta = dynamic.get("_cpt_meta", {})
    tax_meta = dynamic.get("_tax_meta", {})
    for slug in cpt_meta:
        content_map[f"cpt:{slug}"] = dynamic.get(f"cpt:{slug}")
    for slug in tax_meta:
        content_map[f"tax:{slug}"] = dynamic.get(f"tax:{slug}")

    # Server tab: fetch live via SSH (not cached — always fresh on vacation checks)
    if active_tab == "server" and has_ssh:
        return await _render_server_tab(ctx, site_id, name, base_url, ssh_cred,
                                        reachable, ssl_valid, tab_defs)

    items = content_map.get(active_tab)

    # ── Health stats ──
    ssh_stat = ui.Stat(
        label="SSH",
        value="Connected" if has_ssh else "Not set up",
        color="green" if has_ssh else "gray",
        icon="Terminal",
    )
    health_stats = ui.Stats(columns=4, children=[
        ui.Stat(label="Reachable", value="Yes" if reachable else "No",
                color="green" if reachable else "red"),
        ui.Stat(label="Auth",      value="OK" if reachable else "Failed",
                color="green" if reachable else "red"),
        ui.Stat(label="SSL",       value="HTTPS" if ssl_valid else "HTTP",
                color="green" if ssl_valid else "red"),
        ssh_stat,
    ])

    # ── Tab selector ──
    tab_defs = [
        ("Posts", "posts"), ("Pages", "pages"), ("Media", "media"),
        ("Comments", "comments"), ("Scheduled", "scheduled"), ("Users", "users"),
    ]
    if orders_data is not None:
        tab_defs.append(("Orders", "orders"))
    for slug, meta in cpt_meta.items():
        tab_defs.append((meta["name"], f"cpt:{slug}"))
    for slug, meta in tax_meta.items():
        tab_defs.append((meta["name"], f"tax:{slug}"))
    if has_ssh:
        tab_defs.append(("Server", "server"))

    tab_bar = ui.Select(
        options=[{"value": key, "label": label} for label, key in tab_defs],
        value=active_tab,
        param_name="active_tab",
        on_change=ui.Call("__panel__center", view="", site_id=site_id),
    )

    ssh_btn = ui.Button(
        "Remove SSH" if has_ssh else "Add SSH",
        icon="Terminal",
        variant="ghost",
        size="sm",
        on_click=ui.Call("remove_ssh", site_id=site_id) if has_ssh
                 else ui.Call("__panel__center", view="add_ssh", site_id=site_id),
    )

    return ui.Page(title=name, subtitle=base_url, children=[
        health_stats,
        ssh_btn,
        tab_bar,
        _render_content_table(items, active_tab),
    ])


async def _render_server_tab(ctx, site_id, name, base_url, ssh_cred,
                              reachable, ssl_valid, tab_defs):
    """Server tab: runs WP-CLI via SSH and renders diagnostics. Always live, never cached."""
    info = await wp_cli.get_server_info(ssh_cred)

    if "error" in info:
        return ui.Page(title=name, subtitle=base_url, children=[
            ui.Alert(message=f"SSH/WP-CLI error: {info['error']}", type="error"),
            ui.Button("Remove SSH", icon="Terminal", variant="ghost", size="sm",
                      on_click=ui.Call("remove_ssh", site_id=site_id)),
        ])

    updates = info["plugin_updates"] + info["theme_updates"] + (1 if info["core_update"] else 0)

    update_stat = ui.Stat(
        label="Updates",
        value=str(updates) if updates else "All up to date",
        color="red" if updates else "green",
    )

    server_stats = ui.Stats(columns=4, children=[
        ui.Stat(label="WordPress", value=info["wp_version"] or "—", color="blue"),
        ui.Stat(label="PHP",       value=info["php_version"] or "—", color="blue"),
        ui.Stat(label="Database",  value=f"{info['db_size_mb']} MB" if info["db_size_mb"] else "—", color="blue"),
        ui.Stat(label="Cron Jobs", value=str(info["cron_count"]), color="blue"),
    ])

    rows = [
        {"check": "WordPress core",   "status": f"Update to {info['core_update_version']} available" if info["core_update"] else "Up to date",  "action": "⚠️" if info["core_update"] else "✅"},
        {"check": "Plugins",          "status": f"{info['plugin_updates']} update(s) available" if info["plugin_updates"] else "All up to date", "action": "⚠️" if info["plugin_updates"] else "✅"},
        {"check": "Themes",           "status": f"{info['theme_updates']} update(s) available" if info["theme_updates"] else "All up to date",  "action": "⚠️" if info["theme_updates"] else "✅"},
    ]
    update_table = ui.DataTable(
        columns=[
            ui.DataColumn("check",  "Check",  sortable=False),
            ui.DataColumn("status", "Status", sortable=False),
            ui.DataColumn("action", "",       sortable=False),
        ],
        rows=rows,
    )

    tab_bar = ui.Select(
        options=[{"value": key, "label": label} for label, key in tab_defs],
        value="server",
        param_name="active_tab",
        on_change=ui.Call("__panel__center", view="", site_id=site_id),
    )
    ssh_btn = ui.Button("Remove SSH", icon="Terminal", variant="ghost", size="sm",
                        on_click=ui.Call("remove_ssh", site_id=site_id))
    health_stats = ui.Stats(columns=4, children=[
        ui.Stat(label="Reachable", value="Yes" if reachable else "No",
                color="green" if reachable else "red"),
        ui.Stat(label="Auth",      value="OK" if reachable else "Failed",
                color="green" if reachable else "red"),
        ui.Stat(label="SSL",       value="HTTPS" if ssl_valid else "HTTP",
                color="green" if ssl_valid else "red"),
        ui.Stat(label="SSH", value="Connected", color="green", icon="Terminal"),
    ])

    return ui.Page(title=name, subtitle=base_url, children=[
        health_stats,
        ssh_btn,
        tab_bar,
        update_stat,
        server_stats,
        update_table,
    ])
