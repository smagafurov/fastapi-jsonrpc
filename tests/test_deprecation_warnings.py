import warnings

import pytest
from fastapi import Body

import fastapi_jsonrpc as jsonrpc


@pytest.fixture
def ep(ep_path):
    ep = jsonrpc.Entrypoint(ep_path)

    @ep.method()
    def probe_sync(value: int = Body(...)) -> int:
        return value

    @ep.method()
    async def probe_async(value: int = Body(...)) -> int:
        return value

    return ep


@pytest.mark.parametrize('method', ['probe_sync', 'probe_async'])
def test_dispatch_does_not_warn(json_request, method):
    with warnings.catch_warnings(record=True) as record:
        warnings.simplefilter('always')
        resp = json_request({'id': 1, 'jsonrpc': '2.0', 'method': method, 'params': {'value': 5}})

    assert resp == {'id': 1, 'jsonrpc': '2.0', 'result': 5}

    from_library = [
        f'{w.filename}:{w.lineno}: {w.message}'
        for w in record
        if issubclass(w.category, DeprecationWarning) and 'fastapi_jsonrpc' in w.filename
    ]
    assert from_library == []
