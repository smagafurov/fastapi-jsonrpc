import contextlib
import contextvars
import logging
import sys
import uuid
from collections import defaultdict
from typing import Tuple

import pytest
from fastapi import Body

import fastapi_jsonrpc as jsonrpc


unique_marker = str(uuid.uuid4())
unique_marker2 = str(uuid.uuid4())


class _TestError(jsonrpc.BaseError):
    CODE = 33333
    MESSAGE = "Test error"


@pytest.fixture
def ep(ep_path):
    _calls = defaultdict(list)

    ep_middleware_var = contextvars.ContextVar('ep_middleware')
    method_middleware_var = contextvars.ContextVar('method_middleware')

    @contextlib.asynccontextmanager
    async def ep_handle_exception(_ctx: jsonrpc.JsonRpcContext):
        try:
            yield
        except RuntimeError as exc:
            logging.exception(str(exc), exc_info=exc)
            raise _TestError(unique_marker2)

    @contextlib.asynccontextmanager
    async def ep_middleware(ctx: jsonrpc.JsonRpcContext):
        nonlocal _calls
        ep_middleware_var.set('ep_middleware-value')
        _calls[ctx.raw_request.get('id')].append((
            'ep_middleware', 'enter', ctx.raw_request, ctx.raw_response, sys.exc_info()[0]
        ))
        try:
            yield
        finally:
            _calls[ctx.raw_response.get('id')].append((
                'ep_middleware', 'exit', ctx.raw_request, ctx.raw_response, sys.exc_info()[0]
            ))

    @contextlib.asynccontextmanager
    async def method_middleware(ctx):
        nonlocal _calls
        method_middleware_var.set('method_middleware-value')
        _calls[ctx.raw_request.get('id')].append((
            'method_middleware', 'enter', ctx.raw_request, ctx.raw_response, sys.exc_info()[0]
        ))
        try:
            yield
        finally:
            _calls[ctx.raw_response.get('id')].append((
                'method_middleware', 'exit', ctx.raw_request, ctx.raw_response, sys.exc_info()[0]
            ))

    ep = jsonrpc.Entrypoint(
        ep_path,
        middlewares=[ep_handle_exception, ep_middleware],
    )

    @ep.method(middlewares=[method_middleware])
    def probe(
        data: str = Body(..., examples=['123']),
    ) -> str:
        return data

    @ep.method(middlewares=[method_middleware])
    def probe_error(
    ) -> str:
        raise RuntimeError(unique_marker)

    @ep.method(middlewares=[method_middleware])
    def probe_context_vars(
    ) -> Tuple[str, str]:
        return ep_middleware_var.get(), method_middleware_var.get()

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
                None,
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
                None,
            )
        ]
    }


def test_single_error(ep, method_request, assert_log_errors):
    resp = method_request('probe_error', {'data': 'one'}, request_id=111)
    assert resp == {
        'id': 111, 'jsonrpc': '2.0', 'error': {
            'code': 33333, 'data': unique_marker2, 'message': 'Test error',
        }
    }
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
                RuntimeError,
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
                RuntimeError,
            )
        ]
    }

    assert_log_errors(unique_marker, pytest.raises(RuntimeError))


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
                None,
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
                None,
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
                None,
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
                None,
            )
        ]
    }


def test_batch_error(ep, json_request, assert_log_errors):
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
        {
            'id': 111, 'jsonrpc': '2.0', 'error': {
                'code': 33333, 'data': unique_marker2, 'message': 'Test error',
            }
        },
        {
            'id': 222, 'jsonrpc': '2.0', 'error': {
                'code': 33333, 'data': unique_marker2, 'message': 'Test error',
            }
        },
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
                RuntimeError,
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
                RuntimeError,
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
                RuntimeError,
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
                RuntimeError,
            )
        ]
    }

    assert_log_errors(
        unique_marker, pytest.raises(RuntimeError),
        unique_marker, pytest.raises(RuntimeError),
    )


def test_context_vars(ep, method_request):
    resp = method_request('probe_context_vars', {}, request_id=111)
    assert resp == {'id': 111, 'jsonrpc': '2.0', 'result': ['ep_middleware-value', 'method_middleware-value']}
