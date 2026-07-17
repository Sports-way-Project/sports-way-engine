import base64

import httpx

from app.core.config import settings
from app.core.integration_settings import get_dolibarr_config


class DolibarrClient:
    """Thin wrapper around the Dolibarr REST API. This is the only place
    in the whole system allowed to talk to Dolibarr directly.

    Base URL / API key can come from either the backend's .env or a
    superadmin's override saved in Supabase (see get_dolibarr_config) — the
    underlying httpx client is rebuilt whenever that resolved config changes,
    so a saved override takes effect without restarting the process."""

    def __init__(self) -> None:
        self._base_url = ""
        self._api_key = ""
        self._client: httpx.AsyncClient | None = None

    async def _ensure_client(self) -> httpx.AsyncClient:
        config = await get_dolibarr_config()
        if self._client is None or config["api_url"] != self._base_url or config["api_key"] != self._api_key:
            if self._client is not None:
                await self._client.aclose()
            self._base_url = config["api_url"]
            self._api_key = config["api_key"]
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                headers={"DOLAPIKEY": self._api_key},
                verify=settings.dolibarr_verify_ssl,
                timeout=15.0,
            )
        return self._client

    async def search_products(self, query: str, limit: int = 15) -> list[dict]:
        client = await self._ensure_client()
        safe_query = query.replace("'", "")
        sqlfilters = f"(t.ref:like:'%{safe_query}%') or (t.label:like:'%{safe_query}%')"
        response = await client.get(
            "/products",
            params={
                "sqlfilters": sqlfilters,
                "limit": limit,
                "includestockdata": 1,
            },
        )
        response.raise_for_status()
        return response.json()

    async def get_product(self, dolibarr_id: int, include_stock: bool = True) -> dict:
        client = await self._ensure_client()
        response = await client.get(
            f"/products/{dolibarr_id}",
            params={"includestockdata": 1 if include_stock else 0},
        )
        response.raise_for_status()
        return response.json()

    async def list_products(self, page: int = 0, limit: int = 100) -> list[dict]:
        client = await self._ensure_client()
        response = await client.get(
            "/products",
            params={"page": page, "limit": limit, "includestockdata": 1},
        )
        response.raise_for_status()
        return response.json()

    async def get_order(self, dolibarr_order_id: str) -> dict:
        client = await self._ensure_client()
        response = await client.get(f"/orders/{dolibarr_order_id}")
        response.raise_for_status()
        return response.json()

    async def get_invoice(self, dolibarr_invoice_id: str) -> dict:
        client = await self._ensure_client()
        response = await client.get(f"/invoices/{dolibarr_invoice_id}")
        response.raise_for_status()
        return response.json()

    async def download_document(self, modulepart: str, ref: str) -> bytes | None:
        """Downloads a previously-generated PDF via Dolibarr's documented
        /documents/download endpoint (modulepart: 'commande', 'facture',
        'expedition'). Returns None if Dolibarr hasn't generated the PDF yet
        (the admin needs to open the object in Dolibarr once to generate it —
        this call does not trigger generation itself, only fetches an
        existing file, to avoid guessing at Dolibarr's builddoc behavior
        without a live instance to verify it against)."""
        client = await self._ensure_client()
        response = await client.get(
            "/documents/download",
            params={"modulepart": modulepart, "original_file": f"{ref}/{ref}.pdf"},
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        data = response.json()
        content_b64 = data.get("content")
        if not content_b64:
            return None
        return base64.b64decode(content_b64)

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()


dolibarr_client = DolibarrClient()
