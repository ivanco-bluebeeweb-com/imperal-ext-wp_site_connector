import json

SITES_COLLECTION = "sites"
SECRET_NAME = "wp_credentials"


async def _find_doc(ctx, site_id):
    # ctx.store.create assigns its own doc id, so look our slug up by querying + filtering.
    page = await ctx.store.query(SITES_COLLECTION, limit=100)
    for doc in page.data:
        if doc.data.get("id") == site_id:
            return doc
    return None


async def list_site_records(ctx):
    page = await ctx.store.query(SITES_COLLECTION, limit=100)
    return [doc.data for doc in page.data]


async def get_site_record(ctx, site_id):
    doc = await _find_doc(ctx, site_id)
    return doc.data if doc else None


async def save_site_record(ctx, record):
    doc = await _find_doc(ctx, record["id"])
    if doc:
        await ctx.store.update(SITES_COLLECTION, doc.id, record)
    else:
        await ctx.store.create(SITES_COLLECTION, record)


async def delete_site_record(ctx, site_id):
    doc = await _find_doc(ctx, site_id)
    if doc:
        await ctx.store.delete(SITES_COLLECTION, doc.id)


async def _load_map(ctx):
    raw = await ctx.secrets.get(SECRET_NAME)
    return json.loads(raw) if raw else {}


async def _save_map(ctx, data):
    await ctx.secrets.set(SECRET_NAME, json.dumps(data))


async def get_credential(ctx, site_id):
    return (await _load_map(ctx)).get(site_id)


async def set_credential(ctx, site_id, app_password):
    data = await _load_map(ctx)
    data[site_id] = app_password
    await _save_map(ctx, data)


async def delete_credential(ctx, site_id):
    data = await _load_map(ctx)
    data.pop(site_id, None)
    await _save_map(ctx, data)
