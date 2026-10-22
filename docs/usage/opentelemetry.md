# OpenTelemetry integration

HTTP-level instrumentation sees one `POST` route for every JSON-RPC method, HTTP 200 for every JSON-RPC error, and one request for a whole batch. `fastapi-jsonrpc` ships an OpenTelemetry middleware that works at the JSON-RPC level instead:

- one `SERVER` span per call, named after the method, including each call in a batch;
- JSON-RPC error codes on the span as `error.type` and `rpc.status_code`, with span status `ERROR`;
- the `rpc.server.call.duration` histogram, labelled by method and error code.

It follows the [OpenTelemetry JSON-RPC semantic conventions](https://github.com/open-telemetry/semantic-conventions/blob/6afd3ad9ada204137355c1d3431e0a225b6f37cc/docs/rpc/json-rpc.md) as of commit [`6afd3ad`](https://github.com/open-telemetry/semantic-conventions/tree/6afd3ad9ada204137355c1d3431e0a225b6f37cc/docs/rpc). Those conventions are still in Development, so attribute names may change before they become stable.

Install it as `pip install 'fastapi-jsonrpc[opentelemetry]'`. The extra depends only on `opentelemetry-api`; configure the SDK and exporters in your application as usual.

## Setup

```python
import fastapi_jsonrpc as jsonrpc
from fastapi_jsonrpc.contrib.opentelemetry import OpenTelemetryMiddleware

api_v1 = jsonrpc.Entrypoint(
    '/api/v1/jsonrpc',
    middlewares=[OpenTelemetryMiddleware(), *other_middlewares],
)
```

!!! warning "Put it first"
    `OpenTelemetryMiddleware` must be the **first** entry in `Entrypoint.middlewares`. A middleware only sees errors raised by middlewares entered after it, such as `InvalidRequest` for a malformed call, and spans created by later middlewares only nest under the call span if it is already current. Add it to the entrypoint, not to `@entrypoint.method(middlewares=...)`: method-level middlewares run after the method is resolved, so they never see `MethodNotFound` or `InvalidRequest`.

The call span is a child of whatever span is current, normally the HTTP server span from `opentelemetry-instrumentation-fastapi` or `-asgi`. The two work together: every JSON-RPC span of a batch sits under the single HTTP span.

### Options

| Option | Default | Meaning |
|---|---|---|
| `tracer_provider` | global provider | Where spans go. |
| `meter_provider` | global provider | Where the metric goes. |
| `enable_metrics` | `True` | `False` creates no histogram. |
| `record_exception` | `False` | Whether unhandled exceptions are recorded on the span. See [Exceptions](#exceptions). |
| `request_hook` | `None` | `hook(span, ctx)` called right after the span starts. |
| `response_hook` | `None` | `hook(span, ctx)` called before the span ends. |

## Spans

| Attribute | Value |
|---|---|
| span name | registered method name; `jsonrpc` when the method is unknown or missing |
| `rpc.system.name` | `jsonrpc` |
| `rpc.method` | registered method name; `_OTHER` for a name that isn't registered; absent when the request has no string `method` |
| `rpc.method_original` | the requested name, only when `rpc.method` is `_OTHER` |
| `jsonrpc.protocol.version` | `2.0` |
| `jsonrpc.request.id` | the request `id` as a string; absent for notifications and for `"id": null` |
| `fastapi_jsonrpc.request.type` | `call`, `notification` or `unknown`, see [Request type](#request-type) |
| `error.type`, `rpc.status_code` | the JSON-RPC error code as a string, e.g. `-32602`, only on errors |

The JSON-RPC conventions make `rpc.method` opt-in because a generic instrumentation can't bound the method names a client sends. Here the registered methods are that bound: any other name becomes `_OTHER`.

Outcomes:

| Outcome | Span status | `error.type` | `rpc.status_code` |
|---|---|---|---|
| result | `UNSET` | — | — |
| `BaseError`, including `MethodNotFound`, `InvalidParams` and your own errors | `ERROR` with the error's `MESSAGE` | code | code |
| unhandled exception, answered with `InternalError` | `ERROR` with `Internal error` | `-32603` | `-32603` |
| `HTTPException`, answered as an HTTP error | `ERROR` | exception class, e.g. `fastapi.exceptions.HTTPException` | — |
| cancellation | `UNSET` | — | — |

`UNSET` means no error status was assigned, not that the call is known to have completed successfully. Params and results are never recorded.

### Request type

`fastapi_jsonrpc.request.type` is a library-specific attribute, not an OpenTelemetry semantic convention. It is set on spans and on the metric:

| Value | Meaning |
|---|---|
| `call` | a validated request with an `id`, including `"id": null` |
| `notification` | a validated request without an `id` |
| `unknown` | no validated request is available, e.g. a call without a `method` or a batch item that isn't an object |

The type comes from the request the library already validated; the middleware never validates on its own, so a request that failed validation stays `unknown`. It classifies the request, so it doesn't say whether a notification's method was scheduled or finished. Error attributes are kept alongside it: a notification with invalid params is a `notification` with `error.type` `-32602`.

### Cancellation

Cancellation is propagated, not converted into an error. If the call is cancelled while it runs, the span, the response hook and the metric are finalized once, with `UNSET` status and no error attributes, and no exception is recorded. A method that catches the cancellation and returns a result is a normal success. A timeout inside the call, e.g. `asyncio.wait_for` in the method, raises `TimeoutError`, which is an unhandled exception and ends as `InternalError` (`-32603`).

The middleware only sees what happens inside it. A timeout or a client disconnect outside it doesn't cancel the call: the call keeps running and is measured until it really ends. An outer middleware can also change the final response after this one has finished, which is one more reason to put it first.

## Exceptions

By default an unhandled exception leaves only `error.type`, `rpc.status_code` and the `Internal error` status on the span: no exception event, no message, no stack trace. Exception messages often contain request data such as emails or phone numbers, and the client only sees `Internal error` anyway. This is stricter than most OpenTelemetry instrumentations, which record exceptions by default.

`record_exception` controls it:

```python
# record the exception as is: type, message and stack trace
OpenTelemetryMiddleware(record_exception=True)


# record only the exception type and the stack trace, without the message
def redact(exc: Exception) -> Exception | None:
    return RuntimeError(type(exc).__qualname__).with_traceback(exc.__traceback__)

OpenTelemetryMiddleware(record_exception=redact)
```

A callable receives the exception and returns the exception to record, or `None` to record nothing. If it raises, the middleware logs a warning and records nothing. `BaseError` responses are expected outcomes and are never recorded as exceptions.

## Metric

`rpc.server.call.duration` is a histogram in seconds with the bucket boundaries the conventions recommend: `0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 0.75, 1, 2.5, 5, 7.5, 10`. One measurement is recorded each time the middleware finishes, for every call and every notification, so the histogram count is the number of operations the middleware observed, not the number of completed background executions.

Attributes: `rpc.system.name`, `rpc.method` (registered name or `_OTHER`), `fastapi_jsonrpc.request.type`, and on errors `error.type` and `rpc.status_code`. The requested method name and the request id are never metric attributes, so a client can't create unlimited series.

A notification's measurement covers dispatch, not the method's run time, so filter by `fastapi_jsonrpc.request.type="call"` for method latency.

## Hooks

```python
def request_hook(span, ctx: jsonrpc.JsonRpcContext):
    span.set_attribute('app.tenant', ctx.http_request.headers.get('x-tenant', ''))


def response_hook(span, ctx: jsonrpc.JsonRpcContext):
    span.set_attribute('app.cached', ctx.http_response.headers.get('x-cache') == 'hit')


OpenTelemetryMiddleware(request_hook=request_hook, response_hook=response_hook)
```

- `request_hook` runs before any later middleware or the method. `ctx.request` raises `InvalidRequest` for a malformed call, so read `ctx.raw_request` or guard the access.
- `response_hook` runs after the outcome is on the span. `ctx.raw_response` and `ctx.exception` are available.
- A hook that raises is logged as a warning and changes neither the span nor the response.

Whatever a hook records is your choice: be careful with params, results and exception messages.

## What it doesn't cover

- **JSON parsing.** The body is parsed before any call exists, so a `ParseError` or an empty batch produces no JSON-RPC span. The HTTP span still covers it.
- **Shared dependencies.** `Entrypoint.dependencies` are solved once per HTTP request, before the calls start, outside every call span and the metric. If they raise a `BaseError`, each call span records that error.
- **Notification bodies.** For a notification the span and the measurement cover validation, dependencies and handing the method to the background scheduler; they end when the middleware exits. The method may start while the span is still open or after it has ended, and may keep running after it. Handing it over can include waiting for room in the scheduler's queue, so a notification's HTTP response isn't guaranteed to be immediate. Errors or cancellation in the method can happen after the span has ended and then don't appear on it. Spans the method creates still nest under the notification span. Tracing the method to its end is not part of this integration.
