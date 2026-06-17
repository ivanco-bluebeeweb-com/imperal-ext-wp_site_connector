from imperal_sdk import Extension, ChatExtension

ext = Extension(
    "wp-site-connector",
    version="0.1.0",
    display_name="WP Site Connector",
    description="Connect WordPress sites by URL and Application Password and read their posts, pages, media, and health.",
    icon="icon.svg",
    actions_explicit=True,
)

chat = ChatExtension(ext, tool_name="wp-site-connector", description="Browse connected WordPress sites")

# Encrypted credential store: one secret holds {site_id: app_password} for all connected sites.
# write_mode="both" lets the connection-form tool write it via ctx.secrets.set().
ext.secret(
    "wp_credentials",
    "JSON map of {site_id: WordPress Application Password} for connected sites.",
    write_mode="both",
    max_bytes=16384,
)(lambda: None)


@ext.health_check
async def health_check(ctx) -> dict:
    """Liveness probe for the extension."""
    return {"status": "ok"}


# Handler modules register their decorators on import (after ext/chat exist).
import handlers_connect  # noqa: E402,F401
import handlers_read  # noqa: E402,F401
import skeleton  # noqa: E402,F401
import panels  # noqa: E402,F401
