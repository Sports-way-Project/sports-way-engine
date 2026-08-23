import re

from fastapi import APIRouter, Header, HTTPException, Query, Response

from app.core.dolibarr_client import dolibarr_client
from app.core.integration_settings import get_dolibarr_config
from app.core.supabase_client import SupabaseConfigError
from app.models.schemas import OrderDetail, OrderListItem, OrderSyncRequest
from app.routers.admin import _require_admin
from app.services import orders_service

router = APIRouter(prefix="/orders", tags=["orders"])

DOCUMENT_KINDS = {
    "order": "commande",
    "invoice": "facture",
    "shipment": "expedition",
}

# There's no separate "Livraison" (delivery receipt) module in this Dolibarr
# install — htdocs/livraison/ doesn't exist. A shipment (expedition) IS the
# delivery record here: it gets its own PDF once validated, and "classify
# closed" on it is literally what our own trigger treats as "Delivered" (see
# the trigger class). So "shipment PDFs" below cover delivery receipts too;
# there's no third, separate document type to fetch.


async def _require_sync_secret(x_sync_secret: str | None) -> None:
    """Gate for the one write path this API exposes. Read endpoints below
    are intentionally open (same trust level as the Dolibarr product-search
    endpoints) — only writes need the shared secret, since only writes can
    change what the website shows customers. The expected secret can come
    from a superadmin's Supabase override (AdminIntegrationSettings) or the
    .env default — see get_dolibarr_config."""
    config = await get_dolibarr_config()
    if not config["sync_secret"] or x_sync_secret != config["sync_secret"]:
        raise HTTPException(status_code=401, detail="Invalid or missing X-Sync-Secret")


@router.get("", response_model=list[OrderListItem])
async def list_orders(unlinked: bool = Query(False)):
    """Used by the Dolibarr website-orders module's list page and its
    incoming-orders badge count."""
    try:
        return await orders_service.list_orders(unlinked_only=unlinked)
    except SupabaseConfigError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/{order_id}", response_model=OrderDetail)
async def get_order(order_id: str):
    try:
        order = await orders_service.get_order(order_id)
    except SupabaseConfigError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


@router.get("/{order_id}/dolibarr-status")
async def dolibarr_status(order_id: str, authorization: str | None = Header(None)):
    """Whether the Dolibarr order/invoice this website order links to still
    actually exists — dolibarr_order_id can outlive the real commande (it
    used to never get cleared on delete; the trigger class fixed that going
    forward, but older rows can still be stale), so the admin UI checks
    live instead of assuming a stored id is still valid."""
    await _require_admin(authorization)
    try:
        order = await orders_service.get_order(order_id)
    except SupabaseConfigError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    async def _fetch(fetch_fn, dolibarr_id):
        """Returns (exists, ref) — ref is Dolibarr's human ref (e.g. SO2607-0080),
        nicer for the admin to see than the raw internal id."""
        if not dolibarr_id:
            return None, None
        try:
            obj = await fetch_fn(dolibarr_id)
            return True, obj.get("ref")
        except Exception:
            return False, None

    order_exists, order_ref = await _fetch(dolibarr_client.get_order, order.dolibarr_order_id)
    invoice_exists, invoice_ref = await _fetch(dolibarr_client.get_invoice, order.dolibarr_invoice_id)

    # DOLIBARR_API_URL points at .../htdocs/api/index.php — strip that off to
    # get the browsable Dolibarr base URL for building admin-facing links
    # (the admin needs to actually click through to the native order/invoice
    # card, same as the Dolibarr-side list.php already links back the other way).
    config = await get_dolibarr_config()
    dolibarr_base_url = re.sub(r"/api/index\.php/?$", "", config["api_url"])

    return {
        "orderExists": order_exists,
        "orderRef": order_ref,
        "orderUrl": f"{dolibarr_base_url}/commande/card.php?id={order.dolibarr_order_id}" if order.dolibarr_order_id else None,
        "invoiceExists": invoice_exists,
        "invoiceRef": invoice_ref,
        "invoiceUrl": f"{dolibarr_base_url}/compta/facture/card.php?id={order.dolibarr_invoice_id}" if order.dolibarr_invoice_id else None,
    }


def _extract_shipment_ids(order_obj: dict) -> list[int]:
    """linkedObjectsIds on a Dolibarr commande is an associative array keyed
    by element type (e.g. {'shipping': {123: 123, 124: 124}}) — pulls out
    just the shipment ids, tolerating either a dict-of-ids or list-of-ids
    shape since the REST API's JSON encoding of that PHP array can go
    either way depending on whether the keys are sequential."""
    linked = order_obj.get("linkedObjectsIds") or {}
    shipping = linked.get("shipping") if isinstance(linked, dict) else None
    if not shipping:
        return []
    if isinstance(shipping, dict):
        return [int(v) for v in shipping.values()]
    if isinstance(shipping, list):
        return [int(v) for v in shipping]
    return []


@router.get("/{order_id}/documents")
async def list_documents(order_id: str, authorization: str | None = Header(None)):
    """Lists which Dolibarr PDFs are available for this website order — the
    order itself, its invoice, and one entry per shipment (there's no
    separate "delivery receipt" object in this Dolibarr install; a validated/
    closed shipment IS the delivery record — see DOCUMENT_KINDS above).
    Requires an admin session — unlike the other GET endpoints on this
    router, this one is reachable directly from the browser and order IDs
    are guessable (SWWO-YYMM#####), so it can't be left open like the
    Dolibarr-only endpoints above."""
    await _require_admin(authorization)
    try:
        order = await orders_service.get_order(order_id)
    except SupabaseConfigError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    if not order.dolibarr_order_id:
        return {"documents": [], "orderDeleted": False}

    # Confirm the commande actually still exists before offering ANY PDFs —
    # a deleted order has nothing left to show a document for, and this also
    # gives us the linked shipment ids in one call instead of a second round trip.
    try:
        order_obj = await dolibarr_client.get_order(order.dolibarr_order_id)
    except Exception:
        return {"documents": [], "orderDeleted": True}

    available = [{"kind": "order", "label": "Dolibarr Order", "url": f"/orders/{order_id}/documents/order/{order.dolibarr_order_id}"}]

    if order.dolibarr_invoice_id:
        available.append({"kind": "invoice", "label": "Invoice", "url": f"/orders/{order_id}/documents/invoice/{order.dolibarr_invoice_id}"})

    for shipment_id in _extract_shipment_ids(order_obj):
        available.append({
            "kind": "shipment",
            "label": f"Shipment #{shipment_id}",
            "url": f"/orders/{order_id}/documents/shipment/{shipment_id}",
        })

    return {"documents": available, "orderDeleted": False}


@router.get("/{order_id}/documents/{kind}/{dolibarr_id}")
async def download_document(order_id: str, kind: str, dolibarr_id: str, authorization: str | None = Header(None)):
    """Streams the actual PDF back to the browser. Fetches the Dolibarr
    object first to resolve its `ref` (documents are stored on disk/served
    by Dolibarr keyed by ref, not by internal numeric id). dolibarr_id is
    taken from the caller rather than re-derived from the order record so
    shipments (which aren't stored on the website order at all — there can
    be several) work the same way as order/invoice."""
    await _require_admin(authorization)
    if kind not in DOCUMENT_KINDS:
        raise HTTPException(status_code=400, detail="kind must be 'order', 'invoice', or 'shipment'")

    try:
        order = await orders_service.get_order(order_id)
    except SupabaseConfigError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    modulepart = DOCUMENT_KINDS[kind]
    try:
        if kind == "order":
            obj = await dolibarr_client.get_order(dolibarr_id)
        elif kind == "invoice":
            obj = await dolibarr_client.get_invoice(dolibarr_id)
        else:
            obj = await dolibarr_client.get_shipment(dolibarr_id)
        ref = obj.get("ref")
        if not ref:
            raise HTTPException(status_code=502, detail=f"Dolibarr {kind} has no ref")
        pdf_bytes = await dolibarr_client.download_document(modulepart, ref)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to reach Dolibarr: {exc}") from exc

    if not pdf_bytes:
        raise HTTPException(
            status_code=404,
            detail=f"PDF not generated in Dolibarr yet — open the {kind} in Dolibarr once to generate it, then try again.",
        )

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{ref}.pdf"'},
    )


@router.post("/{order_id}/sync", response_model=OrderDetail)
async def sync_order(order_id: str, payload: OrderSyncRequest, x_sync_secret: str | None = Header(None)):
    """Called by the Dolibarr module right after creating a Dolibarr order
    (to store dolibarr_order_id) and by its trigger class on order/shipment/
    invoice status changes (ORDER_VALIDATE, SHIPPING_VALIDATE, ORDER_CANCEL,
    BILL_VALIDATE) — or manually, when staff override the website status
    directly from Dolibarr instead of going through the native workflow."""
    await _require_sync_secret(x_sync_secret)
    try:
        order = await orders_service.sync_order(order_id, payload.model_dump())
    except SupabaseConfigError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order
