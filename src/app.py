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

# Handler modules register their decorators on import (after ext/chat exist).
import handlers_connect  # noqa: E402,F401
import handlers_read  # noqa: E402,F401
