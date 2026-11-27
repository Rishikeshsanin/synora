import json
import logging
import time
import secrets
import shutil
import os
from datetime import datetime, timezone
from typing import Annotated, NoReturn
from uuid import UUID, uuid4
import httpx
from fastapi import FastAPI, Depends, Header, Query
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException
from .config import settings
from .models import MusicSpec, ProjectSpec
from . import db
from .provider import fixture_capabilities, to_engine_spec
from engines.music.core import MusicError
from .storage import local_url, local_path, valid_signature, SupabaseStorage

log=logging.getLogger("synora.api")
app=FastAPI(title="Synora",version="0.1.0",docs_url=None if settings.environment=="production" else "/docs")
if settings.cors_origins:
    app.add_middleware(CORSMiddleware,allow_origins=settings.cors_origins.split(","),allow_methods=["GET","POST"],allow_headers=["Authorization","Content-Type","Idempotency-Key"])

def error(request,status,code,message):
    return JSONResponse(status_code=status,content={"code":code,"message":message,"request_id":getattr(request.state,"request_id",str(uuid4()))})

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
async def http_error(request,exc):
    code,message=exc.detail if isinstance(exc.detail,tuple) else ("http_error","Request failed")
    return error(request,exc.status_code,code,message)

@app.exception_handler(RequestValidationError)
async def invalid(request,exc):
    return error(request,422,"invalid_request","Request validation failed")

def abort(status: int, code: str, message: str) -> NoReturn:
    raise HTTPException(status,detail=(code,message))

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
    if not row or (row["simulated"] and settings.environment=="production"):
        abort(404,"not_found","Job not found")
    return {k:row[k] for k in ("id","status","progress","asset_id","error","created_at","updated_at","provider","simulated")}

@app.get("/health")
def health(): return {"status":"ok"}

@app.get("/ready")
def ready():
    try:
        with db.db() as c:
            c.execute("select id from synora.jobs limit 0")
        if settings.provider!="fixture":
            abort(503,"provider_disabled","No approved provider")
        if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
            abort(503,"not_ready","Audio validation tools unavailable")
        settings.media_dir.mkdir(parents=True, exist_ok=True)
        if not os.access(settings.media_dir, os.W_OK):
            abort(503,"not_ready","Media storage unavailable")
        return {"status":"ready","simulated":True}
    except HTTPException:
        raise
    except Exception:
        abort(503,"not_ready","Database unavailable")

@app.get("/v1/music/capabilities")
def capabilities():
    return fixture_capabilities() if settings.provider=="fixture" else {"available":False,"simulated":False}

@app.post("/v1/music/jobs",status_code=202)
def submit(spec:MusicSpec,uid:Annotated[UUID,Depends(user)],key:Annotated[str,Header(alias="Idempotency-Key",min_length=1,max_length=128)]):
    if not key.strip():
        abort(422,"invalid_request","Idempotency key required")
    if settings.provider!="fixture":
        abort(503,"provider_disabled","No approved provider")
    try:
        to_engine_spec(spec)
        return job_view(db.submit(uid,key,spec.model_dump(mode="json")))
    except (ValueError, MusicError):
        abort(422,"unsupported_spec","Music specification unsupported")
    except db.Conflict:
        abort(409,"idempotency_conflict","Key already used for a different request")
    except db.RateLimited:
        abort(429,"rate_limited","Generation limit reached")

@app.get("/v1/jobs/{id}")
def get_job(id:UUID,uid:Annotated[UUID,Depends(user)]): return job_view(db.owned_job(uid,id))

@app.post("/v1/jobs/{id}/cancel")
def cancel(id:UUID,uid:Annotated[UUID,Depends(user)]): return job_view(db.cancel(uid,id))

def asset_view(row, download=False):
    if not row or (row["simulated"] and settings.environment=="production"):
        abort(404,"not_found","Asset not found")
    expiry=int(time.time())+300
    asset_id=UUID(str(row["id"]))
    url=local_url(asset_id,expiry,download) if row["simulated"] else SupabaseStorage().sign(row["storage_key"],download)
    return {**{k:row[k] for k in ("id","kind","mime_type","duration_seconds","simulated")},"url":url,"expires_at":datetime.fromtimestamp(expiry,timezone.utc)}

@app.get("/v1/assets/{id}")
def asset(id:UUID,uid:Annotated[UUID,Depends(user)],download:bool=False):
    return asset_view(db.owned_asset(uid,id),download)

@app.get("/v1/music/library")
def library(uid:Annotated[UUID,Depends(user)],
            limit:Annotated[int,Query(ge=1,le=100)]=30,
            cursor:UUID|None=None):
    try:
        rows=db.music_library(uid,limit,cursor,settings.environment!="production")
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
        row=c.execute("select * from synora.assets where id=%s and simulated",(id,)).fetchone()
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
