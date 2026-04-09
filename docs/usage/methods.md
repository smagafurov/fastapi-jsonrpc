# Methods & parameters

A JSON-RPC method is a regular Python function decorated with `@entrypoint.method()`. Parameters are declared using the same FastAPI building blocks you already know — `Body`, `Header`, `Cookie`, `Depends`, and Pydantic models.

```python
import fastapi_jsonrpc as jsonrpc
from fastapi import Body
from pydantic import BaseModel

app = jsonrpc.API()
api_v1 = jsonrpc.Entrypoint('/api/v1/jsonrpc')


class Greeting(BaseModel):
    text: str
    language: str = 'en'


@api_v1.method()
def greet(
    name: str = Body(..., examples=['Ada']),
    loud: bool = Body(False),
) -> Greeting:
    text = f'Hello, {name}!'
    return Greeting(text=text.upper() if loud else text)


app.bind_entrypoint(api_v1)
```

## Declaring parameters

| FastAPI primitive | Ends up as                                   |
|-------------------|----------------------------------------------|
| `Body(...)`       | A field inside JSON-RPC `params`             |
| `Header(...)`     | An HTTP header on the enclosing POST request |
| `Cookie(...)`     | A cookie on the enclosing POST request       |
| Pydantic model    | A nested object inside `params`              |
| `Depends(...)`    | Reused via FastAPI's DI — see [Dependencies](dependencies.md) |

Return types must be JSON-serialisable. Pydantic models are rendered into the OpenAPI/OpenRPC schemas automatically.

## Async methods

`async def` methods are supported transparently:

```python
@api_v1.method()
async def fetch_user(user_id: int = Body(...)) -> dict:
    return await users_repo.get(user_id)
```

## Batching and notifications

JSON-RPC 2.0 batches and notifications (requests without `id`) are handled automatically. Each request in a batch gets its own dependency resolution — see [Dependencies](dependencies.md) for per-batch vs per-request behaviour.

## Multiple entrypoints

You can mount several entrypoints on the same `API`:

```python
api_v1 = jsonrpc.Entrypoint('/api/v1/jsonrpc')
api_v2 = jsonrpc.Entrypoint('/api/v2/jsonrpc')

app.bind_entrypoint(api_v1)
app.bind_entrypoint(api_v2)
```

Each entrypoint has its own set of default errors, middlewares and dependencies.
