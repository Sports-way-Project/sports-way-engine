from fastapi import APIRouter, Header, HTTPException, Query, Response

from app.core.integration_settings import get_dolibarr_config
from app.core.supabase_client import SupabaseConfigError
from app.models.schemas import DolibarrProductResult, ProductSyncRequest
from app.services import products_service, stock_service

router = APIRouter(prefix="/products", tags=["products"])


async def _require_sync_secret(x_sync_secret: str | None) -> None:
    """Same gate as /orders' sync endpoint (see app/routers/orders.py) —
    only the write path needs the shared secret."""
    config = await get_dolibarr_config()
    if not config["sync_secret"] or x_sync_secret != config["sync_secret"]:
        raise HTTPException(status_code=401, detail="Invalid or missing X-Sync-Secret")


@router.get("/search", response_model=list[DolibarrProductResult])
async def search_products(q: str = Query(..., min_length=1)):
    """Search Dolibarr products by ref or label, used by the admin link picker."""
    return await stock_service.search_dolibarr_products(q)


@router.get("/dolibarr/all", response_model=list[DolibarrProductResult])
async def list_all_products():
    """Every Dolibarr product, used by the admin product-mapping page to diff
    against Supabase products."""
    return await stock_service.list_all_dolibarr_products()


@router.get("/{dolibarr_id}/photos")
async def get_product_photos(dolibarr_id: int):
    """Count of photos available for this Dolibarr product, used by the admin
    product-mapping page to know how many /photo?index=N calls to make."""
    count = await stock_service.get_product_photo_count(dolibarr_id)
    return {"count": count}


@router.get("/{dolibarr_id}/photo")
async def get_product_photo(dolibarr_id: int, index: int = 0):
    """Product photo fetched live from Dolibarr, used as a thumbnail in the
    admin search results (index 0) or copied into the gallery on import.
    404s if the product has no uploaded photo at that index."""
    result = await stock_service.get_product_photo_bytes(dolibarr_id, index)
    if not result:
        raise HTTPException(status_code=404, detail="No photo found for this product")
    content, content_type = result
    return Response(content=content, media_type=content_type)


@router.post("/{dolibarr_id}/sync")
async def sync_product(dolibarr_id: int, payload: ProductSyncRequest, x_sync_secret: str | None = Header(None)):
    """Called by the Dolibarr website-products module's Catalog & Website tab
    on save — upserts the matching Supabase `products` row (keyed on
    dolibarr_id) with whatever changed."""
    await _require_sync_secret(x_sync_secret)
    try:
        product = await products_service.sync_product(dolibarr_id, payload)
    except SupabaseConfigError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return product or {}


@router.get("/settings/categories")
async def get_custom_categories():
    """Proxies Supabase's site_settings.custom_categories — used by the
    Dolibarr module's CategorySync class to mirror them into real native
    llx_categorie rows, and by the Catalog & Website tab's checkbox list."""
    try:
        return await products_service.get_custom_categories()
    except SupabaseConfigError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/settings/brands")
async def get_product_brands():
    """Proxies Supabase's site_settings.product_brands for the Catalog &
    Website tab's brand dropdown."""
    try:
        return await products_service.get_product_brands()
    except SupabaseConfigError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
