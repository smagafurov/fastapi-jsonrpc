import logging

import pytest
from opentelemetry.trace import StatusCode

from .conftest import SECRET_MESSAGE


@pytest.fixture
def call_crash(method_request, assert_log_errors):
    def call():
        resp = method_request('crash', {})
        assert resp['error'] == {'code': -32603, 'message': 'Internal error'}
        assert_log_errors(SECRET_MESSAGE, pytest.raises(RuntimeError))

    return call


def redact(exc):
    return RuntimeError('redacted').with_traceback(exc.__traceback__)


def skip(_exc):
    return None


def broken_filter(_exc):
    raise ValueError('filter is broken')


def test_nothing_recorded_by_default(call_crash, finished_spans):
    call_crash()

    [span] = finished_spans()
    assert span.attributes['error.type'] == '-32603'
    assert span.attributes['rpc.status_code'] == '-32603'
    assert span.status.status_code == StatusCode.ERROR
    assert span.status.description == 'Internal error'
    assert span.events == ()
    assert SECRET_MESSAGE not in repr(dict(span.attributes))


@pytest.mark.parametrize('middleware_options', [{'record_exception': True}])
def test_record_exception(call_crash, finished_spans):
    call_crash()

    [span] = finished_spans()
    [event] = span.events
    assert event.name == 'exception'
    assert event.attributes['exception.message'] == SECRET_MESSAGE
    assert 'in crash' in event.attributes['exception.stacktrace']
    assert span.status.description == 'Internal error'


@pytest.mark.parametrize('middleware_options', [{'record_exception': redact}])
def test_record_redacted_exception(call_crash, finished_spans):
    call_crash()

    [span] = finished_spans()
    [event] = span.events
    assert event.attributes['exception.message'] == 'redacted'
    assert 'in crash' in event.attributes['exception.stacktrace']
    assert SECRET_MESSAGE not in repr(dict(event.attributes))


@pytest.mark.parametrize('middleware_options', [{'record_exception': skip}])
def test_filter_skips_exception(call_crash, finished_spans):
    call_crash()

    [span] = finished_spans()
    assert span.events == ()


@pytest.mark.parametrize('middleware_options', [{'record_exception': broken_filter}])
def test_broken_filter_records_nothing(method_request, assert_log_errors, finished_spans, caplog):
    resp = method_request('crash', {})
    assert resp['error'] == {'code': -32603, 'message': 'Internal error'}
    [warning] = [record for record in caplog.records if record.levelno == logging.WARNING]
    assert warning.name == 'fastapi_jsonrpc.contrib.opentelemetry'
    assert_log_errors(SECRET_MESSAGE, pytest.raises(RuntimeError))

    [span] = finished_spans()
    assert span.events == ()
    assert span.status.description == 'Internal error'


@pytest.mark.parametrize('middleware_options', [{'record_exception': True}])
def test_jsonrpc_errors_are_never_recorded(method_request, finished_spans):
    method_request('fail_with_error', {})

    [span] = finished_spans()
    assert span.events == ()
