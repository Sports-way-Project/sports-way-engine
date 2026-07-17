import mimetypes

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


async def _list_product_photo_files(ref: str) -> list[dict]:
    """Photo file entries from Dolibarr's own /documents listing (over
    HTTP), not the local filesystem — see DolibarrClient.list_documents for
    why this replaced the old DOLIBARR_DOCUMENTS_ROOT approach."""
    if not ref:
        return []
    docs = await dolibarr_client.list_documents("produit", ref)
    photos = [
        d for d in docs
        if isinstance(d, dict) and str(d.get("name", "")).lower().endswith(IMAGE_EXTENSIONS)
    ]
    photos.sort(key=lambda d: d.get("name", ""))
    return photos


def _document_original_file(ref: str, doc: dict) -> str:
    """Builds the `original_file` path /documents/download expects, from a
    /documents listing entry. Dolibarr's listing includes the file's
    relative subdirectory (photos are usually under <ref>/photos/) — fall
    back to just <ref>/<name> if that field isn't present."""
    name = doc.get("name", "")
    relpath = (doc.get("relpath") or doc.get("path") or "").strip("/")
    return f"{ref}/{relpath}/{name}" if relpath else f"{ref}/{name}"


async def get_product_photo_count(dolibarr_id: int) -> int:
    dolibarr_product = await dolibarr_client.get_product(dolibarr_id, include_stock=False)
    photos = await _list_product_photo_files(dolibarr_product.get("ref", ""))
    return len(photos)


async def get_product_photo_bytes(dolibarr_id: int, index: int = 0) -> tuple[bytes, str] | None:
    """Returns (content, content_type) for one product photo, fetched live
    from Dolibarr — or None if there's no photo at that index."""
    dolibarr_product = await dolibarr_client.get_product(dolibarr_id, include_stock=False)
    ref = dolibarr_product.get("ref", "")
    photos = await _list_product_photo_files(ref)
    if index < 0 or index >= len(photos):
        return None
    doc = photos[index]
    original_file = _document_original_file(ref, doc)
    content = await dolibarr_client.download_document_file("produit", original_file)
    if not content:
        return None
    content_type = mimetypes.guess_type(doc.get("name", ""))[0] or "image/jpeg"
    return content, content_type
