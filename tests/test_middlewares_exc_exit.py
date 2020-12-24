import contextlib
from collections import defaultdict

import pytest
from fastapi import Body

import fastapi_jsonrpc as jsonrpc


@pytest.fixture
def ep(ep_path):
    _calls = defaultdict(list)

    @contextlib.asynccontextmanager
    async def mw_first(ctx: jsonrpc.JsonRpcContext):
        nonlocal _calls
        _calls[ctx.raw_request.get('id')].append(('mw_first', 'enter', ctx.raw_request, ctx.raw_response))
        yield
        _calls[ctx.raw_response.get('id')].append(('mw_first', 'exit', ctx.raw_request, ctx.raw_response))

    @contextlib.asynccontextmanager
    async def mw_exception_exit(ctx: jsonrpc.JsonRpcContext):
        nonlocal _calls
        _calls[ctx.raw_request.get('id')].append(('mw_exception_exit', 'enter', ctx.raw_request, ctx.raw_response))
        # noinspection PyUnreachableCode
        yield
        _calls[ctx.raw_response.get('id')].append(('mw_exception_exit', 'exit', ctx.raw_request, ctx.raw_response))
        raise RuntimeError

    @contextlib.asynccontextmanager
    async def mw_last(ctx: jsonrpc.JsonRpcContext):
        nonlocal _calls
        _calls[ctx.raw_request.get('id')].append(('mw_last', 'enter', ctx.raw_request, ctx.raw_response))
        yield
        _calls[ctx.raw_response.get('id')].append(('mw_last', 'exit', ctx.raw_request, ctx.raw_response))

    ep = jsonrpc.Entrypoint(
        ep_path,
        jsonrpc_middlewares=[mw_first, mw_exception_exit, mw_last],
    )

    @ep.method()
    def probe(
        data: str = Body(..., example='123'),
    ) -> str:
        return data

    ep.calls = _calls

    return ep


def test_ep_exception(ep, method_request):
    resp = method_request('probe', {'data': 'one'}, request_id=111)
    assert resp == {'id': 111, 'jsonrpc': '2.0', 'error': {'code': -32603, 'message': 'Internal error'}}
    assert ep.calls == {
        111: [
            (
                'mw_first',
                'enter',
                {
                    'id': 111,
                    'jsonrpc': '2.0',
                    'method': 'probe',
                    'params': {'data': 'one'},
                },
                None,
            ),
            (
                'mw_exception_exit',
                'enter',
                {
                    'id': 111,
                    'jsonrpc': '2.0',
                    'method': 'probe',
                    'params': {'data': 'one'}
                },
                None,
            ),
            (
                'mw_last',
                'enter',
                {
                    'id': 111,
                    'jsonrpc': '2.0',
                    'method': 'probe',
                    'params': {'data': 'one'},
                },
                None,
            ),
            (
                'mw_last',
                'exit',
                {
                    'id': 111,
                    'jsonrpc': '2.0',
                    'method': 'probe',
                    'params': {'data': 'one'},
                },
                {'id': 111, 'jsonrpc': '2.0', 'result': 'one'},
            ),
            (
                'mw_exception_exit',
                'exit',
                {
                    'id': 111,
                    'jsonrpc': '2.0',
                    'method': 'probe',
                    'params': {'data': 'one'}
                },
                {'id': 111, 'jsonrpc': '2.0', 'result': 'one'},
            ),
            (
                'mw_first',
                'exit',
                {
                    'id': 111,
                    'jsonrpc': '2.0',
                    'method': 'probe',
                    'params': {'data': 'one'}
                },
                {'id': 111, 'jsonrpc': '2.0', 'error': {'code': -32603, 'message': 'Internal error'}},
            ),
        ]
    }
