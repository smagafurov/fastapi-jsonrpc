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
