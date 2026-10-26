# FEAT-0002: OpenTelemetry integration

Tracking issue: [smagafurov/fastapi-jsonrpc#116](https://github.com/smagafurov/fastapi-jsonrpc/issues/116).
Branch: `feature/opentelemetry-integration`.

## Problem

HTTP-level instrumentation (`opentelemetry-instrumentation-fastapi`, Prometheus middlewares) cannot see individual JSON-RPC calls:

- every method shares the entrypoint route (e.g. `POST /api/v1/jsonrpc`), so per-method rate and latency are lost;
- JSON-RPC errors are returned with HTTP 200, so error rates read as zero;
- a batch is one HTTP request, however many calls it carries.

OpenTelemetry has JSON-RPC semantic conventions ([JSON-RPC](https://github.com/open-telemetry/semantic-conventions/blob/main/docs/rpc/json-rpc.md), [RPC spans](https://github.com/open-telemetry/semantic-conventions/blob/main/docs/rpc/rpc-spans.md), [RPC metrics](https://github.com/open-telemetry/semantic-conventions/blob/main/docs/rpc/rpc-metrics.md)). `opentelemetry-python-contrib` prefers native instrumentation inside the library, and `contrib/sentry` already sets that pattern here.

## Agreed with the maintainer

From the issue thread (spumer, 2026-10-14):

1. Lives in `fastapi_jsonrpc/contrib/opentelemetry/`, behind an `opentelemetry` extra that depends only on `opentelemetry-api`.
2. Explicit middleware, documented as the first entry in `Entrypoint.middlewares`. Auto-prepend (an instrumentor like `contrib.sentry`) is a separate discussion.
3. The `rpc.server.call.duration` metric ships in the first PR.
4. The PR names the semconv version it targets, documents what the middleware does not cover, and gives users control over what an unhandled exception puts into the trace.

## Scope

### S1. `OpenTelemetryMiddleware`

One `SERVER` span per JSON-RPC call, including each call in a batch, as a child of the current span (normally the HTTP server span). Attributes, naming and status follow [ARCHITECTURE.md](ARCHITECTURE.md#d4-span-shape).

### S2. Duration metric

`rpc.server.call.duration` histogram in seconds, with the bucket boundaries the conventions recommend. Low-cardinality attributes only. The requested method name is never a metric attribute. Can be turned off.

### S3. Exception recording, off by default

Unhandled exceptions mark the span as an error with `-32603` but record no exception event, no message and no stack trace. Opt in with `record_exception=True`, or pass a callable that redacts, replaces or drops the exception.

### S4. Hooks

`request_hook(span, ctx)` when the span starts and `response_hook(span, ctx)` before it ends, so users can add their own attributes. Params and results are never recorded by the library.

### S5. Packaging and docs

- `opentelemetry` extra in `pyproject.toml`; test-only packages in the `dev` group.
- A docs page under `docs/usage/`, linked from `zensical.toml`.
- `docs/llms.txt` and `docs/llms-full.txt` updated with the new public surface.

## Out of scope

- An instrumentor that prepends the middleware to every `Entrypoint` automatically.
- Client-side spans (this library is a server).
- Opt-in `server.address` / `server.port` attributes.
- Spans or timing for JSON body parsing and shared (batch-level) dependencies. Documented instead (see [D9](ARCHITECTURE.md#d9-what-the-middleware-does-not-cover)).
- An `OTEL_SEMCONV_STABILITY_OPT_IN` migration path. This is a new integration with no older attribute names to keep.

## Acceptance criteria

### AC1. Single call
- A successful call produces one `SERVER` span named after the method, parented to the active span, with `rpc.system.name="jsonrpc"`, `rpc.method`, `jsonrpc.protocol.version="2.0"` and `jsonrpc.request.id`.
- Span status is unset. `rpc.status_code` and `error.type` are absent.

### AC2. Batch
- A batch of N calls produces N sibling spans under the same parent span, each with its own method name and request id.

### AC3. Notification
- A notification produces a span without `jsonrpc.request.id`.
- A call with `"id": null` also has no `jsonrpc.request.id`.

### AC4. Unknown or malformed method
- An unregistered method gives span name `jsonrpc`, `rpc.method="_OTHER"`, `rpc.method_original=<requested name>`, and `error.type` / `rpc.status_code` = `-32601`.
- A call without a usable `method` (`InvalidRequest`) gives span name `jsonrpc`, no `rpc.method`, and `-32600`.
- Metric points for both cases carry `rpc.method="_OTHER"` or no `rpc.method`, never the requested name.

### AC5. `BaseError` raised by a method
- Span status `ERROR` with the error's `MESSAGE` as description; `error.type` and `rpc.status_code` set to the code as a string (e.g. `-32602`, or a user code such as `6001`).
- No exception event in any configuration.

### AC6. Unhandled exception
- Default: span status `ERROR` with description `Internal error`; `error.type` and `rpc.status_code` = `-32603`; **no** exception event; `str(exc)` appears nowhere on the span.
- `record_exception=True`: an exception event with type, message and stack trace.
- Callable returning a replacement exception: the event carries the replacement, not the original.
- Callable returning `None`: no event.

### AC7. Metric
- One `rpc.server.call.duration` data point per call, unit `s`, with the recommended explicit bucket boundaries.
- Attributes are limited to `rpc.system.name`, `rpc.method` (registered name or `_OTHER`), `fastapi_jsonrpc.request.type` (`call`, `notification` or `unknown`), `error.type`, `rpc.status_code`.
- Request ids and raw, unregistered method names never appear as metric attributes.
- Turning the metric off creates no instrument.

### AC8. Hooks
- `request_hook` runs after the span starts and sees the span and context; `response_hook` runs before the span ends and sees `ctx.raw_response`.
- An exception raised inside a hook is logged and does not change the JSON-RPC response.

### AC9. Coexistence with HTTP instrumentation
- With `opentelemetry-instrumentation-fastapi` active, every JSON-RPC span is a child of the HTTP server span for the request that carried it, single and batch alike.
- No duplicate spans.

### AC10. No SDK configured
- With only `opentelemetry-api` installed (no SDK, no-op providers), responses are identical to running without the middleware.

### AC11. Quality gates
- `uv run --frozen python -m pytest` and `uv run --frozen python -m mypy` pass.
- The `tests-latest-fastapi-pydantic.yml` matrix passes.

## Implementation order (TDD)

1. Packaging: extra, dev dependencies, empty module, test harness with in-memory exporter and metric reader.
2. S1 span for a single successful call (AC1), then batch (AC2) and notification (AC3).
3. Error mapping: unknown method, invalid request, `BaseError` (AC4, AC5).
4. S3 unhandled exceptions and the `record_exception` option (AC6).
5. S2 metric (AC7).
6. S4 hooks (AC8).
7. Coexistence and no-SDK tests (AC9, AC10).
8. S5 docs.

Each step: failing test → minimal code → refactor.

## Decisions taken during planning

1. **aiojobs context loss under load.** Calls queued behind the scheduler's `limit` run in the wrong `contextvars` context, so their spans attach to another request's HTTP span. This is a pre-existing core bug, not specific to OpenTelemetry. Decision: fix it in its own PR, merged before this feature. Details: [D10](ARCHITECTURE.md#d10-batch-concurrency-and-context-propagation).
2. **Notification method bodies run after the span ends.** Decision: the first PR documents the limitation and adds no second span around the background execution. Details: [D9](ARCHITECTURE.md#d9-what-the-middleware-does-not-cover).
