import httpx

from app.core.config import settings


class SupabaseConfigError(RuntimeError):
    """Raised when Supabase rejects a request — almost always means
    SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY aren't set correctly in .env yet,
    which is the first thing anyone enabling this feature will hit."""


def _raise_for_status(response: httpx.Response) -> None:
    if response.status_code >= 400:
        raise SupabaseConfigError(
            f"Supabase rejected the request ({response.status_code}): {response.text}. "
            "Check SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in the backend's .env."
        )


class SupabaseClient:
    """Thin wrapper around Supabase's PostgREST API, used ONLY by the
    /orders router (see app/routers/orders.py) so the Dolibarr website-orders
    module can read and sync orders. This is the one place in the whole
    system where FastAPI is allowed to touch Supabase directly — every other
    write in the app still goes browser -> supabase-js, same as before."""

    def __init__(self) -> None:
        self._base_url = settings.supabase_url.rstrip("/") + "/rest/v1"
        self._auth_base = settings.supabase_url.rstrip("/") + "/auth/v1"
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            headers={
                "apikey": settings.supabase_service_role_key,
                "Authorization": f"Bearer {settings.supabase_service_role_key}",
                "Content-Type": "application/json",
            },
            timeout=15.0,
        )

    def _require_configured(self) -> None:
        # An empty service-role key produces an "Authorization: Bearer "
        # header, which httpx rejects as malformed before ever sending the
        # request (LocalProtocolError) — check up front so that shows up as
        # the same clear config error as an actual Supabase rejection would.
        if not settings.supabase_url or not settings.supabase_service_role_key:
            raise SupabaseConfigError(
                "SUPABASE_URL and/or SUPABASE_SERVICE_ROLE_KEY are not set in the backend's .env."
            )

    async def get_site_setting(self, key: str) -> dict | None:
        """Reads one row from `site_settings` (the same key/value store the
        React admin panel's settings pages already write to via supabase-js).
        Used to let a superadmin override Dolibarr/FastAPI config from
        AdminIntegrationSettings without needing a new .env + redeploy for
        every change. Returns None (not raises) on any failure — a bad/unset
        Supabase config here should silently fall back to .env, not break
        Dolibarr-facing endpoints that have nothing to do with Supabase."""
        try:
            response = await self._client.get("/site_settings", params={"select": "value", "key": f"eq.{key}"})
        except httpx.HTTPError:
            return None
        if response.status_code >= 400:
            return None
        rows = response.json()
        return rows[0]["value"] if rows else None

    async def list_orders(self, unlinked_only: bool = False) -> list[dict]:
        self._require_configured()
        params = {"select": "*", "order": "created_at.desc"}
        if unlinked_only:
            # "Unlinked" here means "still needs sales-team action" — a
            # Cancelled order has already been handled (just not turned into
            # a Dolibarr order), so it shouldn't keep counting as new.
            params["dolibarr_order_id"] = "is.null"
            params["status"] = "not.in.(Cancelled,Failed)"
        response = await self._client.get("/orders", params=params)
        _raise_for_status(response)
        return response.json()

    async def get_order(self, order_id: str) -> dict | None:
        self._require_configured()
        response = await self._client.get("/orders", params={"select": "*", "order_id": f"eq.{order_id}"})
        _raise_for_status(response)
        rows = response.json()
        return rows[0] if rows else None

    async def update_order(self, order_id: str, patch: dict) -> dict | None:
        self._require_configured()
        response = await self._client.patch(
            "/orders",
            params={"order_id": f"eq.{order_id}"},
            json=patch,
            headers={"Prefer": "return=representation"},
        )
        _raise_for_status(response)
        rows = response.json()
        return rows[0] if rows else None

    async def verify_user_token(self, access_token: str) -> dict | None:
        """Confirms `access_token` is a genuinely live Supabase session and
        returns {id, email, ...}, or None if it isn't. Uses the anon key, not
        the service-role key — this call authenticates as the calling user,
        not as an admin."""
        self._require_configured()
        response = await self._client.get(
            f"{self._auth_base}/user",
            headers={"Authorization": f"Bearer {access_token}", "apikey": settings.supabase_anon_key},
        )
        if response.status_code != 200:
            return None
        return response.json()

    async def get_profile_role(self, user_id: str) -> str | None:
        self._require_configured()
        response = await self._client.get("/profiles", params={"select": "role", "id": f"eq.{user_id}"})
        _raise_for_status(response)
        rows = response.json()
        return rows[0]["role"] if rows else None

    async def list_admins(self) -> list[dict]:
        self._require_configured()
        response = await self._client.get(
            "/profiles",
            params={"select": "id,email,name,role,created_at", "role": "in.(admin,superadmin)"},
        )
        _raise_for_status(response)
        return response.json()

    async def update_profile_role(self, user_id: str, role: str) -> dict | None:
        self._require_configured()
        response = await self._client.patch(
            "/profiles",
            params={"id": f"eq.{user_id}"},
            json={"role": role},
            headers={"Prefer": "return=representation"},
        )
        _raise_for_status(response)
        rows = response.json()
        return rows[0] if rows else None

    async def create_admin_user(self, email: str, password: str, name: str, role: str) -> dict:
        """Creates a brand-new Supabase Auth account and profile row directly
        with the given role — used by the superadmin-only 'Create new admin'
        flow, so a superadmin never has to sign out of their own session or
        rely on a customer self-registering first. The auth user is created
        with email_confirm=True since this is an internally-provisioned
        account, not a public signup that needs email verification."""
        self._require_configured()
        auth_response = await self._client.post(
            f"{self._auth_base}/admin/users",
            json={
                "email": email,
                "password": password,
                "email_confirm": True,
                "user_metadata": {"name": name},
            },
        )
        _raise_for_status(auth_response)
        auth_user = auth_response.json()
        user_id = auth_user["id"]

        profile_response = await self._client.post(
            "/profiles",
            json={"id": user_id, "email": email, "name": name or "", "role": role, "terms_accepted": True},
            headers={"Prefer": "return=representation"},
        )
        _raise_for_status(profile_response)
        rows = profile_response.json()
        return rows[0] if rows else {"id": user_id, "email": email, "name": name, "role": role}

    async def delete_user_cascade(self, user_id: str) -> None:
        """Deletes a user account entirely: their cart/wishlist rows, their
        profile, unlinks (but keeps) their past orders for historical record,
        then deletes the actual Supabase Auth account. Order matters — all of
        profiles/cart_items/wishlist_items/orders have a foreign key to
        auth.users(id), so the auth user can't be deleted first."""
        self._require_configured()
        _raise_for_status(await self._client.delete("/cart_items", params={"user_id": f"eq.{user_id}"}))
        _raise_for_status(await self._client.delete("/wishlist_items", params={"user_id": f"eq.{user_id}"}))
        _raise_for_status(
            await self._client.patch("/orders", params={"user_id": f"eq.{user_id}"}, json={"user_id": None})
        )
        _raise_for_status(await self._client.delete("/profiles", params={"id": f"eq.{user_id}"}))
        # httpx.delete() doesn't support a request body — must use .request()
        # to send should_soft_delete=False. Without it, GoTrue's admin delete
        # endpoint defaults to a SOFT delete: the auth.users row survives
        # with deleted_at set, and its email stays claimed, so re-creating
        # an account with the same email later fails with "email_exists"
        # even though the UI reported the deletion as successful.
        _raise_for_status(
            await self._client.request(
                "DELETE",
                f"{self._auth_base}/admin/users/{user_id}",
                json={"should_soft_delete": False},
            )
        )

    async def aclose(self) -> None:
        await self._client.aclose()


supabase_client = SupabaseClient()
