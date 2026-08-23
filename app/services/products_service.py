from app.core.supabase_client import supabase_client
from app.models.schemas import ProductSyncRequest


async def sync_product(dolibarr_id: int, payload: ProductSyncRequest) -> dict | None:
    """Upserts a Supabase `products` row from what the Catalog & Website tab
    just saved in Dolibarr. Only writes columns that actually exist on
    `products` today (see frontend/database/schema.sql) — art_no/name_ar/color
    aren't website-facing columns yet, so they stay Dolibarr-only (native
    extrafields) until/unless a future migration adds them here. `price` is
    never touched: that's the storefront sell price, managed separately from
    this Dolibarr-side cost/catalog sync."""
    patch: dict = {}
    if payload.name is not None:
        patch["name"] = payload.name
    if payload.dolibarr_ref is not None:
        patch["dolibarr_ref"] = payload.dolibarr_ref
    if payload.categories is not None:
        patch["categories"] = payload.categories
        # `category` (singular) is NOT NULL — keep it populated with the
        # first selected category so a brand-new row (first-ever sync for
        # this product) doesn't fail the constraint.
        patch["category"] = payload.categories[0] if payload.categories else ""
    if payload.brand is not None:
        patch["brand"] = payload.brand
    if payload.show_on_website is not None:
        patch["show_on_website"] = payload.show_on_website

    if not patch:
        return None
    return await supabase_client.upsert_product(dolibarr_id, patch)


async def get_custom_categories() -> list:
    """Proxies Supabase's site_settings.custom_categories for Dolibarr's
    CategorySync class, which mirrors them into real native llx_categorie
    rows, and for the Catalog & Website tab's category checkbox list."""
    value = await supabase_client.get_site_setting("custom_categories")
    return value or []


async def get_product_brands() -> list:
    """Proxies Supabase's site_settings.product_brands for the Catalog &
    Website tab's brand dropdown."""
    value = await supabase_client.get_site_setting("product_brands")
    return value or []
