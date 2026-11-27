"""Native Studio acceptance: no intercepted API requests or injected media elements.

The execution harness owns two authenticated, isolated fixture-only storage states.
This is a genuine UI-to-worker flow, not proof of production Supabase JWT validity.
"""
import hashlib
import io
import os
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4
import wave

import pytest
from playwright.sync_api import sync_playwright, expect


def required(name):
    value = os.getenv(name)
    if not value:
        if os.getenv("SYNORA_QA_REQUIRE_BROWSER") == "1":
            pytest.fail("Missing native Studio QA configuration: " + name)
        pytest.skip("Native Studio QA configuration missing: " + name)
    return value


def test_native_studio_two_authenticated_users():
    web = required("SYNORA_QA_WEB_URL").rstrip("/")
    api = required("SYNORA_QA_API_URL").rstrip("/")
    assert all(urlparse(u).hostname in ("localhost", "127.0.0.1", "::1")
               for u in (web, api))
    assert required("SYNORA_QA_FIXTURE_POSTS") == "1"
    state_a = Path(required("SYNORA_QA_STORAGE_STATE"))
    state_b = Path(required("SYNORA_QA_STORAGE_STATE_B"))
    assert state_a.is_file() and state_b.is_file()
    assert state_a.resolve() != state_b.resolve()
    if state_a.read_bytes() == state_b.read_bytes():
        pytest.fail("Fixture browser states must differ", pytrace=False)
    token_a = required("SYNORA_QA_TOKEN_A")
    token_b = required("SYNORA_QA_TOKEN_B")
    if token_a == token_b:
        pytest.fail("Fixture tokens must differ", pytrace=False)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        contexts = [
            browser.new_context(storage_state=str(s), accept_downloads=True,
                                viewport={"width": 390, "height": 844},
                                reduced_motion="reduce")
            for s in (state_a, state_b)
        ]
        try:
            jobs = []
            assets = []
            prompts = []
            for index, context in enumerate(contexts):
                page = context.new_page()
                response = page.goto(web + "/studio", wait_until="domcontentloaded")
                assert response and response.ok
                expect(page.get_by_role("heading", name="Music Studio")).to_be_visible()
                expect(page.get_by_role("button", name="Sign out")).to_be_visible(timeout=15000)
                expect(page.get_by_label("Explicit local demo")).not_to_be_checked()
                expect(page.get_by_role("button", name="Create server fixture")).to_be_enabled(timeout=15000)
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
                prompt = "Native independent fixture " + str(uuid4()) + " <b>literal</b>"
                prompts.append(prompt)
                page.get_by_label("Describe your sound").fill(prompt)
                with page.expect_response(
                    lambda res: res.url == api + "/v1/music/jobs" and res.request.method == "POST",
                    timeout=20000
                ) as submission:
                    page.get_by_role("button", name="Create server fixture").click()
                result = submission.value
                assert result.status == 202
                # Compare privately; avoid printing credentials or signed URLs.
                if result.request.all_headers().get("authorization") != "Bearer " + (token_a, token_b)[index]:
                    pytest.fail("Unexpected authenticated principal", pytrace=False)
                job = result.json()["id"]
                jobs.append(job)
                expect(page.get_by_text("succeeded · 100%", exact=False)).to_be_visible(timeout=90000)
                expect(page.get_by_text("Server fixture · Not AI-generated", exact=False).first).to_be_visible(timeout=90000)
                audio = page.get_by_label("Track playback")
                expect(audio).to_be_visible()
                expect(audio).to_have_attribute("controls", "")
                src = audio.get_attribute("src")
                assert src and not src.startswith("blob:")
                assert urlparse(src).hostname in ("localhost", "127.0.0.1", "::1")
                # Native media element belonging to the actual app (not injected).
                audio.evaluate("el => el.play()")
                page.wait_for_function("document.querySelector('audio').currentTime > 0", timeout=15000)
                with page.expect_download(timeout=20000) as event:
                    page.get_by_role("button", name="Download audio").click()
                artifact = event.value
                assert artifact.failure() is None
                payload = artifact.path().read_bytes()
                with wave.open(io.BytesIO(payload)) as wav:
                    assert wav.getnframes() > 0
                    assert wav.getframerate() > 0
                    assert wav.getnframes() / wav.getframerate() >= 15
                own = context.request.get(api + "/v1/jobs/" + job, headers={
                    "Authorization": "Bearer " + (token_a, token_b)[index]
                })
                assert own.status == 200 and own.json()["status"] == "succeeded"
                assert own.json()["simulated"] is True
                asset = own.json()["asset_id"]
                assets.append(asset)
                metadata = context.request.get(api + "/v1/assets/" + asset, headers={
                    "Authorization": "Bearer " + (token_a, token_b)[index]
                })
                assert metadata.status == 200
                assert metadata.json()["simulated"] is True
                signed = metadata.json()["url"]
                assert urlparse(signed).hostname in ("localhost", "127.0.0.1", "::1")
                media = context.request.get(signed)
                assert media.status == 200
                assert hashlib.sha256(media.body()).digest() == hashlib.sha256(payload).digest()
            assert jobs[0] != jobs[1] and assets[0] != assets[1]
            for index, context in enumerate(contexts):
                other = 1 - index
                headers = {"Authorization": "Bearer " + (token_a, token_b)[index]}
                for route in ("/v1/jobs/" + jobs[other], "/v1/assets/" + assets[other]):
                    assert context.request.get(api + route, headers=headers).status in (403, 404)
                page = context.pages[0]
                page.reload(wait_until="domcontentloaded")
                page.get_by_role("button", name="Creative Library").click()
                own_track = page.get_by_test_id("library-track-" + jobs[index])
                expect(own_track).to_be_visible(timeout=20000)
                expect(page.get_by_test_id("library-track-" + jobs[other])).to_have_count(0)
                expect(own_track).to_contain_text("Server fixture · Not AI-generated")
                expect(own_track).to_contain_text(prompts[index])
                expect(page.get_by_text(prompts[other], exact=True)).to_have_count(0)
                # User prompt must remain text, not interpreted markup.
                expect(own_track.locator("b")).to_have_count(0)
                with page.expect_response(lambda res: res.url.split("?")[0] == api + "/v1/assets/" + assets[index]
                                          and res.request.method == "GET", timeout=20000) as fresh:
                    own_track.click()
                assert fresh.value.status == 200
                expect(page.get_by_label("Track playback")).to_be_visible()
                # A second page in the same browser session must clear account data too.
                second = context.new_page()
                second.goto(web + "/studio", wait_until="domcontentloaded")
                second.get_by_role("button", name="Creative Library").click()
                expect(second.get_by_test_id("library-track-" + jobs[index])).to_be_visible(timeout=20000)
                page.get_by_role("button", name="Music Studio").click()
                page.get_by_role("button", name="Sign out").click()
                expect(page.get_by_role("button", name="Send sign-in link")).to_be_visible(timeout=15000)
                expect(page.get_by_label("Track playback")).to_have_count(0)
                page.get_by_role("button", name="Creative Library").click()
                expect(page.get_by_test_id("library-track-" + jobs[index])).to_have_count(0)
                expect(page.get_by_label("Track playback")).to_have_count(0)
                expect(second.get_by_text("Sign in to see saved tracks.")).to_be_visible(timeout=15000)
                expect(second.get_by_test_id("library-track-" + jobs[index])).to_have_count(0)
                expect(second.get_by_label("Track playback")).to_have_count(0)
                second.close()
        finally:
            for context in contexts:
                context.close()
            browser.close()
