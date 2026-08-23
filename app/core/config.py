from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Which Dolibarr this backend talks to — see dolibarr_api_url / api_key /
    # verify_ssl below, which resolve to the matching *_local or *_production
    # value. Flip DOLIBARR_MODE in .env to switch the whole backend over.
    dolibarr_mode: str = "local"

    dolibarr_api_url_local: str = ""
    dolibarr_api_key_local: str = ""
    dolibarr_verify_ssl_local: bool = True

    dolibarr_api_url_production: str = ""
    dolibarr_api_key_production: str = ""
    dolibarr_verify_ssl_production: bool = True

    cors_origins: str = "http://localhost:5173"

    # Order-notification secrets — kept server-side so nothing ships in the
    # frontend bundle. Previously the Infobip key was hardcoded directly in
    # CheckoutPage.jsx, visible to anyone who opened devtools.
    infobip_base_url: str = ""
    infobip_api_key: str = ""
    infobip_whatsapp_sender: str = ""
    infobip_whatsapp_recipient: str = ""

    formsubmit_email: str = "sales@sports-way.com"

    # Used only by the /orders router, which the Dolibarr website-orders
    # module calls. This is the one deliberate exception to "FastAPI never
    # touches Supabase" — the caller here is Dolibarr (server-to-server),
    # never a browser, and every write is gated by dolibarr_sync_secret.
    supabase_url: str = ""
    supabase_service_role_key: str = ""
    dolibarr_sync_secret: str = ""

    # Used only by /admin/users delete — verifies the caller is a genuinely
    # logged-in admin (via their own Supabase access token) before using the
    # service-role key to actually delete anything. The anon key is already
    # public (it ships in the frontend bundle too), so this isn't a secret.
    supabase_anon_key: str = ""

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def dolibarr_api_url(self) -> str:
        return self.dolibarr_api_url_production if self.dolibarr_mode == "production" else self.dolibarr_api_url_local

    @property
    def dolibarr_api_key(self) -> str:
        return self.dolibarr_api_key_production if self.dolibarr_mode == "production" else self.dolibarr_api_key_local

    @property
    def dolibarr_verify_ssl(self) -> bool:
        return self.dolibarr_verify_ssl_production if self.dolibarr_mode == "production" else self.dolibarr_verify_ssl_local


settings = Settings()
