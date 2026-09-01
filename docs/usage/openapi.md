# OpenAPI & OpenRPC

`fastapi-jsonrpc` exposes three schemas out of the box:

| URL              | Description                                   |
|------------------|-----------------------------------------------|
| `/docs`          | Swagger UI for interactive calls              |
| `/openapi.json`  | OpenAPI 3.x schema (powered by FastAPI)       |
| `/openrpc.json`  | OpenRPC 1.x schema for the JSON-RPC service   |

## How methods are rendered in OpenAPI

Every JSON-RPC method is mounted as an individual POST route under the entrypoint path:

```
POST /api/v1/jsonrpc/echo
POST /api/v1/jsonrpc/withdraw
```

The entrypoint itself (`POST /api/v1/jsonrpc`) is also registered and accepts the full JSON-RPC request (including batches). The per-method routes are what Swagger UI calls "Try it out" against, so users can exercise a single method without constructing a JSON-RPC envelope by hand.

Request parameters, response model, declared errors and dependency-derived headers/body fields all end up in the schema automatically.

## OpenRPC

The OpenRPC schema is generated from the same metadata as OpenAPI and is served from `openrpc_url` (default `/openrpc.json`). To turn it off, pass `openrpc_url=None` to `API()`:

```python
app = jsonrpc.API(openrpc_url=None)
```

### Which endpoint serves a method

One OpenRPC document can describe several entrypoints, so every method carries a `servers` list pointing at the HTTP endpoint that actually accepts it:

```python
app = jsonrpc.API()
api_v1 = jsonrpc.Entrypoint('/api/v1/jsonrpc')
api_v2 = jsonrpc.Entrypoint('/api/v2/jsonrpc')

@api_v1.method()
def legacy_echo(value: str = Body(...)) -> str:
    return value

@api_v2.method()
def echo(value: str = Body(...)) -> str:
    return value

app.bind_entrypoint(api_v1)
app.bind_entrypoint(api_v2)
```

```json
{
  "methods": [
    {"name": "legacy_echo", "servers": [{"name": "/api/v1/jsonrpc", "url": "/api/v1/jsonrpc"}]},
    {"name": "echo", "servers": [{"name": "/api/v2/jsonrpc", "url": "/api/v2/jsonrpc"}]}
  ]
}
```

This is schema fidelity, not client-side routing: a reader of the document can tell where to send each call, but consumers are free to ignore `Method.servers`, and several OpenRPC tools currently use only the root `servers`.

When you configure `servers` on `API()`, each of them is reused for every method with the entrypoint path appended to its URL; `root_path` and `root_path_in_servers` behave as in FastAPI. Without any configured server the method server is the plain entrypoint path.

Registering the same method on two entrypoints is allowed while both declarations are identical — the method appears once with both servers. OpenRPC requires method names to be unique, so two different contracts under one name raise a `RuntimeError` naming the method and both entrypoints instead of emitting an invalid document.

## Customising component names

By default `fastapi-jsonrpc` gives its generated Pydantic models short, human-friendly names. If you need the raw FastAPI naming (e.g. to avoid collisions with your own components), set:

```python
app = jsonrpc.API(fastapi_jsonrpc_components_fine_names=False)
```

## Tags, summaries, descriptions

All `APIRouter`/`APIRoute` metadata is respected. Pass `tags=`, `summary=`, `description=`, `responses=` etc. to `@entrypoint.method(...)` just as you would with a FastAPI endpoint:

```python
@api_v1.method(
    tags=['accounts'],
    summary='Withdraw money from an account',
)
def withdraw(...): ...
```
