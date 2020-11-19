import pytest
from fastapi import Depends

from fastapi_jsonrpc import get_jsonrpc_request_id


@pytest.fixture
def probe(ep):
    @ep.method()
    def probe(
        jsonrpc_request_id: int = Depends(get_jsonrpc_request_id),
    ) -> int:
        return jsonrpc_request_id
    return ep


def test_basic(probe, json_request):
    resp = json_request({
        'id': 123,
        'jsonrpc': '2.0',
        'method': 'probe',
        'params': {},
    })
    assert resp == {'id': 123, 'jsonrpc': '2.0', 'result': 123}


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
            'method': 'probe',
            'params': {},
        },
    ])
    assert resp == [
        {'id': 1, 'jsonrpc': '2.0', 'result': 1},
        {'id': 2, 'jsonrpc': '2.0', 'result': 2},
    ]
