import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

ACE_WEIGHTS = "eb84216a8ece2d56388e401efc28061a0c30a209"
ACE_CODE = "ca1e85fe9430179831e6bc6be790c332190a3866"

def local_origin(value: str) -> bool:
    try:
        p = urlsplit(value)
        return (p.scheme == "http" and p.hostname == "127.0.0.1" and p.port is not None and 1 <= p.port <= 65535
                and p.netloc == f"127.0.0.1:{p.port}" and value == value.strip()
                and not p.username and not p.password and not p.query and not p.fragment
                and p.path in ("", "/"))
    except ValueError:
        return False


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

    real_approved: bool = os.getenv("SYNORA_REAL_MUSIC_APPROVED") == "1"
    ace_local_approved: bool = os.getenv("SYNORA_ACE_LOCAL_APPROVED") == "1"
    ace_license_reviewed: bool = os.getenv("SYNORA_ACE_LICENSE_REVIEWED") == "1"
    ace_url: str = os.getenv("SYNORA_ACE_URL", "").rstrip("/")
    ace_key: str = field(default=os.getenv("SYNORA_ACE_KEY", ""), repr=False)
    ace_weights_revision: str = os.getenv("SYNORA_ACE_WEIGHTS_REVISION", "")
    ace_code_revision: str = os.getenv("SYNORA_ACE_CODE_REVISION", "")
    ace_precision: str = os.getenv("SYNORA_ACE_PRECISION", "")
    ace_cpu_offload: bool = os.getenv("SYNORA_ACE_CPU_OFFLOAD") == "1"

    def __post_init__(self):
        if self.environment not in ("local", "test", "production"):
            raise ValueError("invalid environment")
        if self.provider not in ("fixture", "disabled", "ace-step"):
            raise ValueError("provider not approved")
        if self.provider == "fixture" and self.environment == "production":
            raise ValueError("fixture forbidden in production")
        if self.environment == "production" and self.fixture_tokens != "{}":
            raise ValueError("fixture auth forbidden in production")
        if self.provider in ("fixture", "ace-step") and (len(self.signing_key) < 32 or not self.public_url):
            raise ValueError("fixture requires signing key and API_PUBLIC_URL")

        if self.provider == "ace-step":
            if (self.environment != "local" or not self.real_approved
                    or not self.ace_local_approved or not self.ace_license_reviewed
                    or self.fixture_tokens != "{}" or not self.ace_key
                    or not local_origin(self.ace_url) or not local_origin(self.public_url)
                    or not local_origin(self.supabase_url) or not self.supabase_key
                    or self.storage_key or self.ace_weights_revision != ACE_WEIGHTS
                    or self.ace_code_revision != ACE_CODE
                    or self.ace_precision not in ("fp16", "fp32")
                    or (self.ace_precision == "fp32" and not self.ace_cpu_offload)):
                raise ValueError("local ACE authorization/configuration incomplete")
            try:
                p = urlsplit(self.database_url)
                if p.scheme not in ("postgresql", "postgres") or p.hostname != "127.0.0.1" or p.query or p.fragment or p.path not in ("/synora_dev", "/synora_qa"):
                    raise ValueError()
            except ValueError:
                raise ValueError("local ACE requires a loopback development database") from None

settings = Settings()
