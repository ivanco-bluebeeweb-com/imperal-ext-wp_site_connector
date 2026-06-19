import json

SITES_COLLECTION = "sites"
CREDS_COLLECTION = "creds"


# ── Site records ──────────────────────────────────────────────────────────────

async def _find_doc(ctx, collection, site_id):
    page = await ctx.store.query(collection, limit=100)
    for doc in page.data:
        if doc.data.get("site_id") == site_id or doc.data.get("id") == site_id:
            return doc
    return None


async def list_site_records(ctx):
    page = await ctx.store.query(SITES_COLLECTION, limit=100)
    return [doc.data for doc in page.data]


async def get_site_record(ctx, site_id):
    doc = await _find_doc(ctx, SITES_COLLECTION, site_id)
    return doc.data if doc else None


async def save_site_record(ctx, record):
    doc = await _find_doc(ctx, SITES_COLLECTION, record["id"])
    if doc:
        await ctx.store.update(SITES_COLLECTION, doc.id, record)
    else:
        await ctx.store.create(SITES_COLLECTION, record)


async def delete_site_record(ctx, site_id):
    doc = await _find_doc(ctx, SITES_COLLECTION, site_id)
    if doc:
        await ctx.store.delete(SITES_COLLECTION, doc.id)


# ── Credentials (stored in ctx.store — vault provisioning not required) ───────

async def get_credential(ctx, site_id):
    doc = await _find_doc(ctx, CREDS_COLLECTION, site_id)
    return doc.data.get("password") if doc else None


async def set_credential(ctx, site_id, app_password):
    doc = await _find_doc(ctx, CREDS_COLLECTION, site_id)
    if doc:
        await ctx.store.update(CREDS_COLLECTION, doc.id,
                               {"site_id": site_id, "password": app_password})
    else:
        await ctx.store.create(CREDS_COLLECTION,
                               {"site_id": site_id, "password": app_password})


async def delete_credential(ctx, site_id):
    doc = await _find_doc(ctx, CREDS_COLLECTION, site_id)
    if doc:
        await ctx.store.delete(CREDS_COLLECTION, doc.id)


# ── Content cache (posts/pages/media fetched once, tabs switch from cache) ────

CACHE_COLLECTION = "wp_cache"


async def get_content_cache(ctx, site_id):
    doc = await _find_doc(ctx, CACHE_COLLECTION, site_id)
    return doc.data if doc else None


async def set_content_cache(ctx, site_id, posts=None, pages=None, media=None,
                            comments=None, scheduled=None, users=None, orders=None):
    data = {
        "site_id":   site_id,
        "posts":     posts or [],
        "pages":     pages or [],
        "media":     media or [],
        "comments":  comments or [],
        "scheduled": scheduled or [],
        "users":     users or [],
        "orders":    orders,  # None = WC not installed; [] = installed but no orders
    }
    doc = await _find_doc(ctx, CACHE_COLLECTION, site_id)
    if doc:
        await ctx.store.update(CACHE_COLLECTION, doc.id, data)
    else:
        await ctx.store.create(CACHE_COLLECTION, data)


async def clear_content_cache(ctx, site_id):
    doc = await _find_doc(ctx, CACHE_COLLECTION, site_id)
    if doc:
        await ctx.store.delete(CACHE_COLLECTION, doc.id)
