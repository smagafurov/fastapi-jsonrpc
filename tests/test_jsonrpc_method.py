import pytest
from fastapi import Depends

from fastapi_jsonrpc import get_jsonrpc_method


@pytest.fixture
def probe(ep):
    @ep.method()
    def probe(
        jsonrpc_method: str = Depends(get_jsonrpc_method),
    ) -> str:
        return jsonrpc_method

    @ep.method()
    def probe2(
        jsonrpc_method: str = Depends(get_jsonrpc_method),
    ) -> str:
        return jsonrpc_method

    return ep


def test_basic(probe, json_request):
    resp = json_request({
        'id': 123,
        'jsonrpc': '2.0',
        'method': 'probe',
        'params': {},
    })
    assert resp == {'id': 123, 'jsonrpc': '2.0', 'result': 'probe'}


def test_batch(probe, json_request):
    resp = json_request([
        {
            'id': 1,
            'jsonrpc': '2.0',
            'method': 'probe',
            'params': {},
        },
        {
            'id': 2,
            'jsonrpc': '2.0',
            'method': 'probe2',
            'params': {},
        },
    ])
    assert resp == [
        {'id': 1, 'jsonrpc': '2.0', 'result': 'probe'},
        {'id': 2, 'jsonrpc': '2.0', 'result': 'probe2'},
    ]
