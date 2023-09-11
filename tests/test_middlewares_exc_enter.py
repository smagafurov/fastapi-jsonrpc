import contextlib
import sys
import uuid
from collections import defaultdict

import pytest
from fastapi import Body

import fastapi_jsonrpc as jsonrpc


unique_marker = str(uuid.uuid4())


@pytest.fixture
def ep(ep_path):
    _calls = defaultdict(list)

    @contextlib.asynccontextmanager
    async def mw_first(ctx: jsonrpc.JsonRpcContext):
        nonlocal _calls
        _calls[ctx.raw_request.get('id')].append((
            'mw_first', 'enter', ctx.raw_request, ctx.raw_response, sys.exc_info()[0]
        ))
        try:
            yield
        finally:
            _calls[ctx.raw_response.get('id')].append((
                'mw_first', 'exit', ctx.raw_request, ctx.raw_response, sys.exc_info()[0]
            ))

    @contextlib.asynccontextmanager
    async def mw_exception_enter(ctx: jsonrpc.JsonRpcContext):
        nonlocal _calls
        _calls[ctx.raw_request.get('id')].append((
            'mw_exception_enter', 'enter', ctx.raw_request, ctx.raw_response, sys.exc_info()[0]
        ))
        raise RuntimeError(unique_marker)
        # noinspection PyUnreachableCode
        try:
            yield
        finally:
            _calls[ctx.raw_response.get('id')].append((
                'mw_exception_enter', 'exit', ctx.raw_request, ctx.raw_response, sys.exc_info()[0]
            ))

    @contextlib.asynccontextmanager
    async def mw_last(ctx: jsonrpc.JsonRpcContext):
        nonlocal _calls
        _calls[ctx.raw_request.get('id')].append((
            'mw_last', 'enter', ctx.raw_request, ctx.raw_response, sys.exc_info()[0]
        ))
        try:
            yield
        finally:
            _calls[ctx.raw_response.get('id')].append((
                'mw_last', 'exit', ctx.raw_request, ctx.raw_response, sys.exc_info()[0]
            ))

    ep = jsonrpc.Entrypoint(
        ep_path,
        middlewares=[mw_first, mw_exception_enter, mw_last],
    )

    @ep.method()
    def probe(
        data: str = Body(..., examples=['123']),
    ) -> str:
        return data

    ep.calls = _calls

    return ep


def test_ep_exception(ep, method_request, assert_log_errors):
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
                None,
            ),
            (
                'mw_exception_enter',
                'enter',
                {
                    'id': 111,
                    'jsonrpc': '2.0',
                    'method': 'probe',
                    'params': {'data': 'one'}
                },
                None,
                None,
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
                RuntimeError,
            ),
        ]
    }

    assert_log_errors(unique_marker, pytest.raises(RuntimeError))
