from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.dolibarr_client import dolibarr_client
from app.core.supabase_client import supabase_client
from app.routers import admin, chat, notifications, orders, products, stock

// fastapi app
app = FastAPI(title="Sports Way FastAPI Core")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(products.router)
app.include_router(stock.router)
app.include_router(chat.router)
app.include_router(notifications.router)
app.include_router(orders.router)
app.include_router(admin.router)


@app.on_event("shutdown")
async def shutdown_event():
    await dolibarr_client.aclose()
    await supabase_client.aclose()


@app.get("/health")
async def health():
    return {"status": "ok"}
