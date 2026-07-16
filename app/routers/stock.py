from fastapi import APIRouter

from app.models.schemas import StockResult
from app.services import stock_service

router = APIRouter(prefix="/stock", tags=["stock"])


@router.get("/{product_id}/{dolibarr_id}", response_model=StockResult)
async def get_live_stock(product_id: int, dolibarr_id: int):
    """Live stock check: called by the website product card/page and by the
    admin stocks page, which does its own comparison and Supabase write."""
    return await stock_service.get_live_stock(product_id, dolibarr_id)
