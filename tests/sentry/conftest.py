import pytest
import sentry_sdk
from sentry_sdk import Transport
from sentry_sdk.envelope import Envelope
from sentry_sdk.integrations.starlette import StarletteIntegration
from sentry_sdk.integrations.fastapi import FastApiIntegration
from fastapi_jsonrpc.contrib.sentry import FastApiJsonRPCIntegration


@pytest.fixture
def capture_events(monkeypatch):
    def inner():
        events = []
        test_client = sentry_sdk.get_client()
        old_capture_envelope = test_client.transport.capture_envelope

        def append_event(envelope):
            for item in envelope:
                if item.headers.get("type") in ("event", "transaction"):
                    events.append(item.payload.json)
            return old_capture_envelope(envelope)

        monkeypatch.setattr(test_client.transport, "capture_envelope", append_event)

        return events

    return inner


@pytest.fixture
def capture_envelopes(monkeypatch):
    def inner():
        envelopes = []
        test_client = sentry_sdk.get_client()
        old_capture_envelope = test_client.transport.capture_envelope

        def append_envelope(envelope):
            envelopes.append(envelope)
            return old_capture_envelope(envelope)

        monkeypatch.setattr(test_client.transport, "capture_envelope", append_envelope)

        return envelopes

    return inner


@pytest.fixture
def capture_exceptions(monkeypatch):
    def inner():
        errors = set()
        old_capture_event_hub = sentry_sdk.Hub.capture_event
        old_capture_event_scope = sentry_sdk.Scope.capture_event

        def capture_event_hub(self, event, hint=None, scope=None):
            """
            Can be removed when we remove push_scope and the Hub from the SDK.
            """
            if hint:
                if "exc_info" in hint:
                    error = hint["exc_info"][1]
                    errors.add(error)
            return old_capture_event_hub(self, event, hint=hint, scope=scope)

        def capture_event_scope(self, event, hint=None, scope=None):
            if hint:
                if "exc_info" in hint:
                    error = hint["exc_info"][1]
                    errors.add(error)
            return old_capture_event_scope(self, event, hint=hint, scope=scope)

        monkeypatch.setattr(sentry_sdk.Hub, "capture_event", capture_event_hub)
        monkeypatch.setattr(sentry_sdk.Scope, "capture_event", capture_event_scope)

        return errors

    return inner


@pytest.fixture
def sentry_init(request):
    def inner(*a, **kw):
        kw.setdefault("transport", TestTransport())
        kw.setdefault("integrations", [FastApiJsonRPCIntegration()])
        kw.setdefault("traces_sample_rate", 1.0)
        kw.setdefault("disabled_integrations", [StarletteIntegration, FastApiIntegration])

        client = sentry_sdk.Client(*a, **kw)
        sentry_sdk.get_global_scope().set_client(client)

    if request.node.get_closest_marker("forked"):
        # Do not run isolation if the test is already running in
        # ultimate isolation (seems to be required for celery tests that
        # fork)
        yield inner
    else:
        old_client = sentry_sdk.get_global_scope().client
        try:
            sentry_sdk.get_current_scope().set_client(None)
            yield inner
        finally:
            sentry_sdk.get_global_scope().set_client(old_client)


class TestTransport(Transport):
    def capture_envelope(self, _: Envelope) -> None:
        """
        No-op capture_envelope for tests
        """
