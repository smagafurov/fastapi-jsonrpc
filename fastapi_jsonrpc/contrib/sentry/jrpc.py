from random import Random
from typing import TYPE_CHECKING, Callable
from contextlib import asynccontextmanager

import sentry_sdk
from fastapi_jsonrpc import BaseError, Entrypoint, JsonRpcContext
from sentry_sdk.utils import event_from_exception, is_valid_sample_rate
from sentry_sdk.consts import OP
from sentry_sdk.tracing import SENTRY_TRACE_HEADER_NAME, Transaction
from sentry_sdk.tracing_utils import normalize_incoming_data

from .http import sentry_asgi_context

if TYPE_CHECKING:
    from .integration import FastApiJsonRPCIntegration

_DEFAULT_TRANSACTION_NAME = "generic JRPC request"
TransactionNameGenerator = Callable[[JsonRpcContext], str]

if hasattr(sentry_sdk.tracing, 'TransactionSource'):
    # sentry_sdk ^2.23
    TRANSACTION_SOURCE_CUSTOM = sentry_sdk.tracing.TransactionSource.CUSTOM
else:
    # sentry_sdk ^2.0
    TRANSACTION_SOURCE_CUSTOM = sentry_sdk.tracing.TRANSACTION_SOURCE_CUSTOM


@asynccontextmanager
async def jrpc_transaction_middleware(ctx: JsonRpcContext):
    """
    Start new transaction for each JRPC request. Applies same sampling decision for every transaction in the batch.
    """

    current_asgi_context = sentry_asgi_context.get()
    headers = current_asgi_context["asgi_headers"]
    transaction_params = dict(
        # this name is replaced by event processor
        name=_DEFAULT_TRANSACTION_NAME,
        op=OP.HTTP_SERVER,
        source=TRANSACTION_SOURCE_CUSTOM,
        origin="manual",
    )
    with sentry_sdk.isolation_scope() as jrpc_request_scope:
        jrpc_request_scope.clear()

        if SENTRY_TRACE_HEADER_NAME in headers:
            # continue existing trace
            # https://github.com/getsentry/sentry-python/blob/2.19.2/sentry_sdk/scope.py#L471
            jrpc_request_scope.generate_propagation_context(headers)
            transaction = JrpcTransaction.continue_from_headers(
                normalize_incoming_data(headers),
                **transaction_params,
            )
        else:
            # no parent transaction, start a new trace
            transaction = JrpcTransaction(
                trace_id=current_asgi_context["sampled_sentry_trace_id"].hex,
                **transaction_params,  # type: ignore
            )

        integration: FastApiJsonRPCIntegration | None = sentry_sdk.get_client().get_integration(  # type: ignore
            "FastApiJsonRPCIntegration"
        )
        name_generator = integration.transaction_name_generator if integration else default_transaction_name_generator

        with jrpc_request_scope.start_transaction(
            transaction,
            scope=jrpc_request_scope,
        ):
            jrpc_request_scope.add_event_processor(make_transaction_info_event_processor(ctx, name_generator))
            try:
                yield
            except Exception as exc:
                if isinstance(exc, BaseError):
                    raise

                # attaching event to current transaction
                event, hint = event_from_exception(
                    exc,
                    client_options=sentry_sdk.get_client().options,
                    mechanism={"type": "asgi", "handled": False},
                )
                sentry_sdk.capture_event(event, hint=hint)
                # propagate error further. Possible duplicates would be suppressed by default `DedupeIntegration`
                raise exc from None


class JrpcTransaction(Transaction):
    """
    Overrides `_set_initial_sampling_decision` to apply same sampling decision for transactions with same `trace_id`.
    """

    def _set_initial_sampling_decision(self, sampling_context):
        super()._set_initial_sampling_decision(sampling_context)
        # https://github.com/getsentry/sentry-python/blob/2.19.2/sentry_sdk/tracing.py#L1125
        if self.sampled or not is_valid_sample_rate(self.sample_rate, source="Tracing"):
            return

        if not self.sample_rate:
            return

        # https://github.com/getsentry/sentry-python/blob/2.19.2/sentry_sdk/tracing.py#L1158
        self.sampled = Random(self.trace_id).random() < self.sample_rate  # noqa: S311


def make_transaction_info_event_processor(ctx: JsonRpcContext, name_generator: TransactionNameGenerator) -> Callable:
    def _event_processor(event, _):
        event["transaction_info"]["source"] = TRANSACTION_SOURCE_CUSTOM
        if ctx.method_route is not None:
            event["transaction"] = name_generator(ctx)

        return event

    return _event_processor


def default_transaction_name_generator(ctx: JsonRpcContext) -> str:
    return f"JRPC:{ctx.method_route.name}"


def prepend_jrpc_transaction_middleware():  # noqa: C901
    # prepend the jrpc_sentry_transaction_middleware to the middlewares list.
    # we cannot patch Entrypoint _init_ directly,  since objects can be created before invoking this integration

    def _prepend_transaction_middleware(self: Entrypoint):
        if not hasattr(self, "__patched_middlewares__"):
            original_middlewares = self.__dict__.get("middlewares", [])
            self.__patched_middlewares__ = original_middlewares

        # middleware was passed manually
        if jrpc_transaction_middleware in self.__patched_middlewares__:
            return self.__patched_middlewares__

        self.__patched_middlewares__ = [jrpc_transaction_middleware, *self.__patched_middlewares__]
        return self.__patched_middlewares__

    def _middleware_setter(self: Entrypoint, value):
        self.__patched_middlewares__ = value
        _prepend_transaction_middleware(self)

    Entrypoint.middlewares = property(_prepend_transaction_middleware, _middleware_setter)
