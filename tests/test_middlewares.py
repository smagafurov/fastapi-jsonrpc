import contextlib
from collections import defaultdict

import pytest
from fastapi import Body

import fastapi_jsonrpc as jsonrpc


@pytest.fixture
def ep(ep_path):
    _calls = defaultdict(list)

    @contextlib.asynccontextmanager
    async def ep_middleware(ctx: jsonrpc.JsonRpcContext):
        nonlocal _calls
        _calls[ctx.raw_request.get('id')].append(('ep_middleware', 'enter', ctx.raw_request, ctx.raw_response))
        yield
        _calls[ctx.raw_response.get('id')].append(('ep_middleware', 'exit', ctx.raw_request, ctx.raw_response))

    @contextlib.asynccontextmanager
    async def method_middleware(ctx):
        nonlocal _calls
        _calls[ctx.raw_request.get('id')].append(('method_middleware', 'enter', ctx.raw_request, ctx.raw_response))
        yield
        _calls[ctx.raw_response.get('id')].append(('method_middleware', 'exit', ctx.raw_request, ctx.raw_response))

    ep = jsonrpc.Entrypoint(
        ep_path,
        jsonrpc_middlewares=[ep_middleware],
    )

    @ep.method(jsonrpc_middlewares=[method_middleware])
    def probe(
        data: str = Body(..., example='123'),
    ) -> str:
        return data

    @ep.method(jsonrpc_middlewares=[method_middleware])
    def probe_error(
    ) -> str:
        raise RuntimeError('qwe')

    ep.calls = _calls

    return ep


def test_single(ep, method_request):
    resp = method_request('probe', {'data': 'one'}, request_id=111)
    assert resp == {'id': 111, 'jsonrpc': '2.0', 'result': 'one'}
    assert ep.calls == {
        111: [
            (
                'ep_middleware',
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
                'method_middleware',
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
                'method_middleware',
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
                'ep_middleware',
                'exit',
                {
                    'id': 111,
                    'jsonrpc': '2.0',
                    'method': 'probe',
                    'params': {'data': 'one'}
                },
                {'id': 111, 'jsonrpc': '2.0', 'result': 'one'},
            )
        ]
    }


def test_single_error(ep, method_request):
    resp = method_request('probe_error', {'data': 'one'}, request_id=111)
    assert resp == {'id': 111, 'jsonrpc': '2.0', 'error': {'code': -32603, 'message': 'Internal error'}}
    assert ep.calls == {
        111: [
            (
                'ep_middleware',
                'enter',
                {
                    'id': 111,
                    'jsonrpc': '2.0',
                    'method': 'probe_error',
                    'params': {'data': 'one'},
                },
                None,
            ),
            (
                'method_middleware',
                'enter',
                {
                    'id': 111,
                    'jsonrpc': '2.0',
                    'method': 'probe_error',
                    'params': {'data': 'one'}
                },
                None,
            ),
            (
                'method_middleware',
                'exit',
                {
                    'id': 111,
                    'jsonrpc': '2.0',
                    'method': 'probe_error',
                    'params': {'data': 'one'}
                },
                {'id': 111, 'jsonrpc': '2.0', 'error': {'code': -32603, 'message': 'Internal error'}},
            ),
            (
                'ep_middleware',
                'exit',
                {
                    'id': 111,
                    'jsonrpc': '2.0',
                    'method': 'probe_error',
                    'params': {'data': 'one'}
                },
                {'id': 111, 'jsonrpc': '2.0', 'error': {'code': -32603, 'message': 'Internal error'}},
            )
        ]
    }


def test_batch(ep, json_request):
    resp = json_request([
        {
            'id': 111,
            'jsonrpc': '2.0',
            'method': 'probe',
            'params': {'data': 'one'},
        },
        {
            'id': 222,
            'jsonrpc': '2.0',
            'method': 'probe',
            'params': {'data': 'two'},
        },
    ])
    assert resp == [
        {'id': 111, 'jsonrpc': '2.0', 'result': 'one'},
        {'id': 222, 'jsonrpc': '2.0', 'result': 'two'},
    ]
    assert ep.calls == {
        111: [
            (
                'ep_middleware',
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
                'method_middleware',
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
                'method_middleware',
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
                'ep_middleware',
                'exit',
                {
                    'id': 111,
                    'jsonrpc': '2.0',
                    'method': 'probe',
                    'params': {'data': 'one'}
                },
                {'id': 111, 'jsonrpc': '2.0', 'result': 'one'},
            )
        ],
        222: [
            (
                'ep_middleware',
                'enter',
                {
                    'id': 222,
                    'jsonrpc': '2.0',
                    'method': 'probe',
                    'params': {'data': 'two'},
                },
                None,
            ),
            (
                'method_middleware',
                'enter',
                {
                    'id': 222,
                    'jsonrpc': '2.0',
                    'method': 'probe',
                    'params': {'data': 'two'}
                },
                None,
            ),
            (
                'method_middleware',
                'exit',
                {
                    'id': 222,
                    'jsonrpc': '2.0',
                    'method': 'probe',
                    'params': {'data': 'two'}
                },
                {'id': 222, 'jsonrpc': '2.0', 'result': 'two'},
            ),
            (
                'ep_middleware',
                'exit',
                {
                    'id': 222,
                    'jsonrpc': '2.0',
                    'method': 'probe',
                    'params': {'data': 'two'}
                },
                {'id': 222, 'jsonrpc': '2.0', 'result': 'two'},
            )
        ]
    }


def test_batch_error(ep, json_request):
    resp = json_request([
        {
            'id': 111,
            'jsonrpc': '2.0',
            'method': 'probe_error',
            'params': {'data': 'one'},
        },
        {
            'id': 222,
            'jsonrpc': '2.0',
            'method': 'probe_error',
            'params': {'data': 'two'},
        },
    ])
    assert resp == [
        {'id': 111, 'jsonrpc': '2.0', 'error': {'code': -32603, 'message': 'Internal error'}},
        {'id': 222, 'jsonrpc': '2.0', 'error': {'code': -32603, 'message': 'Internal error'}},
    ]
    assert ep.calls == {
        111: [
            (
                'ep_middleware',
                'enter',
                {
                    'id': 111,
                    'jsonrpc': '2.0',
                    'method': 'probe_error',
                    'params': {'data': 'one'},
                },
                None,
            ),
            (
                'method_middleware',
                'enter',
                {
                    'id': 111,
                    'jsonrpc': '2.0',
                    'method': 'probe_error',
                    'params': {'data': 'one'}
                },
                None,
            ),
            (
                'method_middleware',
                'exit',
                {
                    'id': 111,
                    'jsonrpc': '2.0',
                    'method': 'probe_error',
                    'params': {'data': 'one'}
                },
                {'id': 111, 'jsonrpc': '2.0', 'error': {'code': -32603, 'message': 'Internal error'}},
            ),
            (
                'ep_middleware',
                'exit',
                {
                    'id': 111,
                    'jsonrpc': '2.0',
                    'method': 'probe_error',
                    'params': {'data': 'one'}
                },
                {'id': 111, 'jsonrpc': '2.0', 'error': {'code': -32603, 'message': 'Internal error'}},
            )
        ],
        222: [
            (
                'ep_middleware',
                'enter',
                {
                    'id': 222,
                    'jsonrpc': '2.0',
                    'method': 'probe_error',
                    'params': {'data': 'two'},
                },
                None,
            ),
            (
                'method_middleware',
                'enter',
                {
                    'id': 222,
                    'jsonrpc': '2.0',
                    'method': 'probe_error',
                    'params': {'data': 'two'}
                },
                None,
            ),
            (
                'method_middleware',
                'exit',
                {
                    'id': 222,
                    'jsonrpc': '2.0',
                    'method': 'probe_error',
                    'params': {'data': 'two'}
                },
                {'id': 222, 'jsonrpc': '2.0', 'error': {'code': -32603, 'message': 'Internal error'}},
            ),
            (
                'ep_middleware',
                'exit',
                {
                    'id': 222,
                    'jsonrpc': '2.0',
                    'method': 'probe_error',
                    'params': {'data': 'two'}
                },
                {'id': 222, 'jsonrpc': '2.0', 'error': {'code': -32603, 'message': 'Internal error'}},
            )
        ]
    }
