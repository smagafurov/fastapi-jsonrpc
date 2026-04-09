# Errors

Errors in `fastapi-jsonrpc` are Python classes that inherit from `jsonrpc.BaseError`. They carry a JSON-RPC error `CODE`, a human-readable `MESSAGE`, and — optionally — a typed `DataModel` that is included in both the response and the generated schema.

## A custom error

```python
import fastapi_jsonrpc as jsonrpc
from pydantic import BaseModel


class NotEnoughMoney(jsonrpc.BaseError):
    CODE = 6001
    MESSAGE = 'Not enough money'

    class DataModel(BaseModel):
        balance: int
        currency: str
```

Raising it:

```python
raise NotEnoughMoney(data={'balance': 42, 'currency': 'USD'})
```

Response:

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "error": {
    "code": 6001,
    "message": "Not enough money",
    "data": {"balance": 42, "currency": "USD"}
  }
}
```

## Declaring errors on a method

List the errors a method can produce so they appear in the OpenAPI/OpenRPC schema:

```python
@api_v1.method(errors=[NotEnoughMoney])
def withdraw(amount: int = Body(...)) -> int:
    ...
```

## Entrypoint-wide errors

Errors that any method on an entrypoint may raise (for example auth errors) can be declared once on the `Entrypoint`:

```python
common_errors = [AuthError, AccountNotFound]
common_errors.extend(jsonrpc.Entrypoint.default_errors)

api_v1 = jsonrpc.Entrypoint('/api/v1/jsonrpc', errors=common_errors)
```

`Entrypoint.default_errors` contains the JSON-RPC 2.0 spec errors (`ParseError`, `InvalidRequest`, `MethodNotFound`, `InvalidParams`, `InternalError`).

## Built-in errors

`fastapi_jsonrpc` exposes the JSON-RPC 2.0 standard errors as classes you can catch or subclass:

- `ParseError` (`-32700`)
- `InvalidRequest` (`-32600`)
- `MethodNotFound` (`-32601`)
- `InvalidParams` (`-32602`)
- `InternalError` (`-32603`)

Any unhandled exception raised from a method is converted to `InternalError` and logged via the standard library `logging` module.

## Typed error data

When `DataModel` is set, the value passed to `raise MyError(data=...)` is validated and re-serialised through Pydantic. This means you get a single place to describe the shape of error data, and it automatically ends up in Swagger UI and the OpenRPC schema as the response type for that error.
