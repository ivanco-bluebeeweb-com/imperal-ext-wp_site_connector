from imperal_sdk.testing import MockContext, MockSecretStore
import app  # noqa: F401
import panels
import storage


# ── overview ────────────────────────────────────────────────────────────────

async def test_overview_empty_no_sites():
    ctx = MockContext()
    node = await panels.overview(ctx)
    s = str(node)
    assert "No sites connected" in s or "Connect New Site" in s


async def test_overview_renders_site_cards():
    ctx = MockContext()
    ctx.secrets = MockSecretStore({})
    await storage.save_site_record(ctx, {"id": "a-com", "name": "Alpha", "url": "https://a.com", "status": "connected"})
    await storage.save_site_record(ctx, {"id": "b-com", "name": "Beta",  "url": "https://b.com", "status": "error"})
    node = await panels.overview(ctx)
    s = str(node)
    assert "Alpha" in s
    assert "Beta" in s
    assert "Grid" in s  # ui.Grid(columns=2) must be used, not manual Stack pairs


async def test_overview_search_filter():
    ctx = MockContext()
    ctx.secrets = MockSecretStore({})
    await storage.save_site_record(ctx, {"id": "a-com", "name": "Alpha", "url": "https://a.com", "status": "connected"})
    await storage.save_site_record(ctx, {"id": "b-com", "name": "Beta",  "url": "https://b.com", "status": "connected"})
    node = await panels.overview(ctx, search="Alpha")
    s = str(node)
    assert "Alpha" in s
    assert "Beta" not in s


async def test_overview_status_filter_connected():
    ctx = MockContext()
    ctx.secrets = MockSecretStore({})
    await storage.save_site_record(ctx, {"id": "a-com", "name": "Alpha", "url": "https://a.com", "status": "connected"})
    await storage.save_site_record(ctx, {"id": "b-com", "name": "Beta",  "url": "https://b.com", "status": "error"})
    node = await panels.overview(ctx, status_filter="connected")
    s = str(node)
    assert "Alpha" in s
    assert "Beta" not in s


async def test_overview_status_filter_error():
    ctx = MockContext()
    ctx.secrets = MockSecretStore({})
    await storage.save_site_record(ctx, {"id": "a-com", "name": "Alpha", "url": "https://a.com", "status": "connected"})
    await storage.save_site_record(ctx, {"id": "b-com", "name": "Beta",  "url": "https://b.com", "status": "error"})
    node = await panels.overview(ctx, status_filter="error")
    s = str(node)
    assert "Beta" in s
    assert "Alpha" not in s


async def test_overview_no_match_shows_empty():
    ctx = MockContext()
    ctx.secrets = MockSecretStore({})
    await storage.save_site_record(ctx, {"id": "a-com", "name": "Alpha", "url": "https://a.com", "status": "connected"})
    node = await panels.overview(ctx, search="zzz")
    s = str(node)
    assert "match" in s.lower() or "No sites" in s


async def test_overview_site_count_in_header():
    ctx = MockContext()
    ctx.secrets = MockSecretStore({})
    await storage.save_site_record(ctx, {"id": "a-com", "name": "Alpha", "url": "https://a.com", "status": "connected"})
    await storage.save_site_record(ctx, {"id": "b-com", "name": "Beta",  "url": "https://b.com", "status": "connected"})
    node = await panels.overview(ctx)
    s = str(node)
    assert "2" in s  # total count in header


# ── connect_form ─────────────────────────────────────────────────────────────

async def test_connect_form_has_password_field():
    ctx = MockContext()
    node = await panels.connect_form(ctx)
    s = str(node)
    assert "app_password" in s and "'type': 'password'" in s


# ── detail ───────────────────────────────────────────────────────────────────

async def test_detail_returns_empty_when_no_site():
    ctx = MockContext()
    node = await panels.detail(ctx, site_id=None)
    assert node is not None


async def test_detail_has_back_button():
    ctx = MockContext()
    ctx.secrets = MockSecretStore({})
    await storage.save_site_record(ctx, {"id": "x-com", "name": "X", "url": "https://x.com", "username": "admin", "status": "connected"})
    await storage.set_credential(ctx, "x-com", "pw")
    ctx.http.mock_get("https://x.com/wp-json/wp/v2/users/me", {"name": "Admin"}, 200)
    ctx.http.mock_get("https://x.com/wp-json/wp/v2/posts", [], 200)
    ctx.http.mock_get("https://x.com/wp-json/wp/v2/pages", [], 200)
    ctx.http.mock_get("https://x.com/wp-json/wp/v2/media", [], 200)
    node = await panels.detail(ctx, site_id="x-com")
    s = str(node)
    assert "__panel__overview" in s  # back button points to overview


async def test_detail_renders_site_content():
    ctx = MockContext()
    ctx.secrets = MockSecretStore({})
    await storage.save_site_record(ctx, {"id": "x-com", "name": "X", "url": "https://x.com", "username": "admin", "status": "connected"})
    await storage.set_credential(ctx, "x-com", "pw")
    ctx.http.mock_get("https://x.com/wp-json/wp/v2/users/me", {"name": "Admin"}, 200)
    ctx.http.mock_get("https://x.com/wp-json/wp/v2/posts",
                      [{"id": 1, "title": {"rendered": "Hello"}, "status": "publish", "date": "2026-06-15T00:00:00"}], 200)
    ctx.http.mock_get("https://x.com/wp-json/wp/v2/pages", [], 200)
    ctx.http.mock_get("https://x.com/wp-json/wp/v2/media", [], 200)
    node = await panels.detail(ctx, site_id="x-com")
    s = str(node)
    assert "Page" in s        # ui.Page wrapper
    assert "Stats" in s       # ui.Stats for health + counts
    assert "Reachable" in s   # Stat label
    assert "DataTable" in s   # ui.DataTable for content tabs
    assert "Hello" in s       # post title appears in table rows


async def test_overview_card_calls_refresh_site():
    ctx = MockContext()
    ctx.secrets = MockSecretStore({})
    await storage.save_site_record(ctx, {"id": "a-com", "name": "Alpha",
                                         "url": "https://a.com", "status": "connected"})
    node = await panels.overview(ctx)
    s = str(node)
    assert "refresh_site" in s


async def test_overview_card_has_remove_menu():
    ctx = MockContext()
    ctx.secrets = MockSecretStore({})
    await storage.save_site_record(ctx, {"id": "a-com", "name": "Alpha",
                                         "url": "https://a.com", "status": "connected"})
    node = await panels.overview(ctx)
    s = str(node)
    assert "forget_site" in s


async def test_overview_header_uses_heading_variant():
    ctx = MockContext()
    node = await panels.overview(ctx)
    s = str(node)
    assert "heading" in s


async def test_overview_filter_bar_has_status_select():
    ctx = MockContext()
    node = await panels.overview(ctx)
    s = str(node)
    assert "status_filter" in s
