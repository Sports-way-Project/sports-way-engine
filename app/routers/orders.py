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
}


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


@router.get("/{order_id}/documents")
async def list_documents(order_id: str, authorization: str | None = Header(None)):
    """Lists which Dolibarr PDFs (order/invoice) are available for this
    website order, for the admin order-detail view. Requires an admin
    session — unlike the other GET endpoints on this router, this one is
    reachable directly from the browser and order IDs are guessable
    (SWWO-YYMM#####), so it can't be left open like the Dolibarr-only
    endpoints above."""
    await _require_admin(authorization)
    try:
        order = await orders_service.get_order(order_id)
    except SupabaseConfigError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    available = []
    if order.dolibarr_order_id:
        available.append({"kind": "order", "label": "Dolibarr Order", "url": f"/orders/{order_id}/documents/order"})
    if order.dolibarr_invoice_id:
        available.append({"kind": "invoice", "label": "Invoice", "url": f"/orders/{order_id}/documents/invoice"})
    return {"documents": available}


@router.get("/{order_id}/documents/{kind}")
async def download_document(order_id: str, kind: str, authorization: str | None = Header(None)):
    """Streams the actual PDF back to the browser. Fetches the Dolibarr
    object first to resolve its `ref` (documents are stored on disk/served
    by Dolibarr keyed by ref, not by internal numeric id)."""
    await _require_admin(authorization)
    if kind not in DOCUMENT_KINDS:
        raise HTTPException(status_code=400, detail="kind must be 'order' or 'invoice'")

    try:
        order = await orders_service.get_order(order_id)
    except SupabaseConfigError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    dolibarr_id = order.dolibarr_order_id if kind == "order" else order.dolibarr_invoice_id
    if not dolibarr_id:
        raise HTTPException(status_code=404, detail=f"This order has no linked Dolibarr {kind} yet")

    modulepart = DOCUMENT_KINDS[kind]
    try:
        obj = await dolibarr_client.get_order(dolibarr_id) if kind == "order" else await dolibarr_client.get_invoice(dolibarr_id)
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
