from json import dumps as json_dumps

from opentelemetry.trace import SpanKind, StatusCode


def test_single_call(method_request, finished_spans):
    assert method_request('echo', {'data': 'hi'}, request_id=1) == {'id': 1, 'jsonrpc': '2.0', 'result': 'hi'}

    [span] = finished_spans()
    assert span.name == 'echo'
    assert span.kind == SpanKind.SERVER
    assert dict(span.attributes) == {
        'rpc.system.name': 'jsonrpc',
        'rpc.method': 'echo',
        'jsonrpc.protocol.version': '2.0',
        'jsonrpc.request.id': '1',
    }
    assert span.status.status_code == StatusCode.UNSET


def test_string_request_id(method_request, finished_spans):
    method_request('echo', {'data': 'hi'}, request_id='abc')

    [span] = finished_spans()
    assert span.attributes['jsonrpc.request.id'] == 'abc'


def test_span_is_current_inside_method(method_request, finished_spans):
    method_request('traced_echo', {'data': 'hi'})

    inner, call = finished_spans()
    assert call.name == 'traced_echo'
    assert inner.parent.span_id == call.context.span_id


def test_batch(json_request, finished_spans):
    json_request([
        {'id': 1, 'jsonrpc': '2.0', 'method': 'echo', 'params': {'data': 'one'}},
        {'id': 2, 'jsonrpc': '2.0', 'method': 'traced_echo', 'params': {'data': 'two'}},
    ])

    calls = sorted(
        (span for span in finished_spans() if span.kind == SpanKind.SERVER),
        key=lambda span: span.attributes['jsonrpc.request.id'],
    )
    assert [(span.name, span.attributes['jsonrpc.request.id']) for span in calls] == [
        ('echo', '1'),
        ('traced_echo', '2'),
    ]


def test_notification(raw_request, finished_spans):
    resp = raw_request(json_dumps({'jsonrpc': '2.0', 'method': 'echo', 'params': {'data': 'hi'}}))
    assert resp.content == b''

    [span] = finished_spans()
    assert span.name == 'echo'
    assert 'jsonrpc.request.id' not in span.attributes


def test_null_request_id(json_request, finished_spans):
    json_request({'id': None, 'jsonrpc': '2.0', 'method': 'echo', 'params': {'data': 'hi'}})

    [span] = finished_spans()
    assert 'jsonrpc.request.id' not in span.attributes
