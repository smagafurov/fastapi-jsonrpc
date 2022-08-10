from unittest.mock import ANY

import pytest
from fastapi import Depends, Body, Header
from typing import Tuple

import fastapi_jsonrpc as jsonrpc


@pytest.fixture
def ep(ep_path):
    _shared_counter = 0
    _common_counter = 0

    def get_shared_counter(
        shared: str = Header('shared'),
    ) -> str:
        nonlocal _shared_counter
        _shared_counter += 1
        return f'{shared}-{_shared_counter}'

    def get_common_counter(
        common: str = Body(...),
    ) -> Tuple[str, int]:
        nonlocal _common_counter
        _common_counter += 1
        return common, _common_counter

    ep = jsonrpc.Entrypoint(
        ep_path,
        dependencies=[Depends(get_shared_counter)],
        common_dependencies=[Depends(get_common_counter)],
    )

    @ep.method()
    def probe(
        shared_counter: str = Depends(get_shared_counter),
        common_counter: Tuple[str, int] = Depends(get_common_counter),
    ) -> Tuple[str, str, int]:
        return shared_counter, common_counter[0], common_counter[1]

    return ep


def test_single(method_request):
    resp1 = method_request('probe', {'common': 'one'}, request_id=111)
    resp2 = method_request('probe', {'common': 'two'}, request_id=222)
    resp3 = method_request('probe', {'common': 'three'}, request_id=333)
    assert [resp1, resp2, resp3] == [
        {'id': 111, 'jsonrpc': '2.0', 'result': ['shared-1', 'one', 1]},
        {'id': 222, 'jsonrpc': '2.0', 'result': ['shared-2', 'two', 2]},
        {'id': 333, 'jsonrpc': '2.0', 'result': ['shared-3', 'three', 3]},
    ]


def test_batch(json_request):
    resp = json_request([
        {
            'id': 111,
            'jsonrpc': '2.0',
            'method': 'probe',
            'params': {'common': 'one'},
        },
        {
            'id': 222,
            'jsonrpc': '2.0',
            'method': 'probe',
            'params': {'common': 'two'},
        },
        {
            'id': 333,
            'jsonrpc': '2.0',
            'method': 'probe',
            'params': {'common': 'three'},
        },
    ])
    assert resp == [
        {'id': 111, 'jsonrpc': '2.0', 'result': ['shared-1', 'one', ANY]},
        {'id': 222, 'jsonrpc': '2.0', 'result': ['shared-1', 'two', ANY]},
        {'id': 333, 'jsonrpc': '2.0', 'result': ['shared-1', 'three', ANY]},
    ]
    assert set(r['result'][2] for r in resp) == {1, 2, 3}
