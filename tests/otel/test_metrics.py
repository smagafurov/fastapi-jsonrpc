from json import dumps as json_dumps

import pytest

from .conftest import SLOW_METHOD_SECONDS

RECOMMENDED_BOUNDARIES = (0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 0.75, 1, 2.5, 5, 7.5, 10)


def test_successful_call(method_request, duration_points):
    method_request('echo', {'data': 'hi'})

    [(metric, point)] = duration_points()
    assert metric.unit == 's'
    assert dict(point.attributes) == {
        'rpc.system.name': 'jsonrpc',
        'rpc.method': 'echo',
        'fastapi_jsonrpc.request.type': 'call',
    }
    assert point.count == 1
    assert point.explicit_bounds == RECOMMENDED_BOUNDARIES


def test_duration_covers_the_call(method_request, duration_points):
    method_request('slow', {})

    [(_, point)] = duration_points()
    assert point.sum >= SLOW_METHOD_SECONDS


def test_batch_records_each_call(json_request, duration_points):
    json_request([
        {'id': 1, 'jsonrpc': '2.0', 'method': 'echo', 'params': {'data': 'one'}},
        {'id': 2, 'jsonrpc': '2.0', 'method': 'echo', 'params': {'data': 'two'}},
    ])

    [(_, point)] = duration_points()
    assert point.count == 2


def test_error_attributes(method_request, duration_points):
    method_request('fail_with_error', {})

    [(_, point)] = duration_points()
    assert dict(point.attributes) == {
        'rpc.system.name': 'jsonrpc',
        'rpc.method': 'fail_with_error',
        'fastapi_jsonrpc.request.type': 'call',
        'error.type': '5000',
        'rpc.status_code': '5000',
    }


def test_unknown_method_never_uses_requested_name(json_request, duration_points):
    json_request({'id': 1, 'jsonrpc': '2.0', 'method': 'nope', 'params': {}})

    [(_, point)] = duration_points()
    assert dict(point.attributes) == {
        'rpc.system.name': 'jsonrpc',
        'rpc.method': '_OTHER',
        'fastapi_jsonrpc.request.type': 'call',
        'error.type': '-32601',
        'rpc.status_code': '-32601',
    }


def test_invalid_request_has_no_method(json_request, duration_points):
    json_request({'id': 1, 'jsonrpc': '2.0', 'params': {}})

    [(_, point)] = duration_points()
    assert dict(point.attributes) == {
        'rpc.system.name': 'jsonrpc',
        'fastapi_jsonrpc.request.type': 'unknown',
        'error.type': '-32600',
        'rpc.status_code': '-32600',
    }


def test_http_exception(raw_request, duration_points):
    raw_request(json_dumps({'id': 1, 'jsonrpc': '2.0', 'method': 'fail_with_http_exception', 'params': {}}))

    [(_, point)] = duration_points()
    assert dict(point.attributes) == {
        'rpc.system.name': 'jsonrpc',
        'rpc.method': 'fail_with_http_exception',
        'fastapi_jsonrpc.request.type': 'call',
        'error.type': 'fastapi.exceptions.HTTPException',
    }


@pytest.mark.parametrize('middleware_options', [{'enable_metrics': False}])
def test_metrics_disabled(method_request, duration_points, finished_spans):
    method_request('echo', {'data': 'hi'})

    assert duration_points() == []
    assert len(finished_spans()) == 1
