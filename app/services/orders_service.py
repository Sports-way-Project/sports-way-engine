from app.core.supabase_client import supabase_client
from app.models.schemas import OrderDetail, OrderItem, OrderListItem

UNPAID_STATUSES = {"Pending Payment", "Cancelled", "Failed"}


def _derive_paid(status: str, payment_method: str) -> bool:
    """Best-effort only — there's no dedicated payment-received column yet
    (that lands with real payment tracking, e.g. once Sadad is wired up).
    Cash on Delivery is never auto-marked paid since cash isn't collected
    until the courier hands over the order; bank transfer is treated as
    paid once staff move it past "Pending Payment"."""
    if status in UNPAID_STATUSES:
        return False
    return payment_method != "Cash on Delivery"


def _map_item(raw: dict) -> OrderItem:
    return OrderItem(
        productId=raw.get("productId") or raw.get("id"),
        dolibarrId=raw.get("dolibarrId"),
        dolibarrRef=raw.get("dolibarrRef"),
        name=raw.get("name", ""),
        qty=int(raw.get("qty", 0)),
        price=float(raw.get("price", 0)),
    )


def _map_list_item(row: dict) -> OrderListItem:
    return OrderListItem(
        order_id=row["order_id"],
        customer_name=row.get("customer_name", ""),
        email=row.get("email", ""),
        phone=row.get("phone", ""),
        total=float(row.get("total", 0)),
        payment_method=row.get("payment_method", ""),
        paid=_derive_paid(row.get("status", ""), row.get("payment_method", "")),
        status=row.get("status", ""),
        dolibarr_order_id=row.get("dolibarr_order_id"),
        dolibarr_invoice_id=row.get("dolibarr_invoice_id"),
        created_at=row.get("created_at", ""),
    )


def _map_detail(row: dict) -> OrderDetail:
    base = _map_list_item(row)
    return OrderDetail(
        **base.model_dump(),
        subtotal=float(row.get("subtotal", 0)),
        shipping=float(row.get("shipping", 0)),
        discount=float(row.get("discount", 0)),
        coupon_code=row.get("coupon_code"),
        website_user_id=row.get("user_id"),
        address=row.get("address", ""),
        billing_details=row.get("billing_details"),
        notes=row.get("notes", ""),
        items=[_map_item(item) for item in (row.get("items") or [])],
    )


async def list_orders(unlinked_only: bool = False) -> list[OrderListItem]:
    rows = await supabase_client.list_orders(unlinked_only=unlinked_only)
    return [_map_list_item(row) for row in rows]


async def get_order(order_id: str) -> OrderDetail | None:
    row = await supabase_client.get_order(order_id)
    return _map_detail(row) if row else None


async def sync_order(order_id: str, patch: dict) -> OrderDetail | None:
    clean_patch = {k: v for k, v in patch.items() if v is not None}
    if not clean_patch:
        return await get_order(order_id)
    row = await supabase_client.update_order(order_id, clean_patch)
    return _map_detail(row) if row else None
