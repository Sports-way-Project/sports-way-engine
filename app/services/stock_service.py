from app.core.dolibarr_client import dolibarr_client
from app.models.schemas import DolibarrProductResult, StockResult

MODULEPART = "produit"


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


async def get_live_stock(product_id: int, dolibarr_id: int, barcode: str = "", art_no: str = "") -> StockResult:
    """Resolves the Dolibarr product the same way the swwebsiteproducts
    module links them (see supabaseclient.class.php::linkAndUpsertProduct):
    barcode first, then art_no, and dolibarr_id only as the last resort —
    that priority is what lets this survive the linked Dolibarr product
    having been deleted and recreated (new id, same barcode/art_no)."""
    dolibarr_product = None
    if barcode:
        dolibarr_product = await dolibarr_client.get_product_by_barcode(barcode)
    if dolibarr_product is None and art_no:
        dolibarr_product = await dolibarr_client.get_product_by_art_no(art_no)
    if dolibarr_product is None:
        dolibarr_product = await dolibarr_client.get_product(dolibarr_id)

    stock_count = _extract_stock_count(dolibarr_product)
    resolved_id = int(dolibarr_product.get("id", dolibarr_id))
    return StockResult(
        product_id=product_id,
        dolibarr_id=resolved_id,
        stock_count=stock_count,
        stock_status=_stock_status_from_count(stock_count),
    )


async def _list_product_photo_files(ref: str) -> list[dict]:
    """Photo file entries from Dolibarr's own /documents listing (over
    HTTP), not the local filesystem — see DolibarrClient.list_documents for
    why this replaced the old DOLIBARR_DOCUMENTS_ROOT approach.

    Dolibarr's real response uses `filename` (not `name`) for the file's
    basename, `filepath` for its subfolder relative to the modulepart root
    (e.g. "produit/<ref>"), and a `content-type` field that's more reliable
    than guessing from the extension — confirmed against a live instance."""
    if not ref:
        return []
    docs = await dolibarr_client.list_documents(MODULEPART, ref)
    photos = [
        d for d in docs
        if isinstance(d, dict) and str(d.get("content-type", "")).startswith("image/")
    ]
    photos.sort(key=lambda d: d.get("filename", ""))
    return photos


def _document_original_file(ref: str, doc: dict) -> str:
    """Builds the `original_file` path /documents/download expects, from a
    /documents listing entry: strip the modulepart prefix off `filepath` to
    get the subfolder relative to it, then join with `filename`."""
    filename = doc.get("filename", "")
    filepath = (doc.get("filepath") or "").strip("/")
    prefix = f"{MODULEPART}/"
    subfolder = filepath[len(prefix):] if filepath.startswith(prefix) else ref
    return f"{subfolder}/{filename}"


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
    content = await dolibarr_client.download_document_file(MODULEPART, original_file)
    if not content:
        return None
    return content, doc.get("content-type") or "image/jpeg"
