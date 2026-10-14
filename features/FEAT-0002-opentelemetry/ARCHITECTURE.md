# FEAT-0002: Architecture

Decisions behind [README.md](README.md), with the reasons for each.

## D1. Placement and dependencies

- Module: `fastapi_jsonrpc/contrib/opentelemetry/`.
- Extra: `opentelemetry = ["opentelemetry-api>=1.30"]`. 1.30.0 is the first release whose `Meter.create_histogram` accepts `explicit_bucket_boundaries_advisory` (opentelemetry-python CHANGELOG, "Add support for explicit bucket boundaries advisory for Histograms").
- No `opentelemetry-semantic-conventions` dependency. The JSON-RPC attributes are still Development and RC, and the package's generated constants follow released spec versions, while we target an unreleased commit (D3). Attribute keys are module-level string constants in our code.
- Dev group adds `opentelemetry-sdk` (in-memory span exporter and metric reader) and `opentelemetry-instrumentation-fastapi` (coexistence tests).

**Why:** library users who don't trace should not pull in the SDK; the API package is a no-op without one.

## D2. Explicit middleware

```python
from fastapi_jsonrpc.contrib.opentelemetry import OpenTelemetryMiddleware

api_v1 = jsonrpc.Entrypoint(
    '/api/v1/jsonrpc',
    middlewares=[OpenTelemetryMiddleware(), *other_middlewares],
)
```

`OpenTelemetryMiddleware` is a callable `(ctx) -> AsyncContextManager`, matching `JsonRpcMiddleware`. It must be the **first** middleware in `Entrypoint.middlewares`:

- `JsonRpcContext.enter_middlewares` enters middlewares in order, each followed by its own `_handle_exception()` guard (`fastapi_jsonrpc/__init__.py`, `enter_middlewares`). A later middleware that reads `ctx.request` raises `InvalidRequest` for a malformed call, and only middlewares entered earlier see that error.
- The span has to be current while later middlewares run, so their own spans nest under it.

It belongs on the entrypoint, not on `MethodRoute.middlewares`. Method-level middlewares run after method resolution, so they would miss `MethodNotFound` and `InvalidRequest`.

Constructor:

```python
OpenTelemetryMiddleware(
    *,
    tracer_provider: TracerProvider | None = None,   # default: global
    meter_provider: MeterProvider | None = None,     # default: global
    enable_metrics: bool = True,
    record_exception: bool | Callable[[Exception], Exception | None] = False,
    request_hook: Callable[[Span, JsonRpcContext], None] | None = None,
    response_hook: Callable[[Span, JsonRpcContext], None] | None = None,
)
```

Tracer and histogram are created once in `__init__` with instrumentation scope `fastapi_jsonrpc` and the package version.

**Why explicit:** the maintainer asked for it, and it avoids the class-attribute patching `contrib/sentry/jrpc.py` uses to prepend its middleware.

## D3. Semantic conventions target

Target: `open-telemetry/semantic-conventions` `main` at [`6afd3ad`](https://github.com/open-telemetry/semantic-conventions/tree/6afd3ad9ada204137355c1d3431e0a225b6f37cc/docs/rpc) (2026-10-13).

- The latest release, v1.44.0 (2026-08-04), still names the status attribute `rpc.response.status_code`. [#3921](https://github.com/open-telemetry/semantic-conventions/pull/3921) renamed it to `rpc.status_code` the next day. We use `rpc.status_code` and switch the pinned reference to the first release tag that contains it.
- The JSON-RPC span conventions are Development; the RPC attributes are RC. The docs page states that attribute names may change before they are stable, and the module docstring names the commit above.

## D4. Span shape

| Item | Value |
|---|---|
| Kind | `SERVER` |
| Parent | current context (normally the HTTP server span from ASGI/FastAPI instrumentation) |
| Name | registered method name; `jsonrpc` when the method is unknown or missing |
| `rpc.system.name` | `jsonrpc`, set at creation |
| `rpc.method` | registered method name, or `_OTHER` for an unregistered name; absent when the request has no string `method`; set at creation |
| `rpc.method_original` | requested name, only when `rpc.method` is `_OTHER` |
| `jsonrpc.protocol.version` | `2.0` (the conventions require it whenever it isn't `1.0`) |
| `jsonrpc.request.id` | `str(id)`; absent for notifications and for `"id": null` |
| `rpc.status_code` | error code as a string, only on error responses |
| `error.type` | see D5 |

### Method resolution at span start

`rpc.method` should be present at creation because samplers use it. At that point `ctx.method_route` is still `None` on the main entrypoint path (`EntrypointRoute.handle_req` sets it after middlewares are entered), and `ctx.request` may raise `InvalidRequest`. So the middleware:

- reads `ctx.raw_request` defensively: a `dict` with a `str` `method`, otherwise "missing";
- checks the name against the names of the entrypoint's `MethodRoute`s (`ctx.entrypoint.routes`), cached per entrypoint because one middleware instance may serve several.

On the per-method path (`MethodRoute.handle_req_to_resp`), `ctx.method_route` is already set, but the same lookup gives the same answer, so there is one code path.

### Why `rpc.method` is on by default

For JSON-RPC the conventions mark `rpc.method` **Opt-In**: general-purpose instrumentations "SHOULD NOT set this attribute by default and SHOULD provide a way to configure the list of recognized RPC methods". That rule guards against unbounded cardinality when an instrumentation cannot know the method set. Here the registered methods *are* that configured list, and anything else collapses to `_OTHER`, so cardinality is bounded by the application's own code.

## D5. Outcome mapping

The middleware wraps `yield` in `try/except Exception` and always re-raises. On the success path `ctx.raw_response` is already set when the middleware exits (`handle_req_to_resp` calls `ctx.on_raw_response` inside the context). On the error path the inner `_handle_exception` guard has already populated `ctx.raw_response`, `ctx.exception` and `ctx.is_unhandled_exception` before the exception reaches us.

| Outcome | Span status | `error.type` | `rpc.status_code` | Exception event |
|---|---|---|---|---|
| Result | unset | — | — | — |
| `BaseError` (incl. `MethodNotFound`, `InvalidParams`, user errors) | `ERROR`, description = response `error.message` (the class's static `MESSAGE`) | code as string | code as string | never |
| Unhandled exception → `InternalError` | `ERROR`, description `Internal error` | `-32603` | `-32603` | only if `record_exception` allows (D6) |
| `HTTPException` (propagates as an HTTP response, no JSON-RPC body) | `ERROR`, no description | fully qualified class name | — | never |

Notes:

- The conventions say all JSON-RPC error codes SHOULD count as errors, so every error response sets status `ERROR`.
- `error.type` uses the code, not the Python class, because a status code was returned. The class-name rule applies only when no code exists, which is the `HTTPException` row.
- Span status descriptions never use `str(exc)`.
- The tracer's span context manager must be entered with `record_exception=False, set_status_on_exception=False`. Otherwise the re-raised exception would be recorded and the span status overwritten by the OTel SDK, bypassing D6.

## D6. Exception recording

`record_exception` controls only unhandled exceptions (the `InternalError` row):

| Value | Behaviour |
|---|---|
| `False` (default) | no event |
| `True` | `span.record_exception(exc)`: type, message, stack trace |
| `callable(exc)` | returns an exception to record instead (e.g. a sanitised copy), or `None` to skip |

To keep the original stack trace, the callable returns `replacement.with_traceback(exc.__traceback__)`. The docs show that pattern. A callable that raises is logged at `WARNING` and nothing is recorded, so the default stays the safe side.

**Why off by default:** exception messages often contain request data (emails, phone numbers, IDs), and the response already tells the client only `Internal error`. Recording more than the client sees should be a deliberate choice. This is stricter than OTel's usual `record_exception=True`, and the docs say so.

## D7. Metric

- Instrument: `rpc.server.call.duration`, histogram, unit `s`, `explicit_bucket_boundaries_advisory=[0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 0.75, 1, 2.5, 5, 7.5, 10]`.
- Measured with `time.perf_counter()` from middleware entry to exit, so it covers the same work as the span.
- Attributes: `rpc.system.name`, `rpc.method` (registered or `_OTHER`; absent when missing), `error.type`, `rpc.status_code`. Never `rpc.method_original` or the request id.
- `enable_metrics=False` creates no instrument.

## D8. Hooks

- `request_hook(span, ctx)` runs right after the span starts and before `yield`. `ctx.request` may raise for malformed input, so the docs tell hook authors to read `ctx.raw_request` or guard the access.
- `response_hook(span, ctx)` runs after the outcome mapping and before the span ends. `ctx.raw_response` and `ctx.exception` are available. Whatever the hook records is the user's choice; the docs warn about params, results and exception messages.
- A hook that raises is logged at `WARNING`. It never changes the JSON-RPC response and never stops the span from ending.

Hooks only add attributes. They are not how exception data is controlled (D6), which is what the maintainer asked for.

## D9. What the middleware does not cover

Documented on the docs page:

1. **JSON parsing.** `EntrypointRoute.handle_http_request` parses the body before any call exists. A `ParseError` or empty-batch `InvalidRequest` produces no JSON-RPC span; the HTTP span still covers it.
2. **Shared dependencies.** `Entrypoint.dependencies` are solved once per HTTP request in `handle_body`, before calls are scheduled. Their time is outside every call span and the metric. If they raise a `BaseError`, each call re-raises it inside `MethodRoute.handle_req`, so each call span still records the error.
3. **Notification bodies.** For a notification, `MethodRoute.handle_req` validates params, solves dependencies, then spawns the method body on the aiojobs scheduler and returns `{}`. The span and the metric cover dispatch only; the method body runs after the span has ended. Exceptions from the body go to the scheduler's exception handler and are not on the span. Spans the body creates still nest under the notification span (OTel allows children to outlive parents).

Decided: the first PR documents this and adds no span around the background body. That can be a follow-up if users ask for it.

## D10. Batch concurrency and context propagation

Each call runs as an aiojobs job (`handle_body` → `scheduler.spawn`). `asyncio.create_task` copies the current `contextvars` context, so a job started immediately sees the HTTP request's OTel context and the call span gets the right parent.

**Problem found during planning:** the scheduler is shared per entrypoint across all HTTP requests and defaults to `limit=100`. Jobs over the limit are queued and later started from another job's done callback, in *that* job's context. A reproduction (scratch script, `aiojobs.Scheduler(limit=1)`, three requests each setting a `ContextVar` before `spawn`) shows queued jobs seeing the first request's value:

```
expected=req-0 seen=req-0 OK
expected=req-1 seen=req-0 WRONG CONTEXT
expected=req-2 seen=req-0 WRONG CONTEXT
```

With more than 100 calls in flight per entrypoint, call spans would attach to the wrong HTTP span and trace. This affects every `contextvars` user (including `contrib.sentry` and any logging context), not just OpenTelemetry.

**Decided:** a separate core fix, landed before this feature. Capture `contextvars.copy_context()` at spawn time and restore it inside the job. Python 3.10 has no `create_task(context=...)`, so the job coroutine sets each captured variable at its start. The task runs in its own context copy, so nothing leaks. That fix gets its own regression test. The OTel PR then adds a test that a batch larger than a small scheduler `limit` keeps every span under the right parent.

## D11. Testing

- New directory `tests/otel/` with its own `conftest.py`, following `tests/sentry/`. It can't be named `tests/opentelemetry/`: pytest puts `tests/` on `sys.path`, and that package would shadow the real `opentelemetry` namespace package.
- Fixtures build a local `TracerProvider` with `InMemorySpanExporter` + `SimpleSpanProcessor`, and a `MeterProvider` with `InMemoryMetricReader`, and pass them to the middleware. No global provider mutation, so tests stay isolated.
- The coexistence test uses `FastAPIInstrumentor.instrument_app(app, tracer_provider=...)` on the same provider and asserts parent/child links and span counts.
- The no-SDK test runs with the API's default no-op providers.
- Unhandled-exception tests use `assert_log_errors(...)`, because the core logs them at `ERROR` and the autouse `check_no_errors` fixture would otherwise fail the test.
