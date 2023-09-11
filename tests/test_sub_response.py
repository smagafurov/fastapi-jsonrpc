import contextlib
from json import dumps as json_dumps

import pytest
from fastapi import Body, Response

from fastapi_jsonrpc import JsonRpcContext


@pytest.fixture
def probe_ep(ep):
    @contextlib.asynccontextmanager
    async def ep_middleware(ctx: JsonRpcContext):
        ctx.http_response.set_cookie(key='ep_middleware_enter', value='1')
        yield
        ctx.http_response.set_cookie(key='ep_middleware_exit', value='2')

    ep.middlewares.append(ep_middleware)

    @contextlib.asynccontextmanager
    async def method_middleware(ctx: JsonRpcContext):
        ctx.http_response.set_cookie(key='method_middleware_enter', value='3')
        yield
        ctx.http_response.set_cookie(key='method_middleware_exit', value='4')

    @ep.method(middlewares=[method_middleware])
    def probe(
        http_response: Response,
        data: str = Body(..., examples=['123']),
    ) -> str:
        http_response.set_cookie(key='probe-cookie', value=data)
        http_response.status_code = 404
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
    assert response.cookies['ep_middleware_enter'] == '1'
    assert response.cookies['ep_middleware_exit'] == '2'
    assert response.cookies['method_middleware_enter'] == '3'
    assert response.cookies['method_middleware_exit'] == '4'
    assert response.status_code == 404
