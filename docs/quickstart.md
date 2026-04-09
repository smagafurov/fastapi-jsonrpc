# Quickstart

A minimal JSON-RPC service with a custom error.

## 1. Write the app

`app.py`:

```python
import fastapi_jsonrpc as jsonrpc
from pydantic import BaseModel
from fastapi import Body


app = jsonrpc.API()
api_v1 = jsonrpc.Entrypoint('/api/v1/jsonrpc')


class MyError(jsonrpc.BaseError):
    CODE = 5000
    MESSAGE = 'My error'

    class DataModel(BaseModel):
        details: str


@api_v1.method(errors=[MyError])
def echo(
    data: str = Body(..., examples=['hello']),
) -> str:
    if data == 'error':
        raise MyError(data={'details': 'boom'})
    return data


app.bind_entrypoint(api_v1)


if __name__ == '__main__':
    import uvicorn
    uvicorn.run('app:app', port=5000, access_log=False)
```

## 2. Run it

```bash
uvicorn app:app --port 5000
```

## 3. Call it

```bash
curl -s http://127.0.0.1:5000/api/v1/jsonrpc \
  -H 'content-type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"echo","params":{"data":"hello"}}'
```

Response:

```json
{"jsonrpc": "2.0", "id": 1, "result": "hello"}
```

Trigger the custom error:

```bash
curl -s http://127.0.0.1:5000/api/v1/jsonrpc \
  -H 'content-type: application/json' \
  -d '{"jsonrpc":"2.0","id":2,"method":"echo","params":{"data":"error"}}'
```

```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "error": {
    "code": 5000,
    "message": "My error",
    "data": {"details": "boom"}
  }
}
```

## 4. Explore the schema

- Swagger UI — <http://127.0.0.1:5000/docs>
- OpenAPI — <http://127.0.0.1:5000/openapi.json>
- OpenRPC — <http://127.0.0.1:5000/openrpc.json>

Each method is exposed as its own POST route in Swagger (for example `POST /api/v1/jsonrpc/echo`), so you can invoke it interactively with the built-in "Try it out" button.

Next: [Methods & parameters](usage/methods.md).
