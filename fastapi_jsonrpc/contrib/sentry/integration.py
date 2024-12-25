from typing import Optional
from fastapi_jsonrpc import MethodRoute, EntrypointRoute
from sentry_sdk.integrations import Integration

from .http import set_shared_sentry_context
from .jrpc import TransactionNameGenerator, default_transaction_name_generator, prepend_jrpc_transaction_middleware


class FastApiJsonRPCIntegration(Integration):
    identifier = "FastApiJsonRPCIntegration"
    _already_enabled: bool = False

    def __init__(self, transaction_name_generator: Optional[TransactionNameGenerator] = None):
        self.transaction_name_generator = transaction_name_generator or default_transaction_name_generator

    @staticmethod
    def setup_once():
        if FastApiJsonRPCIntegration._already_enabled:
            return

        prepend_jrpc_transaction_middleware()
        set_shared_sentry_context(MethodRoute)
        set_shared_sentry_context(EntrypointRoute)

        FastApiJsonRPCIntegration._already_enabled = True
