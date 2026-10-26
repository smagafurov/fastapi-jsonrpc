import contextlib
from json import dumps as json_dumps

import pytest
from fastapi import Depends
from opentelemetry.trace import StatusCode

from fastapi_jsonrpc import JsonRpcContext

from .conftest import MyError


def error_attributes(code):
    return {'error.type': code, 'rpc.status_code': code}


def test_unknown_method(json_request, finished_spans):
    resp = json_request({'id': 1, 'jsonrpc': '2.0', 'method': 'nope', 'params': {}})
    assert resp['error']['code'] == -32601

    [span] = finished_spans()
    assert span.name == 'jsonrpc'
    assert dict(span.attributes) == {
        'rpc.system.name': 'jsonrpc',
        'rpc.method': '_OTHER',
        'rpc.method_original': 'nope',
        'jsonrpc.protocol.version': '2.0',
        'jsonrpc.request.id': '1',
        'fastapi_jsonrpc.request.type': 'call',
        **error_attributes('-32601'),
    }
    assert span.status.status_code == StatusCode.ERROR
    assert span.status.description == 'Method not found'


def test_method_mismatching_method_path(json_request, finished_spans):
    resp = json_request({'id': 1, 'jsonrpc': '2.0', 'method': 'nope', 'params': {}}, path_postfix='/echo')
    assert resp['error']['code'] == -32601

    [span] = finished_spans()
    assert span.name == 'jsonrpc'
    assert span.attributes['rpc.method'] == '_OTHER'
    assert span.attributes['rpc.method_original'] == 'nope'


@pytest.mark.parametrize('request_body', [
    {'id': 1, 'jsonrpc': '2.0', 'params': {}},
    {'id': 1, 'jsonrpc': '2.0', 'method': 123, 'params': {}},
], ids=['missing method', 'non-string method'])
def test_invalid_request(json_request, finished_spans, request_body):
    resp = json_request(request_body)
    assert resp['error']['code'] == -32600

    [span] = finished_spans()
    assert span.name == 'jsonrpc'
    assert dict(span.attributes) == {
        'rpc.system.name': 'jsonrpc',
        'jsonrpc.protocol.version': '2.0',
        'jsonrpc.request.id': '1',
        'fastapi_jsonrpc.request.type': 'unknown',
        **error_attributes('-32600'),
    }
    assert span.status.status_code == StatusCode.ERROR
    assert span.status.description == 'Invalid Request'


def test_batch_item_is_not_an_object(json_request, finished_spans):
    [resp] = json_request([1])
    assert resp['error']['code'] == -32600

    [span] = finished_spans()
    assert span.name == 'jsonrpc'
    assert dict(span.attributes) == {
        'rpc.system.name': 'jsonrpc',
        'jsonrpc.protocol.version': '2.0',
        'fastapi_jsonrpc.request.type': 'unknown',
        **error_attributes('-32600'),
    }


def test_invalid_params(method_request, finished_spans):
    resp = method_request('echo', {})
    assert resp['error']['code'] == -32602

    [span] = finished_spans()
    assert span.name == 'echo'
    assert span.attributes['rpc.method'] == 'echo'
    assert {k: span.attributes[k] for k in error_attributes('')} == error_attributes('-32602')
    assert span.status.status_code == StatusCode.ERROR
    assert span.status.description == 'Invalid params'


def test_user_error(method_request, finished_spans):
    resp = method_request('fail_with_error', {})
    assert resp['error'] == {'code': 5000, 'message': 'My error'}

    [span] = finished_spans()
    assert span.name == 'fail_with_error'
    assert {k: span.attributes[k] for k in error_attributes('')} == error_attributes('5000')
    assert span.status.status_code == StatusCode.ERROR
    assert span.status.description == 'My error'
    assert span.events == ()


def test_error_from_later_middleware_enter(ep, method_request, finished_spans):
    @contextlib.asynccontextmanager
    async def rejecting_middleware(_ctx: JsonRpcContext):
        raise MyError()
        # noinspection PyUnreachableCode
        yield

    ep.middlewares.append(rejecting_middleware)

    resp = method_request('echo', {'data': 'hi'})
    assert resp['error']['code'] == 5000

    [span] = finished_spans()
    assert span.name == 'echo'
    assert {k: span.attributes[k] for k in error_attributes('')} == error_attributes('5000')
    assert span.status.status_code == StatusCode.ERROR


def raise_my_error():
    raise MyError()


@pytest.mark.parametrize('ep_options', [{'dependencies': [Depends(raise_my_error)]}])
def test_shared_dependency_error_on_every_call(json_request, finished_spans):
    json_request([
        {'id': 1, 'jsonrpc': '2.0', 'method': 'echo', 'params': {'data': 'one'}},
        {'id': 2, 'jsonrpc': '2.0', 'method': 'echo', 'params': {'data': 'two'}},
    ])

    spans = finished_spans()
    assert len(spans) == 2
    for span in spans:
        assert {k: span.attributes[k] for k in error_attributes('')} == error_attributes('5000')
        assert span.status.status_code == StatusCode.ERROR


def test_http_exception(raw_request, finished_spans):
    resp = raw_request(json_dumps({'id': 1, 'jsonrpc': '2.0', 'method': 'fail_with_http_exception', 'params': {}}))
    assert resp.status_code == 403

    [span] = finished_spans()
    assert span.name == 'fail_with_http_exception'
    assert span.attributes['error.type'] == 'fastapi.exceptions.HTTPException'
    assert 'rpc.status_code' not in span.attributes
    assert span.status.status_code == StatusCode.ERROR
    assert span.status.description is None
    assert span.events == ()
