import collections
import contextlib
from json import dumps as json_dumps

import pytest

import fastapi_jsonrpc as jsonrpc

from .conftest import MyError

REQUEST_TYPE = 'fastapi_jsonrpc.request.type'

validated_objects = []


class CountingRequest(jsonrpc.JsonRpcRequest):
    @classmethod
    def model_validate(cls, obj, *args, **kwargs):
        validated_objects.append(obj)
        return super().model_validate(obj, *args, **kwargs)


@pytest.fixture(autouse=True)
def reset_validated_objects():
    validated_objects.clear()


def assert_request_type(finished_spans, duration_points, expected):
    [span] = finished_spans()
    [(_, point)] = duration_points()
    assert span.attributes[REQUEST_TYPE] == expected
    assert point.attributes[REQUEST_TYPE] == expected
    return span, point


def test_call(method_request, finished_spans, duration_points):
    method_request('echo', {'data': 'hi'})

    assert_request_type(finished_spans, duration_points, 'call')


def test_null_id_is_a_call(json_request, finished_spans, duration_points):
    json_request({'id': None, 'jsonrpc': '2.0', 'method': 'echo', 'params': {'data': 'hi'}})

    assert_request_type(finished_spans, duration_points, 'call')


@pytest.mark.parametrize('path_postfix', ['', '/echo'], ids=['entrypoint url', 'method url'])
def test_notification(raw_request, finished_spans, duration_points, path_postfix):
    raw_request(json_dumps({'jsonrpc': '2.0', 'method': 'echo', 'params': {'data': 'hi'}}), path_postfix=path_postfix)

    span, point = assert_request_type(finished_spans, duration_points, 'notification')
    assert 'error.type' not in span.attributes
    assert 'error.type' not in point.attributes


def test_notification_with_invalid_params(raw_request, finished_spans, duration_points):
    raw_request(json_dumps({'jsonrpc': '2.0', 'method': 'echo', 'params': {}}))

    span, point = assert_request_type(finished_spans, duration_points, 'notification')
    assert span.attributes['error.type'] == point.attributes['error.type'] == '-32602'


@pytest.mark.parametrize('body', [
    {'id': 1, 'jsonrpc': '2.0', 'params': {}},
    [1],
], ids=['missing method', 'not an object'])
def test_malformed_request_is_unknown(json_request, finished_spans, duration_points, body):
    json_request(body)

    span, point = assert_request_type(finished_spans, duration_points, 'unknown')
    assert span.attributes['error.type'] == point.attributes['error.type'] == '-32600'


def test_unknown_method_is_classified(json_request, finished_spans, duration_points):
    json_request({'id': 1, 'jsonrpc': '2.0', 'method': 'nope', 'params': {}})

    assert_request_type(finished_spans, duration_points, 'call')


def test_mixed_batch(json_request, finished_spans, duration_points):
    json_request([
        {'id': 1, 'jsonrpc': '2.0', 'method': 'echo', 'params': {'data': 'one'}},
        {'id': 2, 'jsonrpc': '2.0', 'method': 'echo', 'params': {'data': 'two'}},
        {'jsonrpc': '2.0', 'method': 'echo', 'params': {'data': 'three'}},
        {'jsonrpc': '2.0', 'method': 'echo', 'params': {}},
        {'id': 5, 'jsonrpc': '2.0'},
    ])

    assert collections.Counter(span.attributes[REQUEST_TYPE] for span in finished_spans()) == {
        'call': 2,
        'notification': 2,
        'unknown': 1,
    }
    counts = collections.Counter()
    for _, point in duration_points():
        counts[point.attributes[REQUEST_TYPE], point.attributes.get('error.type')] += point.count
    assert counts == {
        ('call', None): 2,
        ('notification', None): 1,
        ('notification', '-32602'): 1,
        ('unknown', '-32600'): 1,
    }


def test_error_raised_while_later_middleware_exits(ep, method_request, finished_spans, duration_points):
    @contextlib.asynccontextmanager
    async def failing_on_exit(_ctx: jsonrpc.JsonRpcContext):
        yield
        raise MyError()

    ep.middlewares.append(failing_on_exit)

    method_request('echo', {'data': 'hi'})

    span, point = assert_request_type(finished_spans, duration_points, 'call')
    assert span.attributes['error.type'] == point.attributes['error.type'] == '5000'


def test_later_middleware_replacing_response_keeps_classification(ep, method_request, finished_spans, duration_points):
    @contextlib.asynccontextmanager
    async def blank_response(ctx: jsonrpc.JsonRpcContext):
        yield
        ctx.raw_response = {}

    ep.middlewares.append(blank_response)

    method_request('echo', {'data': 'hi'})

    assert_request_type(finished_spans, duration_points, 'call')


@pytest.mark.parametrize('ep_options', [{'request_class': CountingRequest}])
def test_finalization_does_not_validate_again(ep, json_request, finished_spans, duration_points):
    @contextlib.asynccontextmanager
    async def reading_request(ctx: jsonrpc.JsonRpcContext):
        assert ctx.request.method == 'echo'
        yield

    ep.middlewares.append(reading_request)

    json_request({'id': 1, 'jsonrpc': '2.0', 'method': 'echo', 'params': {'data': 'hi'}})

    assert len(validated_objects) == 1
    assert_request_type(finished_spans, duration_points, 'call')


@pytest.mark.parametrize('ep_options', [{'request_class': CountingRequest}])
def test_finalization_does_not_retry_failed_validation(json_request, finished_spans, duration_points):
    json_request({'id': 1, 'jsonrpc': '2.0', 'params': {}})

    assert len(validated_objects) == 1
    assert_request_type(finished_spans, duration_points, 'unknown')
