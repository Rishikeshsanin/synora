"""Opt-in black-box tests against an isolated fixture-mode Synora instance."""
import io
import os
import time
import uuid
import wave
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse

import httpx
import pytest

from test_contract_shapes import check_asset, check_error, check_job, utc


def setting(name):
    value = os.getenv(name)
    if not value:
        if os.getenv('SYNORA_QA_REQUIRE_LIVE') == '1':
            pytest.fail('Missing required QA configuration: ' + name)
        pytest.skip('Live QA blocked: missing ' + name)
    return value


@pytest.fixture
def client():
    base = setting('SYNORA_QA_API_URL')
    assert urlparse(base).hostname in ('localhost', '127.0.0.1', '::1'), 'Local isolated target only'
    with httpx.Client(base_url=base, timeout=10, follow_redirects=False) as c:
        yield c


@pytest.fixture
def owners():
    a, b = setting('SYNORA_QA_TOKEN_A'), setting('SYNORA_QA_TOKEN_B')
    assert a != b, 'Use separate authenticated test accounts'
    return ({'Authorization': 'Bearer ' + a}, {'Authorization': 'Bearer ' + b})


def spec():
    return dict(prompt='QA rights-cleared instrumental fixture', mode='instrumental',
                genres=[], moods=[], instruments=[], duration_seconds=15,
                bpm=None, lyrics=None, language=None)


def denied(response):
    assert response.status_code in (401, 403, 404), response.status_code
    check_error(response.json())


def test_health_and_ready(client):
    for path in ('/health', '/ready'):
        assert client.get(path).status_code == 200


def test_unauthenticated(client):
    denied(client.get('/v1/jobs/' + str(uuid.uuid4())))
    denied(client.get('/v1/assets/' + str(uuid.uuid4())))


@pytest.mark.parametrize('change', [dict(duration_seconds=14), dict(duration_seconds=121),
    dict(bpm=39), dict(bpm=201), dict(mode='invalid'), dict(prompt='')])
def test_invalid_music_request(client, owners, change):
    # Explicit local fixture authorization even for negative POSTs.
    assert setting('SYNORA_QA_FIXTURE_POSTS') == '1'
    response = client.post('/v1/music/jobs', json=spec() | change,
                           headers=owners[0] | {'Idempotency-Key': str(uuid.uuid4())})
    assert response.status_code in (400, 422), response.status_code
    check_error(response.json())


def test_missing_idempotency_key(client, owners):
    assert setting('SYNORA_QA_FIXTURE_POSTS') == '1'
    response = client.post('/v1/music/jobs', json=spec(), headers=owners[0])
    assert response.status_code in (400, 422)
    check_error(response.json())


def test_fixture_job_idempotency_isolation_and_wav(client, owners):
    assert setting('SYNORA_QA_FIXTURE_POSTS') == '1'
    a, b = owners
    headers = a | {'Idempotency-Key': str(uuid.uuid4())}

    def submit():
        response = client.post('/v1/music/jobs', json=spec(), headers=headers)
        assert response.status_code == 202, response.status_code
        job = response.json()
        check_job(job)
        return job

    with ThreadPoolExecutor(max_workers=4) as pool:
        jobs = list(pool.map(lambda _: submit(), range(4)))
    assert len({j['id'] for j in jobs}) == 1, 'Duplicate jobs created for one key'
    # Backend draft #8 proposes 409 for reuse with a different payload.
    conflict = client.post('/v1/music/jobs', json=spec() | {'prompt': 'Different QA prompt'}, headers=headers)
    assert conflict.status_code == 409
    check_error(conflict.json())
    job_id = jobs[0]['id']
    path = '/v1/jobs/' + job_id
    denied(client.get(path, headers=b))
    denied(client.get(path))
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        response = client.get(path, headers=a)
        assert response.status_code == 200
        job = response.json()
        check_job(job)
        assert job['id'] == job_id
        if job['status'] in ('succeeded', 'failed', 'cancelled'):
            break
        time.sleep(0.5)
    assert job['status'] == 'succeeded', 'Fixture job failed or timed out'
    assert job['simulated'] is True
    assert job['progress'] == 100
    asset_path = '/v1/assets/' + job['asset_id']
    denied(client.get(asset_path, headers=b))
    denied(client.get(asset_path))
    response = client.get(asset_path, headers=a)
    assert response.status_code == 200
    asset = response.json()
    check_asset(asset)
    assert asset['id'] == job['asset_id']
    assert asset['kind'] == 'audio' and asset['simulated'] is True
    assert utc(asset['expires_at']) > datetime.now(timezone.utc)
    # Fixture WAV is an explicit QA profile, not a requirement for all real providers.
    assert asset['mime_type'] in ('audio/wav', 'audio/x-wav', 'audio/wave')
    url = urljoin(str(client.base_url), asset['url'])
    assert urlparse(url).hostname in ('localhost', '127.0.0.1', '::1')
    # Candidate backend #8 signs expires, download and asset ID. No credentials sent.
    parsed = urlparse(url)
    query = dict(parse_qsl(parsed.query))
    assert query.get('sig') and query.get('expires')
    query['sig'] = '0' * 64 if query['sig'] != '0' * 64 else '1' * 64
    tampered = parsed._replace(query=urlencode(query)).geturl()
    assert httpx.get(tampered, timeout=10, follow_redirects=False).status_code == 403
    assert httpx.get(parsed._replace(query='').geturl(), timeout=10, follow_redirects=False).status_code in (400, 401, 403, 404, 422)
    with httpx.stream('GET', url, timeout=15, follow_redirects=False) as response:
        assert response.status_code == 200
        data = bytearray()
        for chunk in response.iter_bytes():
            data.extend(chunk)
            assert len(data) <= 32 * 1024 * 1024
    with wave.open(io.BytesIO(data)) as audio:
        frames = audio.getnframes()
        rate = audio.getframerate()
        assert frames > 0 and rate > 0
        assert len(audio.readframes(frames)) == frames * audio.getnchannels() * audio.getsampwidth()
        assert abs(frames / rate - asset['duration_seconds']) <= 0.25
