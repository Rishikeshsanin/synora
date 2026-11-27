"""Local Playwright acceptance; selectors are proposed QA hooks, not ratified contracts."""
import os
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
    instance, url = browser
    asset_url = setting('SYNORA_QA_FIXTURE_PAGE_URL')
    assert urlparse(asset_url).hostname == urlparse(url).hostname
    context = instance.new_context(storage_state=setting('SYNORA_QA_STORAGE_STATE'),
                                   accept_downloads=True)
    try:
        page = context.new_page()
        response = page.goto(asset_url, wait_until='domcontentloaded')
        assert response and response.ok
        disclosure = page.get_by_test_id('generation-provenance')
        expect(disclosure).to_be_visible()
        expect(disclosure).to_contain_text('simulated', ignore_case=True)
        page.get_by_test_id('audio-play').click()
        page.wait_for_function("""() => Array.from(document.querySelectorAll('audio'))
            .some(a => !a.paused && a.currentTime > 0)""", timeout=15000)
        with page.expect_download(timeout=15000) as download:
            page.get_by_test_id('audio-download').click()
        artifact = download.value
        assert artifact.failure() is None
        assert artifact.path().stat().st_size > 0
    finally:
        context.close()
