"""The implicit (deprecated) Sentry integration must engage only when Sentry is in use."""

import importlib.metadata
import warnings

import pytest

sentry_sdk_version = importlib.metadata.version("sentry_sdk")
if not sentry_sdk_version.startswith("2."):
    pytest.skip(f"Testset is only for sentry_sdk 2.x, given {sentry_sdk_version=}", allow_module_level=True)

DEPRECATION_MESSAGE = 'Implicit Sentry integration is deprecated'


@pytest.fixture
def probe_router(ep):
    @ep.method(name='probe')
    async def probe() -> dict:
        return {'success': True}


def _implicit_integration_warnings(record):
    return [str(w.message) for w in record if DEPRECATION_MESSAGE in str(w.message)]


def test_no_warning_when_sentry_not_initialized(json_request, probe_router):
    with warnings.catch_warnings(record=True) as record:
        warnings.simplefilter('always')
        response = json_request({'method': 'probe', 'params': {}, 'jsonrpc': '2.0', 'id': 1})

    assert response == {'result': {'success': True}, 'jsonrpc': '2.0', 'id': 1}
    assert _implicit_integration_warnings(record) == []


def test_warns_when_sentry_initialized_without_integration(
    json_request, probe_router, sentry_no_integration,
):
    with warnings.catch_warnings(record=True) as record:
        warnings.simplefilter('always')
        response = json_request({'method': 'probe', 'params': {}, 'jsonrpc': '2.0', 'id': 1})

    assert response == {'result': {'success': True}, 'jsonrpc': '2.0', 'id': 1}
    assert len(_implicit_integration_warnings(record)) == 1


def test_no_warning_when_explicit_integration_used(
    json_request, probe_router, sentry_with_integration,
):
    with warnings.catch_warnings(record=True) as record:
        warnings.simplefilter('always')
        response = json_request({'method': 'probe', 'params': {}, 'jsonrpc': '2.0', 'id': 1})

    assert response == {'result': {'success': True}, 'jsonrpc': '2.0', 'id': 1}
    assert _implicit_integration_warnings(record) == []
