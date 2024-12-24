"""Test fixtures copied from https://github.com/getsentry/sentry-python/"""

import uuid
import importlib.metadata
import pytest
from logging import getLogger
from sentry_sdk.tracing import Transaction
from fastapi_jsonrpc.contrib.sentry.test_utils import (
    get_transaction_trace_id,
    get_captured_transactions,
    assert_jrpc_batch_sentry_items,
)

sentry_sdk_version = importlib.metadata.version("sentry_sdk")
if not sentry_sdk_version.startswith("2."):
    pytest.skip(f"Testset is only for sentry_sdk 2.x, given {sentry_sdk_version=}", allow_module_level=True)


@pytest.fixture
def failing_router(ep):
    sub_app = ep
    logger = getLogger("test-sentry")

    @sub_app.method(name="first_failing_method")
    async def first_failing_method():
        try:
            raise ValueError()
        except Exception:
            logger.exception("First route exc")

    @sub_app.method(name="second_failing_method")
    async def second_failing_method():
        try:
            raise TypeError()
        except Exception:
            logger.exception("Second route exc")

    @sub_app.method(name="unhandled_error_method")
    async def unhandled_error_method():
        raise RuntimeError("Third route exc")

    @sub_app.method(name="successful_method")
    async def successful_method():
        pass


def test_exception_logger_event_creation(
    json_request, capture_exceptions, capture_events, capture_envelopes, failing_router, sentry_init,
    assert_log_errors,
):
    sentry_init()
    exceptions = capture_exceptions()
    envelops = capture_envelopes()
    json_request(
        [
            {"jsonrpc": "2.0", "method": "first_failing_method", "params": {}, "id": 1},
            {"jsonrpc": "2.0", "method": "second_failing_method", "params": {}, "id": 1},
        ],
    )
    assert {type(e) for e in exceptions} == {ValueError, TypeError}
    assert_log_errors(
        'First route exc', pytest.raises(ValueError),
        'Second route exc', pytest.raises(TypeError),
    )
    # 2 errors and 2 transactions
    assert_jrpc_batch_sentry_items(envelops, expected_items={"event": 2, "transaction": 2})


def test_unhandled_exception_capturing(
    json_request, capture_exceptions, capture_events, capture_envelopes, failing_router, assert_log_errors,
    sentry_init
):
    sentry_init()
    exceptions = capture_exceptions()
    envelops = capture_envelopes()
    json_request({"jsonrpc": "2.0", "method": "unhandled_error_method", "params": {}, "id": 1})
    assert_log_errors(
        "Third route exc",
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
                "jsonrpc": "2.0",
                "method": "first_failing_method",
                "params": {},
                "id": 1,
            },
            {
                "jsonrpc": "2.0",
                "method": "unhandled_error_method",
                "params": {},
                "id": 1,
            },
            {
                "jsonrpc": "2.0",
                "method": "successful_method",
                "params": {},
                "id": 1,
            },
        ]
    ],
)
def test_trace_id_propagation(
    request_payload, json_request, capture_exceptions, capture_events, capture_envelopes, failing_router,
    assert_log_errors, sentry_init
):
    sentry_init()
    envelops = capture_envelopes()
    expected_trace_id = uuid.uuid4().hex
    incoming_transaction = Transaction(trace_id=expected_trace_id)
    tracing_headers = list(incoming_transaction.iter_headers())
    json_request(
        request_payload,
        headers=tracing_headers,
    )
    assert_jrpc_batch_sentry_items(envelops, expected_items={"transaction": 3, "event": 2})
    for transaction in get_captured_transactions(envelops):
        assert get_transaction_trace_id(transaction) == expected_trace_id

    assert_log_errors(
        'First route exc', pytest.raises(ValueError),
        'Third route exc', pytest.raises(RuntimeError),
    )
