import sentry_sdk

if not hasattr(sentry_sdk, 'new_scope'):
    # `new_scope` marks sentry-sdk 2.x. On 1.x `sentry_sdk.init()` would accept the
    # integration and the first request would then die on a missing `isolation_scope`
    raise RuntimeError(
        f"fastapi-jsonrpc supports only sentry-sdk 2.*, got {sentry_sdk.VERSION}. "
        f"Upgrade sentry-sdk to use FastApiJsonRPCIntegration."
    )

from .jrpc import TransactionNameGenerator, jrpc_transaction_middleware  # noqa: E402
from .integration import FastApiJsonRPCIntegration  # noqa: E402

__all__ = [
    "FastApiJsonRPCIntegration",
    "TransactionNameGenerator",
    "jrpc_transaction_middleware",
]
