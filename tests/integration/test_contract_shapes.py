"""Independent contract validators; fixtures are NOT product output."""
import uuid
from datetime import datetime, timedelta

import pytest


def utc(value):
    assert isinstance(value, str)
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    assert parsed.utcoffset() == timedelta(0)
    return parsed


def identifier(value):
    assert isinstance(value, str)
    uuid.UUID(value)


def check_job(job):
    identifier(job['id'])
    assert job['status'] in {'queued', 'running', 'succeeded', 'failed', 'cancelled'}
    assert type(job['progress']) in (int, float) and 0 <= job['progress'] <= 100
    assert utc(job['created_at']) <= utc(job['updated_at'])
    assert type(job['simulated']) is bool
    assert job['provider'] is None or isinstance(job['provider'], str)
    if job['asset_id'] is not None:
        identifier(job['asset_id'])
    if job['error'] is not None:
        assert isinstance(job['error']['code'], str) and job['error']['code']
        assert isinstance(job['error']['message'], str) and job['error']['message']
    if job['status'] == 'succeeded':
        assert job['asset_id'] is not None and job['error'] is None
    if job['status'] == 'failed':
        assert job['error'] is not None


def check_asset(asset):
    identifier(asset['id'])
    assert asset['kind'] in {'audio', 'video', 'image'}
    assert asset['mime_type'].startswith(asset['kind'] + '/')
    assert isinstance(asset['url'], str) and asset['url']
    utc(asset['expires_at'])
    assert type(asset['simulated']) is bool
    if asset['kind'] != 'image':
        assert type(asset['duration_seconds']) in (float, int) and asset['duration_seconds'] > 0


def check_error(body):
    for key in ('code', 'message', 'request_id'):
        assert isinstance(body[key], str) and body[key]


@pytest.fixture
def job():
    return dict(id=str(uuid.uuid4()), status='queued', progress=0, asset_id=None,
                error=None, created_at='2026-01-01T00:00:00Z',
                updated_at='2026-01-01T00:00:00Z', provider=None, simulated=True)


def test_queued_fixture(job):
    check_job(job)


@pytest.mark.parametrize('change', [dict(status='complete'), dict(progress=101),
    dict(progress=-1), dict(progress=True), dict(simulated='false'),
    dict(updated_at='2025-01-01T00:00:00Z'), dict(status='succeeded'),
    dict(status='failed'), dict(created_at='2026-01-01T00:00:00')])
def test_reject_invalid_job_fixture(job, change):
    with pytest.raises((AssertionError, ValueError)):
        check_job(job | change)


def test_success_fixture(job):
    check_job(job | dict(status='succeeded', progress=100, asset_id=str(uuid.uuid4())))


def test_failure_fixture(job):
    check_job(job | dict(status='failed', error=dict(code='provider_error', message='fixture failure')))


def test_asset_and_error_fixtures():
    asset = dict(id=str(uuid.uuid4()), kind='audio', mime_type='audio/wav',
                 duration_seconds=15, url='https://example.invalid/fixture',
                 expires_at='2026-01-01T00:00:00Z', simulated=True)
    check_asset(asset)
    with pytest.raises(AssertionError):
        check_asset(asset | dict(duration_seconds=0))
    with pytest.raises(AssertionError):
        check_asset(asset | dict(simulated='true'))
    check_error(dict(code='bad_request', message='invalid', request_id='fixture'))
    with pytest.raises(KeyError):
        check_error(dict(code='bad_request', message='invalid'))
