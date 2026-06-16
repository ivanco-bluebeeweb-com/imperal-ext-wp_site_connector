from imperal_sdk.testing import MockContext, MockSecretStore
import app  # noqa: F401
import panels
import storage


async def test_dashboard_renders_node_not_none():
    ctx = MockContext()
    await storage.save_site_record(ctx, {"id": "x-com", "name": "X", "url": "https://x.com", "status": "connected"})
    node = await panels.dashboard(ctx)
    assert node is not None and "x-com" in str(node)


async def test_detail_returns_empty_when_no_site():
    ctx = MockContext()
    node = await panels.detail(ctx, site_id=None)
    assert node is not None  # must be ui.Empty(), never None


async def test_detail_renders_site_content():
    ctx = MockContext()
    ctx.secrets = MockSecretStore({})
    await storage.save_site_record(ctx, {"id": "x-com", "name": "X", "url": "https://x.com", "username": "admin", "status": "connected"})
    await storage.set_credential(ctx, "x-com", "pw")
    ctx.http.mock_get("https://x.com/wp-json/wp/v2/posts", [{"id": 1, "title": {"rendered": "Hello"}, "status": "publish"}], 200)
    ctx.http.mock_get("https://x.com/wp-json/wp/v2/pages", [], 200)
    ctx.http.mock_get("https://x.com/wp-json/wp/v2/media", [], 200)
    node = await panels.detail(ctx, site_id="x-com")
    assert "Hello" in str(node)


async def test_connect_form_has_password_field():
    ctx = MockContext()
    node = await panels.connect_form(ctx)
    s = str(node)
    assert "app_password" in s and "'type': 'password'" in s
