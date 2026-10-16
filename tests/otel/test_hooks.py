import logging

import pytest


def request_hook(span, ctx):
    span.set_attribute('app.requested_method', ctx.raw_request['method'])


def response_hook(span, ctx):
    span.set_attribute('app.failed', 'error' in ctx.raw_response)


def broken_hook(_span, _ctx):
    raise ValueError('hook is broken')


@pytest.mark.parametrize('middleware_options', [{'request_hook': request_hook}])
def test_request_hook(method_request, finished_spans):
    method_request('echo', {'data': 'hi'})

    [span] = finished_spans()
    assert span.attributes['app.requested_method'] == 'echo'


@pytest.mark.parametrize('middleware_options', [{'response_hook': response_hook}])
def test_response_hook_sees_response(method_request, finished_spans):
    method_request('fail_with_error', {})

    [span] = finished_spans()
    assert span.attributes['app.failed'] is True
    assert span.attributes['error.type'] == '5000'


@pytest.mark.parametrize('middleware_options', [
    {'request_hook': broken_hook},
    {'response_hook': broken_hook},
], ids=['request_hook', 'response_hook'])
def test_broken_hook_changes_nothing(method_request, finished_spans, caplog):
    assert method_request('echo', {'data': 'hi'}) == {'id': 0, 'jsonrpc': '2.0', 'result': 'hi'}

    [span] = finished_spans()
    assert span.name == 'echo'
    [warning] = [record for record in caplog.records if record.levelno == logging.WARNING]
    assert warning.name == 'fastapi_jsonrpc.contrib.opentelemetry'
