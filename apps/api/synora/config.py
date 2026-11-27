import os
from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True)
class Settings:
    environment: str = os.getenv("SYNORA_ENV", "production")
    provider: str = os.getenv("MUSIC_PROVIDER", "disabled")
    database_url: str = os.getenv("DATABASE_URL", "")
    supabase_url: str = os.getenv("SUPABASE_URL", "").rstrip("/")
    supabase_key: str = os.getenv("SUPABASE_PUBLISHABLE_KEY", "")
    storage_key: str = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    media_dir: Path = Path(os.getenv("MEDIA_DIR", "/tmp/synora-media"))
    signing_key: str = os.getenv("MEDIA_SIGNING_KEY", "")
    public_url: str = os.getenv("API_PUBLIC_URL", "").rstrip("/")
    cors_origins: str = os.getenv("CORS_ORIGINS", "")
    fixture_tokens: str = os.getenv("FIXTURE_TOKENS_JSON", "{}")

    def __post_init__(self):
        if self.environment not in ("local", "test", "production"):
            raise ValueError("invalid environment")
        if self.provider not in ("fixture", "disabled"):
            raise ValueError("provider not approved")
        if self.provider == "fixture" and self.environment == "production":
            raise ValueError("fixture forbidden in production")
        if self.environment == "production" and self.fixture_tokens != "{}":
            raise ValueError("fixture auth forbidden in production")
        if self.provider == "fixture" and (len(self.signing_key) < 32 or not self.public_url):
            raise ValueError("fixture requires signing key and API_PUBLIC_URL")

settings = Settings()
