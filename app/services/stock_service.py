from pathlib import Path

from app.core.config import settings
from app.core.dolibarr_client import dolibarr_client
from app.models.schemas import DolibarrProductResult, StockResult

IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp", ".gif")


def _stock_status_from_count(stock_count: float) -> str:
    return "instock" if stock_count > 0 else "outofstock"


def _extract_stock_count(dolibarr_product: dict) -> int:
    raw = dolibarr_product.get("stock_reel", 0)
    try:
        return int(float(raw))
    except (TypeError, ValueError):
        return 0


def _extract_price(dolibarr_product: dict) -> float:
    raw = dolibarr_product.get("price_ttc") or dolibarr_product.get("price") or 0
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 0.0


def _to_result(item: dict) -> DolibarrProductResult:
    stock_count = _extract_stock_count(item)
    return DolibarrProductResult(
        dolibarr_id=int(item["id"]),
        ref=item.get("ref", ""),
        label=item.get("label", ""),
        stock_count=stock_count,
        stock_status=_stock_status_from_count(stock_count),
        price=_extract_price(item),
        description=item.get("description", "") or "",
    )


async def search_dolibarr_products(query: str) -> list[DolibarrProductResult]:
    raw_results = await dolibarr_client.search_products(query)
    return [_to_result(item) for item in raw_results]


async def list_all_dolibarr_products() -> list[DolibarrProductResult]:
    results = []
    page = 0
    limit = 100
    while True:
        raw_results = await dolibarr_client.list_products(page=page, limit=limit)
        if not raw_results:
            break
        results.extend(_to_result(item) for item in raw_results)
        if len(raw_results) < limit:
            break
        page += 1
    return results


async def get_live_stock(product_id: int, dolibarr_id: int) -> StockResult:
    dolibarr_product = await dolibarr_client.get_product(dolibarr_id)
    stock_count = _extract_stock_count(dolibarr_product)
    return StockResult(
        product_id=product_id,
        dolibarr_id=dolibarr_id,
        stock_count=stock_count,
        stock_status=_stock_status_from_count(stock_count),
    )


def _find_photo_paths(ref: str) -> list[Path]:
    if not settings.dolibarr_documents_root or not ref:
        return []

    product_dir = Path(settings.dolibarr_documents_root) / "produit" / ref
    for search_dir in (product_dir / "photos", product_dir):
        if not search_dir.is_dir():
            continue
        photos = sorted(
            candidate for candidate in search_dir.iterdir()
            if candidate.is_file() and candidate.suffix.lower() in IMAGE_EXTENSIONS
        )
        if photos:
            return photos
    return []


async def get_product_photo_path(dolibarr_id: int) -> Path | None:
    dolibarr_product = await dolibarr_client.get_product(dolibarr_id, include_stock=False)
    photos = _find_photo_paths(dolibarr_product.get("ref", ""))
    return photos[0] if photos else None


async def get_product_photo_paths(dolibarr_id: int) -> list[Path]:
    dolibarr_product = await dolibarr_client.get_product(dolibarr_id, include_stock=False)
    return _find_photo_paths(dolibarr_product.get("ref", ""))
