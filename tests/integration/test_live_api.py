"""Opt-in black-box tests against an isolated fixture-mode Synora instance."""
import io
import json
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
    if a == b:
        pytest.fail('Use separate authenticated test accounts', pytrace=False)
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


    # Actual HTTP media behavior, not a mocked storage function.
    # Range playback must return identical bytes to the full artifact.
    media_headers = {'Range': 'bytes=0-63'}
    with httpx.Client(timeout=10, follow_redirects=False) as anonymous:
        chunk = anonymous.get(url, headers=media_headers)
        assert chunk.status_code == 206
        assert chunk.headers.get('content-range') == f'bytes 0-63/{len(data)}'
        assert chunk.content == data[:64]
        assert 'no-store' in chunk.headers.get('cache-control', '').lower()
        tail = anonymous.get(url, headers={'Range': 'bytes=-64'})
        assert tail.status_code == 206 and tail.content == data[-64:]
        assert anonymous.get(url, headers={'Range': f'bytes={len(data)}-'}).status_code == 416
        original = dict(parse_qsl(parsed.query))
        mutations = [
            parsed._replace(query=urlencode(original | {'download': '1'})),
            parsed._replace(query=urlencode(original | {'expires': str(int(original['expires'])+1)})),
            parsed._replace(path=parsed.path.rsplit('/',1)[0]+'/'+str(uuid.uuid4())),
        ]
        for mutated in mutations:
            result = anonymous.get(mutated.geturl())
            assert result.status_code == 403
            check_error(result.json())
        # Download must be separately authorized and byte-identical.
        download = client.get(asset_path, params={'download':'true'}, headers=a)
        assert download.status_code == 200
        signed = urlparse(download.json()['url'])
        if signed.netloc != parsed.netloc or signed.scheme != parsed.scheme:
            pytest.fail('Unexpected download host', pytrace=False)
        result = anonymous.get(signed.geturl())
        assert result.status_code == 200
        assert 'attachment' in result.headers.get('content-disposition','').lower()
        assert result.content == data
    for response in (client.get(path, headers=a), client.get(asset_path, headers=a),
                     client.get('/v1/music/library', headers=a)):
        assert response.status_code == 200
        assert 'no-store' in response.headers.get('cache-control','').lower()


def test_malformed_and_oversize_body_does_not_admit_job(client, owners):
    assert setting('SYNORA_QA_FIXTURE_POSTS') == '1'
    a, _ = owners
    key = str(uuid.uuid4())
    headers = a | {'Idempotency-Key': key, 'Content-Type': 'application/json'}
    marker = 'QA-' + str(uuid.uuid4())
    cases = [
        (b'{"prompt":', 422),
        (json.dumps(spec() | {'user_id': str(uuid.uuid4()), 'prompt': marker}).encode(), 422),
        (json.dumps(spec() | {'duration_seconds': True, 'prompt': marker}).encode(), 422),
        (json.dumps(spec() | {'prompt': marker + 'x' * 32768}).encode(), 413),
    ]
    # Compare before/after IDs without adding jobs or touching rate limits.
    def snapshot():
        response = client.get('/v1/music/library', headers=a, params={'limit':100})
        assert response.status_code == 200
        return {item['job']['id'] for item in response.json()['items']}
    before = snapshot()
    for payload, expected in cases:
        response = client.post('/v1/music/jobs', headers=headers, content=payload)
        assert response.status_code == expected
        error = response.json()
        check_error(error)
        assert error['request_id'] == response.headers.get('x-request-id')
        assert 'no-store' in response.headers.get('cache-control','').lower()
        assert marker not in response.text
    assert snapshot() == before


def test_project_owner_isolation_and_untrusted_owner_fields(client, owners):
    assert setting('SYNORA_QA_FIXTURE_POSTS') == '1'
    a, b = owners
    names = ['Independent QA project '+str(uuid.uuid4()) for _ in range(2)]
    ids = []
    for headers, name in zip((a,b),names):
        response = client.post('/v1/projects', json={'name':name}, headers=headers)
        assert response.status_code == 201
        project = response.json()
        uuid.UUID(project['id'])
        assert project['name'] == name
        ids.append(project['id'])
    for index, headers in enumerate((a,b)):
        response = client.get('/v1/projects', headers=headers)
        assert response.status_code == 200
        projects = response.json()
        assert any(p['id'] == ids[index] and p['name'] == names[index] for p in projects)
        assert all(p['id'] != ids[1-index] and p['name'] != names[1-index] for p in projects)
        assert 'no-store' in response.headers.get('cache-control','').lower()
    denied(client.get('/v1/projects'))
    denied(client.post('/v1/projects',json={'name':'unauthorized'}))
    forged = client.post('/v1/projects',json={'name':'forged','user_id':str(uuid.uuid4())},headers=a)
    assert forged.status_code == 422
    check_error(forged.json())
