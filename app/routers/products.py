from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from app.models.schemas import DolibarrProductResult
from app.services import stock_service

router = APIRouter(prefix="/products", tags=["products"])


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
    photo_paths = await stock_service.get_product_photo_paths(dolibarr_id)
    return {"count": len(photo_paths)}


@router.get("/{dolibarr_id}/photo")
async def get_product_photo(dolibarr_id: int, index: int = 0):
    """Product photo from Dolibarr's document store, used as a thumbnail in the
    admin search results (index 0) or copied into the gallery on import.
    404s if the product has no uploaded photo at that index."""
    photo_paths = await stock_service.get_product_photo_paths(dolibarr_id)
    if index < 0 or index >= len(photo_paths):
        raise HTTPException(status_code=404, detail="No photo found for this product")
    return FileResponse(photo_paths[index])
