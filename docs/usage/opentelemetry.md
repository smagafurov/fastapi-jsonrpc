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
| `error.type`, `rpc.status_code` | the JSON-RPC error code as a string, e.g. `-32602`, only on errors |

The JSON-RPC conventions make `rpc.method` opt-in because a generic instrumentation can't bound the method names a client sends. Here the registered methods are that bound: any other name becomes `_OTHER`.

Outcomes:

| Outcome | Span status | `error.type` | `rpc.status_code` |
|---|---|---|---|
| result | unset | — | — |
| `BaseError`, including `MethodNotFound`, `InvalidParams` and your own errors | `ERROR` with the error's `MESSAGE` | code | code |
| unhandled exception, answered with `InternalError` | `ERROR` with `Internal error` | `-32603` | `-32603` |
| `HTTPException`, answered as an HTTP error | `ERROR` | exception class, e.g. `fastapi.exceptions.HTTPException` | — |

Params and results are never recorded.

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

`rpc.server.call.duration` is a histogram in seconds with the bucket boundaries the conventions recommend: `0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 0.75, 1, 2.5, 5, 7.5, 10`. One measurement is recorded per call.

Attributes: `rpc.system.name`, `rpc.method` (registered name or `_OTHER`), and on errors `error.type` and `rpc.status_code`. The requested method name and the request id are never metric attributes, so a client can't create unlimited series.

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
- **Notification bodies.** For a notification the middleware covers validation and dependencies; the method itself runs in the background after the span has ended. Its exceptions are not on the span, and the metric doesn't include its run time. Spans the method creates still nest under the notification span.
