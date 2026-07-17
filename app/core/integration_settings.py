"""Resolves Dolibarr connection settings by checking Supabase's
`site_settings.integration_settings` row first (the same value the React
admin panel's Integrations page — superadmin only — writes to), falling back
to the backend's own .env values for any field not overridden there.

Cached for a short TTL so a superadmin's change takes effect quickly without
every single Dolibarr-facing request round-tripping to Supabase first.
"""

import time

from app.core.config import settings
from app.core.supabase_client import supabase_client

_CACHE_TTL_SECONDS = 30
_cache: dict | None = None
_cache_at: float = 0.0


async def get_dolibarr_config() -> dict:
    """Returns {"api_url", "api_key", "sync_secret"} — each field individually
    overridden by Supabase's saved value when present and non-empty, else the
    .env default."""
    global _cache, _cache_at

    now = time.monotonic()
    if _cache is None or (now - _cache_at) > _CACHE_TTL_SECONDS:
        overrides = await supabase_client.get_site_setting("integration_settings") or {}
        _cache = {
            "api_url": (overrides.get("dolibarrApiUrl") or settings.dolibarr_api_url or "").rstrip("/"),
            "api_key": overrides.get("dolibarrApiKey") or settings.dolibarr_api_key,
            "sync_secret": overrides.get("dolibarrSyncSecret") or settings.dolibarr_sync_secret,
        }
        _cache_at = now

    return _cache


def invalidate_cache() -> None:
    """Call after AdminIntegrationSettings saves a change, if a future admin
    endpoint for this is added — not required today since the 30s TTL already
    keeps requests fresh without one."""
    global _cache
    _cache = None
