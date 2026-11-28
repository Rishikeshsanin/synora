import json
import logging
import time
import secrets
import shutil
import os
from datetime import datetime, timezone
from typing import Annotated, NoReturn
from collections.abc import Mapping
from uuid import UUID, uuid4
import httpx
from fastapi import FastAPI, Depends, Header, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException
from .config import settings
from .models import MusicSpec, ProjectSpec
from . import db, local_ace
from .provider import fixture_capabilities, to_engine_spec
from engines.music.core import MusicError
from .storage import local_url, local_path, valid_signature, SupabaseStorage

log=logging.getLogger("synora.api")
app=FastAPI(title="Synora",version="0.1.0",docs_url=None if settings.environment=="production" else "/docs")
if settings.cors_origins:
    app.add_middleware(CORSMiddleware,allow_origins=settings.cors_origins.split(","),allow_methods=["GET","POST"],allow_headers=["Authorization","Content-Type","Idempotency-Key"])

class ApiError(HTTPException):
    """Public, sanitized error with Starlette-compatible string detail."""
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(status_code=status, detail=message)
        self.code = code
        self.public_message = message


def error(request: Request, status: int, code: str, message: str,
          headers: Mapping[str, str] | None = None) -> JSONResponse:
    request_id = getattr(request.state, "request_id", str(uuid4()))
    return JSONResponse(
        status_code=status,
        content={"code": code, "message": message, "request_id": request_id},
        headers={**(headers or {}), "X-Request-ID": request_id, "Cache-Control": "no-store"},
    )

@app.middleware("http")
async def trace(request,call_next):
    request.state.request_id=str(uuid4())
    if request.method=="POST":
        # Enforce actual received bytes, not just an untrusted Content-Length.
        body=bytearray()
        async for chunk in request.stream():
            if len(body)+len(chunk)>32768:
                return error(request,413,"body_too_large","Request too large")
            body.extend(chunk)
        request._body=bytes(body)
    try:
        response=await call_next(request)
    except Exception:
        log.warning("request_failed id=%s",request.state.request_id)
        response=error(request,500,"internal_error","Internal error")
    response.headers["X-Request-ID"]=request.state.request_id
    response.headers["Cache-Control"]="no-store"
    return response

@app.exception_handler(HTTPException)
async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
    if isinstance(exc, ApiError):
        return error(request, exc.status_code, exc.code, exc.public_message, exc.headers)
    # Framework errors keep their status and protocol headers, never raw detail.
    return error(request, exc.status_code, "http_error", "Request failed", exc.headers)

@app.exception_handler(RequestValidationError)
async def invalid(request,exc):
    return error(request,422,"invalid_request","Request validation failed")

def abort(status: int, code: str, message: str) -> NoReturn:
    raise ApiError(status, code, message)

def user(authorization: Annotated[str|None,Header()]=None):
    if not authorization or not authorization.startswith("Bearer ") or len(authorization)>8192:
        abort(401,"unauthorized","Bearer token required")
    token=authorization[7:]
    if settings.environment in ("local","test") and settings.provider=="fixture":
        for expected, uid in json.loads(settings.fixture_tokens).items():
            if expected and secrets.compare_digest(expected.encode(),token.encode()):
                return UUID(uid)
    if not settings.supabase_url or not settings.supabase_key:
        abort(401,"unauthorized","Invalid token")
    try:
        if settings.provider=="ace-step":
            with httpx.Client(trust_env=False,follow_redirects=False,timeout=5) as client:
                response=client.get(settings.supabase_url+"/auth/v1/user",headers={"apikey":settings.supabase_key,"Authorization":f"Bearer {token}"})
        else:
            response=httpx.get(settings.supabase_url+"/auth/v1/user",headers={"apikey":settings.supabase_key,"Authorization":f"Bearer {token}"},timeout=5)
        if response.status_code in (401,403):
            abort(401,"unauthorized","Invalid token")
        response.raise_for_status()
        record=response.json()
        if record.get("is_anonymous"):
            abort(403,"forbidden","Account required")
        return UUID(record["id"])
    except (httpx.HTTPError,ValueError,KeyError):
        abort(503,"auth_unavailable","Authentication unavailable")

def job_view(row):
    if (not row or (row["simulated"] and settings.environment=="production")
            or (row.get("experimental_config") is not None and settings.environment!="local")):
        abort(404,"not_found","Job not found")
    return {k:row[k] for k in ("id","status","progress","asset_id","error","created_at","updated_at","provider","simulated")}

@app.get("/health")
def health(): return {"status":"ok"}

@app.get("/ready")
def ready():
    try:
        with db.db() as c:
            c.execute("select id,experimental_config from synora.jobs limit 0")
        if settings.provider not in ("fixture","ace-step"):
            abort(503,"provider_disabled","No approved provider")
        if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
            abort(503,"not_ready","Audio validation tools unavailable")
        settings.media_dir.mkdir(parents=True, exist_ok=True)
        if not os.access(settings.media_dir, os.W_OK):
            abort(503,"not_ready","Media storage unavailable")
        return {"status":"ready","simulated":settings.provider=="fixture"}
    except HTTPException:
        raise
    except Exception:
        abort(503,"not_ready","Database unavailable")

@app.get("/v1/music/capabilities")
def capabilities():
    if settings.provider=="fixture":
        return fixture_capabilities()
    if settings.provider=="ace-step":
        return local_ace.capabilities(settings)
    return {"available":False,"simulated":False}

@app.post("/v1/music/jobs",status_code=202)
def submit(spec:MusicSpec,uid:Annotated[UUID,Depends(user)],key:Annotated[str,Header(alias="Idempotency-Key",min_length=1,max_length=128)],project_id:UUID|None=None):
    if not key.strip():
        abort(422,"invalid_request","Idempotency key required")
    if settings.provider not in ("fixture","ace-step"):
        abort(503,"provider_disabled","No approved provider")
    try:
        to_engine_spec(spec)
        if settings.provider=="ace-step":
            local_ace.validate_request(spec)
            return job_view(db.submit(uid,key,spec.model_dump(mode="json"),project_id,local_ace.options(settings)))
        return job_view(db.submit(uid,key,spec.model_dump(mode="json"),project_id))
    except db.ReconciliationRequired:
        abort(503,"provider_reconciliation_required","Experimental generation needs operator reconciliation")
    except db.ProjectNotFound:
        abort(404,"not_found","Project not found")
    except (ValueError, MusicError):
        abort(422,"unsupported_spec","Music specification unsupported")
    except db.Conflict:
        abort(409,"idempotency_conflict","Key already used for a different request")
    except db.RateLimited:
        abort(429,"rate_limited","Generation limit reached")

@app.get("/v1/jobs/{id}")
def get_job(id:UUID,uid:Annotated[UUID,Depends(user)]): return job_view(db.owned_job(uid,id))

@app.get("/v1/jobs/{id}/recipe")
def recipe(id:UUID,uid:Annotated[UUID,Depends(user)]):
    row=db.owned_job(uid,id)
    job_view(row)
    if row["kind"]!="music":
        abort(404,"not_found","Job not found")
    # Validate the stored public spec rather than returning arbitrary internal fields.
    return {"project_id":row["project_id"],"spec":MusicSpec.model_validate(row["spec"]).model_dump(mode="json")}


@app.get("/v1/jobs/{id}/generation-info")
def generation_info(id:UUID,uid:Annotated[UUID,Depends(user)]):
    row=db.owned_job(uid,id)
    job_view(row)
    config=row.get("experimental_config")
    if config is None:
        return {"simulated":row["simulated"],"experimental":False,
                "quality_status":"not_applicable" if row["simulated"] else "unverified"}
    asset=db.owned_asset(uid,row["asset_id"]) if row["asset_id"] else None
    provenance=asset["provenance"] if asset else {}
    return {"simulated":False,"experimental":True,
            **{k:config.get(k) for k in ("precision_configured","cpu_offload_configured",
                "weights_revision","code_revision","semantic_lm","quality_status","language_evaluated","origin_status")},
            "requested_duration_seconds":row["spec"]["duration_seconds"],
            "requested_language":row["spec"].get("language"),
            "requested_mode":row["spec"]["mode"],
            "technical_status":provenance.get("technical_status","not_validated"),
            "actual_duration_seconds":provenance.get("actual_duration_seconds"),
            "revision_verified_by_api":False,"precision_verified_by_api":False,
            "failure_code":row["error"].get("code") if row["error"] else None,
            "reconciliation_required":row["reconciliation_required"] and row["status"]!="running"}


@app.post("/v1/jobs/{id}/cancel")
def cancel(id:UUID,uid:Annotated[UUID,Depends(user)]):
    job_view(db.owned_job(uid,id))
    return job_view(db.cancel(uid,id))

def asset_view(row, download=False):
    if not row:
        abort(404,"not_found","Asset not found")
    local_real=(row.get("provenance") or {}).get("storage_backend")=="local-ace"
    if (row["simulated"] and settings.environment=="production") or (local_real and settings.environment!="local"):
        abort(404,"not_found","Asset not found")
    expiry=int(time.time())+300
    asset_id=UUID(str(row["id"]))
    url=local_url(asset_id,expiry,download) if row["simulated"] or local_real else SupabaseStorage().sign(row["storage_key"],download)
    return {**{k:row[k] for k in ("id","kind","mime_type","duration_seconds","simulated")},"url":url,"expires_at":datetime.fromtimestamp(expiry,timezone.utc)}

@app.get("/v1/assets/{id}")
def asset(id:UUID,uid:Annotated[UUID,Depends(user)],download:bool=False):
    return asset_view(db.owned_asset(uid,id),download)

@app.get("/v1/music/library")
def library(uid:Annotated[UUID,Depends(user)],
            limit:Annotated[int,Query(ge=1,le=100)]=30,
            cursor:UUID|None=None,project_id:UUID|None=None):
    try:
        rows=db.music_library(uid,limit,cursor,settings.environment!="production",project_id,settings.environment=="local")
    except db.ProjectNotFound:
        abort(404,"not_found","Project not found")
    except ValueError:
        abort(422,"invalid_cursor","Invalid library cursor")
    items=[]
    for row in rows[:limit]:
        joined=row["joined_asset"]
        items.append({"job":job_view(row),"asset":asset_view(joined) if joined["id"] else None,
                      "prompt":row["spec"]["prompt"]})
    return {"items":items,"next_cursor":rows[limit-1]["id"] if len(rows)>limit else None}

@app.get("/v1/media/{id}")
def media(id:UUID,expires:int,download:bool,sig:str):
    if settings.environment=="production" or not valid_signature(id,expires,download,sig):
        abort(403,"forbidden","Invalid or expired media URL")
    with db.db() as c:
        row=c.execute("select * from synora.assets where id=%s and (simulated or (%s and provenance->>'storage_backend'='local-ace'))",(id,settings.environment=="local")).fetchone()
    if not row or not local_path(row["storage_key"]).is_file():
        abort(404,"not_found","Asset not found")
    return FileResponse(local_path(row["storage_key"]),media_type=row["mime_type"],filename=f"{id}.wav" if download else None)

@app.post("/v1/projects",status_code=201)
def create_project(spec:ProjectSpec,uid:Annotated[UUID,Depends(user)]):
    with db.db() as c:
        return c.execute("insert into synora.projects(user_id,name) values(%s,%s) returning id,name,created_at",(uid,spec.name)).fetchone()

@app.get("/v1/projects")
def projects(uid:Annotated[UUID,Depends(user)]):
    with db.db() as c:
        return c.execute("select id,name,created_at from synora.projects where user_id=%s order by created_at desc limit 100",(uid,)).fetchall()


@app.get("/v1/projects/{id}")
def project(id:UUID,uid:Annotated[UUID,Depends(user)]):
    try:
        return db.owned_project(uid,id)
    except db.ProjectNotFound:
        abort(404,"not_found","Project not found")
