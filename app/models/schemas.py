from pydantic import BaseModel


class DolibarrProductResult(BaseModel):
    dolibarr_id: int
    ref: str
    label: str
    stock_count: int
    stock_status: str
    price: float
    description: str = ""


class StockResult(BaseModel):
    product_id: int
    dolibarr_id: int
    stock_count: int
    stock_status: str


class OrderNotificationItem(BaseModel):
    name: str
    qty: int
    price: float


class OrderNotificationRequest(BaseModel):
    id: str
    customer_name: str
    email: str
    phone: str
    status: str
    payment_method: str
    subtotal: float
    shipping: float
    discount: float = 0
    total: float
    coupon_code: str | None = None
    notes: str = ""
    items: list[OrderNotificationItem] = []


class OrderItem(BaseModel):
    productId: int | None = None
    dolibarrId: int | None = None
    dolibarrRef: str | None = None
    name: str
    qty: int
    price: float


class OrderListItem(BaseModel):
    order_id: str
    customer_name: str
    email: str
    phone: str
    total: float
    payment_method: str
    paid: bool
    status: str
    dolibarr_order_id: str | None = None
    dolibarr_invoice_id: str | None = None
    created_at: str


class OrderDetail(OrderListItem):
    address: str = ""
    billing_details: dict | None = None
    subtotal: float
    shipping: float
    discount: float = 0
    coupon_code: str | None = None
    website_user_id: str | None = None
    notes: str = ""
    items: list[OrderItem] = []


class OrderSyncRequest(BaseModel):
    dolibarr_order_id: str | None = None
    dolibarr_invoice_id: str | None = None
    status: str | None = None


class ProductSyncRequest(BaseModel):
    name: str | None = None
    dolibarr_ref: str | None = None
    categories: list[str] | None = None
    brand: str | None = None
    art_no: str | None = None
    name_ar: str | None = None
    color: str | None = None
    show_on_website: bool | None = None
