from pydantic import BaseModel, Field
from imperal_sdk import sdl

VNEXT = "requires companion plugin (vNext)"


class SiteIdParams(BaseModel):
    site_id: str = Field(description="Site id from a previous list_sites call — never invent it")


class ListContentParams(BaseModel):
    site_id: str = Field(description="Site id from a previous list_sites call — never invent it")
    limit: int = Field(default=20, ge=1, le=100, description="Max items to return, 1-100")
    search: str | None = Field(default=None, description="Optional search term")


class ListMediaParams(BaseModel):
    site_id: str = Field(description="Site id from a previous list_sites call — never invent it")
    limit: int = Field(default=20, ge=1, le=100, description="Max items to return, 1-100")


class _NoParams(BaseModel):
    pass


# SDL entities. sdl.Entity already provides: id, title, kind, subtitle, description, status, url.
class Site(sdl.Entity):
    username: str = ""
    last_checked: str | None = None


class Post(sdl.Entity):
    link: str = ""
    date: str | None = None


class Page(sdl.Entity):
    link: str = ""
    date: str | None = None


class MediaItem(sdl.Entity):
    mime_type: str = ""


class SiteHealth(sdl.Entity):
    reachable: bool = False
    auth_ok: bool = False
    ssl_valid: bool = False
    content_counts: dict = Field(default_factory=dict)
    plugin_updates_available: str = VNEXT
    php_version: str = VNEXT
