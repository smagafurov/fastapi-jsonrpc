"""Test fixtures copied from https://github.com/getsentry/sentry-python/
TODO: move integration to sentry_sdk
"""

import pytest
import sentry_sdk
from sentry_sdk import Transport

from sentry_sdk.utils import capture_internal_exceptions


@pytest.fixture
def probe(ep):
    @ep.method()
    def probe() -> str:
        raise ZeroDivisionError

    @ep.method()
    def probe2() -> str:
        raise RuntimeError

    return ep


def test_transaction_is_jsonrpc_method(
    probe,
    json_request,
    sentry_init,
    capture_exceptions,
    capture_events,
    assert_log_errors,
):
    sentry_init(send_default_pii=True)
    exceptions = capture_exceptions()
    events = capture_events()

    # Test in batch to ensure we correctly handle multiple requests
    json_request([
        {
            'id': 1,
            'jsonrpc': '2.0',
            'method': 'probe',
            'params': {},
        },
        {
            'id': 2,
            'jsonrpc': '2.0',
            'method': 'probe2',
            'params': {},
        },
    ])

    assert {type(e) for e in exceptions} == {RuntimeError, ZeroDivisionError}

    assert_log_errors(
        '', pytest.raises(ZeroDivisionError),
        '', pytest.raises(RuntimeError),
    )

    assert set([
        e.get('transaction') for e in events
    ]) == {'test_sentry.probe.<locals>.probe', 'test_sentry.probe.<locals>.probe2'}


class _TestTransport(Transport):
    def __init__(self, capture_event_callback, capture_envelope_callback):
        Transport.__init__(self)
        self.capture_event = capture_event_callback
        self.capture_envelope = capture_envelope_callback
        self._queue = None


@pytest.fixture
def monkeypatch_test_transport(monkeypatch):
    def check_event(event):
        def check_string_keys(map):
            for key, value in map.items:
                assert isinstance(key, str)
                if isinstance(value, dict):
                    check_string_keys(value)

        with capture_internal_exceptions():
            check_string_keys(event)

    def check_envelope(envelope):
        with capture_internal_exceptions():
            # Assert error events are sent without envelope to server, for compat.
            # This does not apply if any item in the envelope is an attachment.
            if not any(x.type == "attachment" for x in envelope.items):
                assert not any(item.data_category == "error" for item in envelope.items)
                assert not any(item.get_event() is not None for item in envelope.items)

    def inner(client):
        monkeypatch.setattr(
            client, "transport", _TestTransport(check_event, check_envelope)
        )

    return inner


@pytest.fixture
def sentry_init(monkeypatch_test_transport, request):
    def inner(*a, **kw):
        hub = sentry_sdk.Hub.current
        client = sentry_sdk.Client(*a, **kw)
        hub.bind_client(client)
        if "transport" not in kw:
            monkeypatch_test_transport(sentry_sdk.Hub.current.client)

    if request.node.get_closest_marker("forked"):
        # Do not run isolation if the test is already running in
        # ultimate isolation (seems to be required for celery tests that
        # fork)
        yield inner
    else:
        with sentry_sdk.Hub(None):
            yield inner


@pytest.fixture
def capture_events(monkeypatch):
    def inner():
        events = []
        test_client = sentry_sdk.Hub.current.client
        old_capture_event = test_client.transport.capture_event
        old_capture_envelope = test_client.transport.capture_envelope

        def append_event(event):
            events.append(event)
            return old_capture_event(event)

        def append_envelope(envelope):
            for item in envelope:
                if item.headers.get("type") in ("event", "transaction"):
                    test_client.transport.capture_event(item.payload.json)
            return old_capture_envelope(envelope)

        monkeypatch.setattr(test_client.transport, "capture_event", append_event)
        monkeypatch.setattr(test_client.transport, "capture_envelope", append_envelope)
        return events

    return inner


@pytest.fixture
def capture_exceptions(monkeypatch):
    def inner():
        errors = set()
        old_capture_event = sentry_sdk.Hub.capture_event

        def capture_event(self, event, hint=None):
            if hint:
                if "exc_info" in hint:
                    error = hint["exc_info"][1]
                    errors.add(error)
            return old_capture_event(self, event, hint=hint)

        monkeypatch.setattr(sentry_sdk.Hub, "capture_event", capture_event)
        return errors

    return inner
