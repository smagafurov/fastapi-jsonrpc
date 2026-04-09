# Middlewares

JSON-RPC middlewares wrap every JSON-RPC call with an `async with`-style context manager. They have access to the whole `JsonRpcContext`: the raw request, the raw response and any exception that occurred.

Middlewares are a good place for:

- request/response logging
- metrics and tracing spans
- propagating correlation IDs
- setting up per-call `contextvars`

## Defining a middleware

```python
import logging
from contextlib import asynccontextmanager
import fastapi_jsonrpc as jsonrpc

logger = logging.getLogger(__name__)


@asynccontextmanager
async def logging_middleware(ctx: jsonrpc.JsonRpcContext):
    logger.info('Request: %r', ctx.raw_request)
    try:
        yield
    finally:
        logger.info('Response: %r', ctx.raw_response)
```

Register it on the entrypoint:

```python
api_v1 = jsonrpc.Entrypoint(
    '/api/v1/jsonrpc',
    middlewares=[logging_middleware],
)
```

## The `JsonRpcContext`

Inside a middleware you get a `JsonRpcContext` instance with (among others):

- `ctx.raw_request` — the parsed-but-not-validated JSON-RPC request dict.
- `ctx.raw_response` — the response dict that will be sent back. Mutating or replacing it is allowed.
- `ctx.exception` — the exception raised during method execution, if any.
- `ctx.http_request` / `ctx.http_response` — the underlying HTTP `Request` and `Response` objects.
- `ctx.method_route` — the matched method route (if any).
- `ctx.background_tasks` — the FastAPI `BackgroundTasks` collector.

You can also read these values anywhere in your code:

```python
from fastapi_jsonrpc import get_jsonrpc_context, get_jsonrpc_method, get_jsonrpc_request_id

ctx = get_jsonrpc_context()
method = get_jsonrpc_method()
request_id = get_jsonrpc_request_id()
```

These are powered by `contextvars`, so they are safe across `async` boundaries.

## Batch vs. per-call

A middleware is entered per JSON-RPC call, so inside a batch request it runs for every item of the batch. If you need a single hook for an entire batch, use entrypoint-level `dependencies` (see [Dependencies](dependencies.md)). For the exact guarantees, see `tests/test_middlewares.py`.
