from json import dumps as json_dumps

import pytest
from fastapi import Body, Response


@pytest.fixture
def probe_ep(ep):
    @ep.method()
    def probe(
        response: Response,
        data: str = Body(..., example='123'),
    ) -> str:
        response.set_cookie(key='probe-cookie', value=data)
        response.status_code = 404
        return data

    return ep


def test_basic(probe_ep, raw_request):
    body = json_dumps({
        'id': 1,
        'jsonrpc': '2.0',
        'method': 'probe',
        'params': {'data': 'data-123'},
    })
    response = raw_request(body)
    assert response.cookies['probe-cookie'] == 'data-123'
    assert response.status_code == 404
