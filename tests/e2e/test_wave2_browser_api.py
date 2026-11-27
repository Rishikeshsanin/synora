"""Real browser-origin API/CORS and audio acceptance; not a full Studio sign-in flow."""
import hashlib
import os
import time
from urllib.parse import urlparse
from uuid import uuid4
import pytest
from playwright.sync_api import sync_playwright


def required(name):
    value = os.getenv(name)
    if not value:
        if os.getenv("SYNORA_QA_REQUIRE_BROWSER_API") == "1":
            pytest.fail("Missing QA setting: "+name)
        pytest.skip("Missing browser API fixture configuration")
    return value


def test_browser_origin_authenticated_fixture_audio():
    web, api = required("SYNORA_QA_WEB_URL"), required("SYNORA_QA_API_URL")
    assert all(urlparse(x).hostname in ("localhost","127.0.0.1","::1") for x in (web,api))
    assert required("SYNORA_QA_FIXTURE_POSTS") == "1"
    a,b = required("SYNORA_QA_TOKEN_A"),required("SYNORA_QA_TOKEN_B")
    assert a != b
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(accept_downloads=True)
        try:
            page = context.new_page()
            response = page.goto(web.rstrip("/")+"/studio",wait_until="domcontentloaded")
            assert response and response.ok
            # Requests are issued from the actual web origin, exercising CORS.
            def req(path, token, method="GET", body=None, key=None):
                return page.evaluate("""async ({url,token,method,body,key}) => {
                    const headers = {Authorization:'Bearer '+token};
                    if (body) headers['Content-Type']='application/json';
                    if (key) headers['Idempotency-Key']=key;
                    const r=await fetch(url,{method,headers,body:body?JSON.stringify(body):undefined});
                    return {status:r.status,data:await r.json()};
                }""",dict(url=api.rstrip("/")+path,token=token,method=method,body=body,key=key))
            spec=dict(prompt="Original browser QA fixture",mode="instrumental",genres=[],moods=[],
                      instruments=[],duration_seconds=15,bpm=None,lyrics=None,language=None)
            result=req("/v1/music/jobs",a,"POST",spec,str(uuid4()))
            assert result["status"] == 202
            job=result["data"]["id"]
            assert req("/v1/jobs/"+job,b)["status"] in (403,404)
            deadline=time.monotonic()+90
            while time.monotonic()<deadline:
                result=req("/v1/jobs/"+job,a)
                assert result["status"] == 200
                if result["data"]["status"] in ("succeeded","cancelled","failed"): break
                time.sleep(.5)
            assert result["data"]["status"] == "succeeded"
            assert result["data"]["simulated"] is True
            asset=result["data"]["asset_id"]
            assert req("/v1/assets/"+asset,b)["status"] in (403,404)
            meta=req("/v1/assets/"+asset,a)["data"]
            assert meta["simulated"] is True
            assert urlparse(meta["url"]).hostname in ("localhost","127.0.0.1","::1")
            page.evaluate("""url => {
                const a=document.createElement('audio'); a.controls=true;
                a.id='qa-real-server-audio'; a.src=url; document.body.append(a);
            }""",meta["url"])
            page.locator("#qa-real-server-audio").evaluate("a => a.play()")
            page.wait_for_function("document.querySelector('#qa-real-server-audio').currentTime > 0",timeout=15000)
            # Same cross-origin fetch used by the application download implementation.
            download_bytes=page.evaluate("""async url => {
                const r=await fetch(url); if (!r.ok) throw Error('media fetch failed');
                return Array.from(new Uint8Array(await r.arrayBuffer()));
            }""",meta["url"])
            raw=bytes(download_bytes)
            assert raw[:4]==b"RIFF" and raw[8:12]==b"WAVE"
            download=req("/v1/assets/"+asset+"?download=true",a)["data"]
            assert urlparse(download["url"]).hostname in ("localhost","127.0.0.1","::1")
            page.evaluate("""url => {
                const a=document.createElement('a'); a.href=url; a.textContent='QA server download';
                a.id='qa-server-download'; document.body.append(a);
            }""",download["url"])
            with page.expect_download(timeout=15000) as event:
                page.locator("#qa-server-download").click()
            assert event.value.failure() is None
            assert hashlib.sha256(event.value.path().read_bytes()).digest()==hashlib.sha256(raw).digest()
        finally:
            context.close()
            browser.close()
