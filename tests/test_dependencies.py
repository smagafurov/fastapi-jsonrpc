import pytest
from fastapi import Depends, Body, Header
from typing import List

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
    ) -> str:
        nonlocal _common_counter
        _common_counter += 1
        return f'{common}-{_common_counter}'

    ep = jsonrpc.Entrypoint(
        ep_path,
        dependencies=[Depends(get_shared_counter)],
        common_dependencies=[Depends(get_common_counter)],
    )

    @ep.method()
    def probe(
        shared_counter: str = Depends(get_shared_counter),
        common_counter: str = Depends(get_common_counter),
    ) -> List[str]:
        return [shared_counter, common_counter]

    return ep


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
        {'id': 111, 'jsonrpc': '2.0', 'result': ['shared-1', 'one-1']},
        {'id': 222, 'jsonrpc': '2.0', 'result': ['shared-1', 'two-2']},
        {'id': 333, 'jsonrpc': '2.0', 'result': ['shared-1', 'three-3']},
    ]
