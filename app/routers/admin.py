from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from app.core.supabase_client import SupabaseConfigError, supabase_client

router = APIRouter(prefix="/admin", tags=["admin"])

ADMIN_ROLES = {"admin", "superadmin"}


async def _require_admin(authorization: str | None) -> dict:
    """Verifies the caller is a logged-in Supabase user whose profile role is
    'admin' or 'superadmin', using their own access token — never a shared
    secret, since this is called from the browser admin panel, not
    server-to-server."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = authorization.split(" ", 1)[1]

    user = await supabase_client.verify_user_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired session")

    role = await supabase_client.get_profile_role(user["id"])
    if role not in ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="Admin role required")

    user["role"] = role
    return user


async def _require_superadmin(authorization: str | None) -> dict:
    admin = await _require_admin(authorization)
    if admin["role"] != "superadmin":
        raise HTTPException(status_code=403, detail="Superadmin role required")
    return admin


@router.delete("/users/{user_id}")
async def delete_user(user_id: str, authorization: str | None = Header(None)):
    """Deletes a customer account entirely (cart/wishlist rows, profile, and
    the actual Supabase Auth account), unlinking but keeping their past
    orders for historical record. See SupabaseClient.delete_user_cascade for
    the exact deletion order (FK constraints require a specific sequence).
    Deleting an admin/superadmin account through this endpoint additionally
    requires the caller to be a superadmin."""
    try:
        admin = await _require_admin(authorization)
        if admin["id"] == user_id:
            raise HTTPException(status_code=400, detail="You can't delete your own account from here")

        target_role = await supabase_client.get_profile_role(user_id)
        if target_role in ADMIN_ROLES and admin["role"] != "superadmin":
            raise HTTPException(status_code=403, detail="Only a superadmin can delete an admin account")

        await supabase_client.delete_user_cascade(user_id)
    except SupabaseConfigError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return {"deleted": True}


@router.get("/admins")
async def list_admins(authorization: str | None = Header(None)):
    """Lists every admin/superadmin account, for the superadmin-only 'Manage
    Admins' screen."""
    try:
        await _require_superadmin(authorization)
        admins = await supabase_client.list_admins()
    except SupabaseConfigError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return admins


class NewAdmin(BaseModel):
    email: str
    password: str
    name: str = ""
    role: str = "admin"


@router.post("/admins")
async def create_admin(body: NewAdmin, authorization: str | None = Header(None)):
    """Creates a brand-new admin (or superadmin) account directly —
    superadmin-only. Unlike promoting an existing customer, this doesn't
    require the person to have signed up first."""
    if body.role not in ("admin", "superadmin"):
        raise HTTPException(status_code=400, detail="role must be 'admin' or 'superadmin'")
    if len(body.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")

    try:
        await _require_superadmin(authorization)
        created = await supabase_client.create_admin_user(body.email, body.password, body.name, body.role)
    except SupabaseConfigError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return created


class RolePatch(BaseModel):
    role: str


@router.post("/admins/{user_id}/role")
async def update_admin_role(user_id: str, body: RolePatch, authorization: str | None = Header(None)):
    """Promotes a customer to admin, or demotes an admin back to customer.
    Superadmin-only — this is the only path in the app allowed to change
    `profiles.role` (see migration 006's trigger, which blocks the write
    everywhere else, including a compromised anon-key call from the browser)."""
    if body.role not in ("customer", "admin"):
        raise HTTPException(status_code=400, detail="role must be 'customer' or 'admin'")

    try:
        admin = await _require_superadmin(authorization)
        if admin["id"] == user_id:
            raise HTTPException(status_code=400, detail="You can't change your own role from here")

        updated = await supabase_client.update_profile_role(user_id, body.role)
    except SupabaseConfigError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    if not updated:
        raise HTTPException(status_code=404, detail="Profile not found")

    return updated
