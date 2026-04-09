# Sentry integration

`fastapi-jsonrpc` ships with a Sentry integration tailored for JSON-RPC:

- The JSON-RPC method name becomes the **transaction name** (instead of the single HTTP route shared by all methods).
- For batch requests, the whole batch is a **single transaction** and each method call is a **span** inside it.
- Available as `fastapi_jsonrpc.contrib.sentry.FastApiJsonRPCIntegration`.

## Setup

```python
import sentry_sdk
from fastapi_jsonrpc.contrib.sentry import FastApiJsonRPCIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration
from sentry_sdk.integrations.fastapi import FastApiIntegration


sentry_sdk.init(
    dsn='...',
    integrations=[FastApiJsonRPCIntegration()],
    # If you do not use regular REST-like routes, you can disable the other
    # integrations for performance:
    disabled_integrations=[StarletteIntegration, FastApiIntegration],
)
```

## What you get

- Transactions grouped by JSON-RPC method name — not by HTTP path.
- Proper parent/child relationship for batches.
- Exceptions raised from methods are captured with full context.

!!! warning "Implicit integration is deprecated"
    Before the explicit integration existed, `fastapi-jsonrpc` could attach to Sentry automatically when `sentry-sdk` was importable. That path is deprecated and will be removed in a future major release — always configure `FastApiJsonRPCIntegration()` explicitly.
