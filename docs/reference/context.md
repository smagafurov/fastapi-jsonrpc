# `jsonrpc.JsonRpcContext`

A per-call context object. Middlewares receive it as their only argument; any code running inside a JSON-RPC call can obtain it via `get_jsonrpc_context()`.

## Attributes

- **`entrypoint: Entrypoint`** — the entrypoint handling this call.
- **`raw_request: Any`** — the parsed JSON-RPC request dict (not yet validated against `JsonRpcRequest`).
- **`raw_response: dict | None`** — the response dict that will be sent back. Assigning a new value runs it through the `on_raw_response` normaliser: the `id` is taken from `raw_request`, exceptions are converted into an error response, unhandled exceptions are turned into `InternalError`. Mutating the existing dict in-place bypasses the normaliser.
- **`exception: Exception | None`** — the exception raised by the method, if any.
- **`is_unhandled_exception: bool`** — `True` if the exception was not a `BaseError`/`HTTPException`, i.e. it was converted to `InternalError`.
- **`http_request: starlette.requests.Request`** — the wrapping HTTP request.
- **`http_response: starlette.responses.Response`** — the HTTP response that will be returned.
- **`background_tasks: fastapi.BackgroundTasks`** — the background task queue.
- **`method_route: MethodRoute | None`** — the matched method route (or `None` if the request failed before dispatch).
- **`request: JsonRpcRequest`** — a validated `JsonRpcRequest` (cached). Raises `InvalidRequest` if validation fails.

## Helpers

```python
from fastapi_jsonrpc import (
    get_jsonrpc_context,
    get_jsonrpc_request_id,
    get_jsonrpc_method,
)

ctx = get_jsonrpc_context()       # the current JsonRpcContext
rid = get_jsonrpc_request_id()    # value of "id" from the raw request
name = get_jsonrpc_method()       # value of "method" from the raw request
```

All three read from a `contextvars.ContextVar` set for the duration of the call, so they work from anywhere in your async call graph.

## Middleware signature

```python
JsonRpcMiddleware = Callable[[JsonRpcContext], AbstractAsyncContextManager]
```

Implementations are typically written with `@asynccontextmanager`:

```python
@asynccontextmanager
async def my_middleware(ctx: jsonrpc.JsonRpcContext):
    # setup
    try:
        yield
    finally:
        # teardown — ctx.raw_response is populated here
        ...
```
