import contextlib
from json import dumps as json_dumps

from fastapi import HTTPException

from fastapi_jsonrpc import JsonRpcContext


def test_method(ep, raw_request):
    @ep.method()
    def probe() -> str:
        raise HTTPException(401)

    resp = raw_request(json_dumps({
        'id': 1,
        'jsonrpc': '2.0',
        'method': 'probe',
        'params': {},
    }))

    assert resp.status_code == 401
    assert resp.json() == {'detail': 'Unauthorized'}


def test_ep_middleware_enter(ep, raw_request):
    @contextlib.asynccontextmanager
    async def middleware(_ctx: JsonRpcContext):
        raise HTTPException(401)
        # noinspection PyUnreachableCode
        yield

    ep.middlewares.append(middleware)

    @ep.method()
    def probe() -> str:
        return 'qwe'

    resp = raw_request(json_dumps({
        'id': 1,
        'jsonrpc': '2.0',
        'method': 'probe',
        'params': {},
    }))

    assert resp.status_code == 401
    assert resp.json() == {'detail': 'Unauthorized'}


def test_ep_middleware_exit(ep, raw_request):
    @contextlib.asynccontextmanager
    async def middleware(_ctx: JsonRpcContext):
        yield
        raise HTTPException(401)

    ep.middlewares.append(middleware)

    @ep.method()
    def probe() -> str:
        return 'qwe'

    resp = raw_request(json_dumps({
        'id': 1,
        'jsonrpc': '2.0',
        'method': 'probe',
        'params': {},
    }))

    assert resp.status_code == 401
    assert resp.json() == {'detail': 'Unauthorized'}


def test_method_middleware_enter(ep, raw_request):
    @contextlib.asynccontextmanager
    async def middleware(_ctx: JsonRpcContext):
        raise HTTPException(401)
        # noinspection PyUnreachableCode
        yield

    @ep.method(middlewares=[middleware])
    def probe() -> str:
        return 'qwe'

    resp = raw_request(json_dumps({
        'id': 1,
        'jsonrpc': '2.0',
        'method': 'probe',
        'params': {},
    }))

    assert resp.status_code == 401
    assert resp.json() == {'detail': 'Unauthorized'}


def test_method_middleware_exit(ep, raw_request):
    @contextlib.asynccontextmanager
    async def middleware(_ctx: JsonRpcContext):
        yield
        raise HTTPException(401)

    @ep.method(middlewares=[middleware])
    def probe() -> str:
        return 'qwe'

    resp = raw_request(json_dumps({
        'id': 1,
        'jsonrpc': '2.0',
        'method': 'probe',
        'params': {},
    }))

    assert resp.status_code == 401
    assert resp.json() == {'detail': 'Unauthorized'}
