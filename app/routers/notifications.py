import httpx
from fastapi import APIRouter

from app.core.config import settings
from app.models.schemas import OrderNotificationRequest

router = APIRouter(prefix="/notifications", tags=["notifications"])


def _format_order_summary(order: OrderNotificationRequest) -> str:
    item_lines = "\n".join(
        f"  • {item.name} x{item.qty}  –  QAR {item.price * item.qty:.2f}" for item in order.items
    )
    lines = [
        "New order – Sports Way Trading",
        "",
        f"Order ID   : {order.id}",
        f"Status     : {order.status}",
        f"Payment    : {order.payment_method}",
        "",
        "-- CUSTOMER --",
        f"Name       : {order.customer_name}",
        f"Email      : {order.email}",
        f"Phone      : {order.phone}",
        "",
        "-- ITEMS --",
        item_lines,
        "",
        f"Subtotal   : QAR {order.subtotal:.2f}",
    ]
    if order.discount:
        lines.append(f"Discount   : -QAR {order.discount:.2f} ({order.coupon_code or ''})")
    lines.append(f"Shipping   : {'Free' if order.shipping == 0 else f'QAR {order.shipping:.2f}'}")
    lines.append(f"TOTAL      : QAR {order.total:.2f}")
    if order.notes:
        lines.append(f"\nNotes      : {order.notes}")
    return "\n".join(lines)


@router.post("/order-placed")
async def notify_order_placed(order: OrderNotificationRequest):
    """Sends the order-placed email + WhatsApp alert. Runs entirely server-side
    so the Infobip API key never has to live in frontend source (it used to be
    hardcoded directly in CheckoutPage.jsx)."""
    summary = _format_order_summary(order)
    result = {"email_sent": False, "whatsapp_sent": False}

    async with httpx.AsyncClient(timeout=10.0) as client:
        # Email via FormSubmit — TEMPORARILY DISABLED (2026-07-15) per request,
        # re-enable by restoring this block.
        # try:
        #     response = await client.post(
        #         f"https://formsubmit.co/ajax/{settings.formsubmit_email}",
        #         json={
        #             "_subject": f"New Order {order.id} - Sports Way Trading",
        #             "_replyto": order.email,
        #             "order_id": order.id,
        #             "customer": order.customer_name,
        #             "phone": order.phone,
        #             "total": f"QAR {order.total:.2f}",
        #             "message": summary,
        #         },
        #     )
        #     result["email_sent"] = response.status_code < 300
        # except httpx.HTTPError:
        #     pass

        if settings.infobip_api_key and settings.infobip_base_url:
            try:
                response = await client.post(
                    f"{settings.infobip_base_url.rstrip('/')}/whatsapp/1/message/text",
                    headers={
                        "Authorization": settings.infobip_api_key,
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                    },
                    json={
                        "from": settings.infobip_whatsapp_sender,
                        "to": settings.infobip_whatsapp_recipient,
                        "content": {"text": summary},
                    },
                )
                result["whatsapp_sent"] = response.status_code < 300
            except httpx.HTTPError:
                pass

    return result
