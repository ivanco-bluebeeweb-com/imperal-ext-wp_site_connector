from imperal_sdk import Extension, ChatExtension, ActionResult, sdl
from pydantic import BaseModel

ext = Extension(
    "wp-site-connector",
    version="0.1.0",
    display_name="WP Site Connector",
    description="Connect WordPress sites by URL and Application Password and read their posts, pages, media, and health.",
    icon="icon.svg",
    actions_explicit=True,
)

chat = ChatExtension(ext, tool_name="wp-site-connector", description="Browse connected WordPress sites")


class _PingResult(sdl.Entity):
    pass


class _PingParams(BaseModel):
    pass


@chat.function("ping", description="Health check for the extension.", action_type="read", data_model=_PingResult)
async def ping(ctx, params: _PingParams) -> ActionResult:
    """Return a static ok result to confirm the extension loads."""
    return ActionResult.success(_PingResult(id="ping", title="ok", kind="ping"), summary="ok")


# Handler modules register their decorators on import (after ext/chat exist).
import handlers_connect  # noqa: E402,F401
