import hashlib
import hmac
import os
import time
from urllib.parse import quote
from uuid import UUID
import httpx
from .config import settings

def local_path(key):
    # Keys are generated server-side from three UUIDs.
    owner, job, attempt = key.split("/")
    return settings.media_dir / str(UUID(owner)) / str(UUID(job)) / (str(UUID(attempt.removesuffix(".wav"))) + ".wav")

def put_local(key, data):
    path=local_path(key)
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix(".tmp")
    with temporary.open("wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(temporary,path)

def delete_local(key):
    local_path(key).unlink(missing_ok=True)

def signature(asset, expiry, download):
    return hmac.new(settings.signing_key.encode(),f"{asset}:{expiry}:{int(download)}".encode(),hashlib.sha256).hexdigest()

def local_url(asset, expiry, download=False):
    sig=signature(asset,expiry,download)
    return f"{settings.public_url}/v1/media/{asset}?expires={expiry}&download={int(download)}&sig={sig}"

def valid_signature(asset, expiry, download, sig):
    return bool(settings.signing_key) and time.time() < expiry <= time.time()+300 and hmac.compare_digest(signature(asset,expiry,download),sig)

class SupabaseStorage:
    """Server-only adapter; bucket must be explicitly provisioned private."""
    bucket="synora-private"
    def put(self, key, data, mime):
        url=f"{settings.supabase_url}/storage/v1/object/{self.bucket}/{quote(key,safe='/')}"
        with httpx.Client(timeout=30) as c:
            response=c.post(url,headers={"apikey":settings.storage_key,"Authorization":f"Bearer {settings.storage_key}","Content-Type":mime,"x-upsert":"false"},content=data)
            response.raise_for_status()
    def sign(self, key, download=False):
        with httpx.Client(timeout=10) as c:
            response=c.post(f"{settings.supabase_url}/storage/v1/object/sign/{self.bucket}/{quote(key,safe='/')}",
                headers={"apikey":settings.storage_key,"Authorization":f"Bearer {settings.storage_key}"},json={"expiresIn":300})
            response.raise_for_status()
            path=response.json()["signedURL"]
        if not path.startswith("/object/sign/"): raise ValueError("unexpected storage URL")
        return settings.supabase_url+"/storage/v1"+path+("&download=" if download else "")
