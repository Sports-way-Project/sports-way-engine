from fastapi import APIRouter

from app.models.schemas import StockResult
from app.services import stock_service

router = APIRouter(prefix="/stock", tags=["stock"])


@router.get("/{product_id}/{dolibarr_id}", response_model=StockResult)
async def get_live_stock(product_id: int, dolibarr_id: int, barcode: str = "", art_no: str = ""):
    """Live stock check: called by the website product card/page and by the
    admin stocks page, which does its own comparison and Supabase write.
    barcode/art_no are optional — when present, they take priority over
    dolibarr_id for resolving which Dolibarr product to read (see
    stock_service.get_live_stock)."""
    return await stock_service.get_live_stock(product_id, dolibarr_id, barcode, art_no)
