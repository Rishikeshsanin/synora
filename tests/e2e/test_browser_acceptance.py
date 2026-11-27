"""Local Playwright acceptance; selectors are proposed QA hooks, not ratified contracts."""
import os
import hashlib
import io
import wave
from urllib.parse import urlparse

import pytest
from playwright.sync_api import sync_playwright, expect


def setting(name):
    value = os.getenv(name)
    if not value:
        if os.getenv('SYNORA_QA_REQUIRE_BROWSER') == '1':
            pytest.fail('Missing required browser configuration: ' + name)
        pytest.skip('Browser QA blocked: missing ' + name)
    return value


@pytest.fixture
def browser():
    url = setting('SYNORA_QA_WEB_URL')
    assert urlparse(url).hostname in ('localhost', '127.0.0.1', '::1')
    with sync_playwright() as p:
        instance = p.chromium.launch()
        yield instance, url
        instance.close()


@pytest.mark.parametrize('width,height', [(320, 800), (390, 844), (768, 1024), (1440, 900)])
def test_landing_layout_and_keyboard(browser, width, height):
    instance, url = browser
    context = instance.new_context(viewport={'width': width, 'height': height})
    try:
        page = context.new_page()
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        response = page.goto(url, wait_until='domcontentloaded')
        assert response and response.ok
        expect(page.locator('main')).to_be_visible()
        expect(page.get_by_role('heading', level=1)).to_be_visible()
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
        page.keyboard.press('Tab')
        assert page.evaluate("""() => {
          const e = document.activeElement;
          return e && e !== document.body && e.getBoundingClientRect().width > 0;
        }""")
        assert not errors
    finally:
        context.close()


def test_existing_fixture_playback_download_and_disclosure(browser):
    """A seeded server job must survive page reload and use native app controls."""
    instance, url = browser
    asset_url = setting('SYNORA_QA_FIXTURE_PAGE_URL')
    api = setting('SYNORA_QA_API_URL').rstrip('/')
    job_id = setting('SYNORA_QA_FIXTURE_JOB_ID')
    token = setting('SYNORA_QA_TOKEN_A')
    assert urlparse(asset_url).netloc == urlparse(url).netloc
    assert urlparse(api).hostname in ('localhost', '127.0.0.1', '::1')
    context = instance.new_context(storage_state=setting('SYNORA_QA_STORAGE_STATE'),
                                   accept_downloads=True)
    try:
        page = context.new_page()
        response = page.goto(asset_url, wait_until='domcontentloaded')
        assert response and response.ok
        headers = {'Authorization': 'Bearer ' + token}
        job = context.request.get(api + '/v1/jobs/' + job_id, headers=headers)
        assert job.status == 200
        body = job.json()
        assert body['status'] == 'succeeded' and body['simulated'] is True
        asset_id = body['asset_id']
        # No generation or injected audio is permitted in this persisted-result gate.
        posts = []
        page.on('request', lambda req: posts.append(req.method)
                if req.method == 'POST' and '/v1/music/jobs' in req.url else None)
        for _ in range(2):
            expect(page.get_by_role('button', name='Creative Library')).to_be_visible()
            page.get_by_role('button', name='Creative Library').click()
            track = page.get_by_test_id('library-track-' + job_id)
            expect(track).to_be_visible(timeout=20000)
            expect(track).to_contain_text('Server fixture · Not AI-generated')
            track.click()
            audio = page.get_by_label('Track playback')
            expect(audio).to_be_visible()
            src = audio.get_attribute('src')
            if not src or src.startswith('blob:') or urlparse(src).hostname not in ('localhost','127.0.0.1','::1'):
                pytest.fail('Persisted track did not expose local signed server media', pytrace=False)
            audio.evaluate('a => a.play()')
            page.wait_for_function("document.querySelector('audio').currentTime > 0", timeout=15000)
            with page.expect_download(timeout=20000) as download:
                page.get_by_role('button', name='Download audio').click()
            artifact = download.value
            assert artifact.failure() is None
            payload = artifact.path().read_bytes()
            with wave.open(io.BytesIO(payload)) as wav:
                assert wav.getnframes() > 0 and wav.getframerate() > 0
            meta = context.request.get(api + '/v1/assets/' + asset_id, headers=headers)
            assert meta.status == 200 and meta.json()['simulated'] is True
            signed = meta.json()['url']
            if urlparse(signed).hostname not in ('localhost','127.0.0.1','::1'):
                pytest.fail('Unexpected media host', pytrace=False)
            server = context.request.get(signed)
            assert server.status == 200
            assert hashlib.sha256(payload).digest() == hashlib.sha256(server.body()).digest()
            page.reload(wait_until='domcontentloaded')
        assert not posts, 'Persisted playback must not generate a replacement job'
    finally:
        context.close()


def test_candidate_frontend_local_preview(browser):
    """PR #9 dc439e8: explicitly simulated, no server job or provider call."""
    instance, url = browser
    context = instance.new_context(accept_downloads=True)
    try:
        page = context.new_page()
        posts = []
        page.on('request', lambda request: posts.append(request.url)
                if request.method == 'POST' and '/v1/music/jobs' in request.url else None)
        response = page.goto(url.rstrip('/') + '/studio', wait_until='domcontentloaded')
        assert response and response.ok
        page.get_by_label('Explicit local demo').check()
        page.get_by_label('Describe your sound').fill('Original QA fixture preview')
        page.get_by_role('button', name='Play local fixture').click()
        expect(page.get_by_text('Local fixture · Not AI-generated', exact=False).first).to_be_visible()
        expect(page.get_by_text('Simulated development output:', exact=False)).to_be_visible()
        audio = page.locator('audio')
        expect(audio).to_have_count(1)
        audio.evaluate('a => a.play()')
        page.wait_for_function("document.querySelector('audio').currentTime > 0")
        with page.expect_download(timeout=15000) as download:
            page.get_by_role('button', name='Download audio').click()
        artifact = download.value
        assert artifact.failure() is None
        with artifact.path().open('rb') as f:
            header = f.read(12)
        assert header[:4] == b'RIFF' and header[8:12] == b'WAVE'
        assert not posts, 'Local demo must not submit a provider job'
    finally:
        context.close()
