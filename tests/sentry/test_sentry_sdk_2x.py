"""Test fixtures copied from https://github.com/getsentry/sentry-python/"""

import uuid
import importlib.metadata
import pytest
from logging import getLogger
from sentry_sdk.tracing import Transaction
from fastapi_jsonrpc import BaseError

from fastapi_jsonrpc.contrib.sentry.test_utils import (
    get_transaction_trace_id,
    get_captured_transactions,
    assert_jrpc_batch_sentry_items,
)

sentry_sdk_version = importlib.metadata.version("sentry_sdk")
if not sentry_sdk_version.startswith("2."):
    pytest.skip(f"Testset is only for sentry_sdk 2.x, given {sentry_sdk_version=}", allow_module_level=True)


class JrpcSampleError(BaseError):
    CODE = 5001
    MESSAGE = "Sample JRPC error"


@pytest.fixture
def failing_router(ep):
    sub_app = ep
    logger = getLogger("test-sentry")

    @sub_app.method(name="first_logged_error_method")
    async def first_logged_error_method() -> dict:
        try:
            raise ValueError()
        except Exception:
            logger.exception("First logged error method exc")

        return {"handled": True}

    @sub_app.method(name="second_logged_error_method")
    async def second_logged_error_method() -> dict:
        try:
            raise TypeError()
        except Exception:
            logger.exception("Second logged error method exc")

        return {"handled": True}

    @sub_app.method(name="unhandled_error_method")
    async def unhandled_error_method() -> dict:
        raise RuntimeError("Unhandled method exc")

    @sub_app.method(name="jrpc_error_method")
    async def jrpc_error_method() -> dict:
        raise JrpcSampleError()

    @sub_app.method(name="successful_method")
    async def successful_method() -> dict:
        return {"success": True}


def test_logged_exceptions_event_creation(
    json_request,
    capture_exceptions,
    capture_events,
    capture_envelopes,
    failing_router,
    sentry_with_integration,
    assert_log_errors,
):
    exceptions = capture_exceptions()
    envelops = capture_envelopes()
    response = json_request(
        [
            {
                "method": "first_logged_error_method",
                "params": {},
                "jsonrpc": "2.0",
                "id": 1,
            },
            {
                "method": "second_logged_error_method",
                "params": {},
                "jsonrpc": "2.0",
                "id": 1,
            },
        ],
    )
    assert response == [
        {
            "result": {"handled": True},
            "jsonrpc": "2.0",
            "id": 1,
        },
        {
            "result": {"handled": True},
            "jsonrpc": "2.0",
            "id": 1,
        },
    ]
    assert {type(e) for e in exceptions} == {ValueError, TypeError}
    assert_log_errors(
        "First logged error method exc",
        pytest.raises(ValueError),
        "Second logged error method exc",
        pytest.raises(TypeError),
    )
    # 2 errors and 2 transactions
    assert_jrpc_batch_sentry_items(envelops, expected_items={"event": 2, "transaction": 2})


def test_unhandled_exception_event_creation(
    json_request,
    capture_exceptions,
    capture_events,
    capture_envelopes,
    failing_router,
    assert_log_errors,
    sentry_with_integration,
):
    exceptions = capture_exceptions()
    envelops = capture_envelopes()
    response = json_request(
        {
            "method": "unhandled_error_method",
            "params": {},
            "jsonrpc": "2.0",
            "id": 1,
        }
    )
    assert response == {
        "error": {"code": -32603, "message": "Internal error"},
        "jsonrpc": "2.0",
        "id": 1,
    }
    assert_log_errors(
        "Unhandled method exc",
        pytest.raises(RuntimeError),
    )
    assert {type(e) for e in exceptions} == {RuntimeError}
    # 1 error and 1 transaction
    assert_jrpc_batch_sentry_items(envelops, expected_items={"event": 1, "transaction": 1})


@pytest.mark.parametrize(
    "request_payload",
    [
        [
            {
                "method": "jrpc_error_method",
                "params": {},
                "jsonrpc": "2.0",
                "id": 1,
            },
            {
                "method": "unhandled_error_method",
                "params": {},
                "jsonrpc": "2.0",
                "id": 1,
            },
            {
                "method": "successful_method",
                "params": {},
                "jsonrpc": "2.0",
                "id": 1,
            },
        ]
    ],
)
def test_trace_id_propagation(
    request_payload,
    json_request,
    capture_exceptions,
    capture_events,
    capture_envelopes,
    failing_router,
    assert_log_errors,
    sentry_with_integration,
):
    envelops = capture_envelopes()
    expected_trace_id = uuid.uuid4().hex
    incoming_transaction = Transaction(trace_id=expected_trace_id)
    tracing_headers = list(incoming_transaction.iter_headers())

    response = json_request(request_payload, headers=tracing_headers)

    assert response == [
        {
            "error": {"code": 5001, "message": "Sample JRPC error"},
            "jsonrpc": "2.0",
            "id": 1,
        },
        {
            "error": {"code": -32603, "message": "Internal error"},
            "jsonrpc": "2.0",
            "id": 1,
        },
        {
            "result": {"success": True},
            "jsonrpc": "2.0",
            "id": 1,
        },
    ]
    assert_jrpc_batch_sentry_items(envelops, expected_items={"transaction": 3, "event": 1})
    for transaction in get_captured_transactions(envelops):
        assert get_transaction_trace_id(transaction) == expected_trace_id

    assert_log_errors(
        "Unhandled method exc",
        pytest.raises(RuntimeError),
    )
