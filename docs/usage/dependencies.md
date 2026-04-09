# Dependencies

Every FastAPI dependency works inside a JSON-RPC method. The `Entrypoint` additionally distinguishes two scopes for batch requests:

- **`dependencies`** — shared across the whole batch. Good for batch-level auth, DB sessions, correlation IDs.
- **`common_dependencies`** — resolved for every request inside a batch. Good for per-call authorisation, resource lookups.

For the exact semantics, see `tests/test_dependencies.py` and `tests/test_http_auth_shared_deps.py`.

```python
import fastapi_jsonrpc as jsonrpc
from fastapi import Body, Header, Depends
from pydantic import BaseModel


class User(BaseModel):
    name: str


class AuthError(jsonrpc.BaseError):
    CODE = 7000
    MESSAGE = 'Auth error'


class AccountNotFound(jsonrpc.BaseError):
    CODE = 6000
    MESSAGE = 'Account not found'


def get_auth_user(
    auth_token: str = Header(None, alias='user-auth-token'),
) -> User:
    if not auth_token:
        raise AuthError
    return User(name=f'user-{auth_token}')


def get_account(
    account_id: str = Body(..., examples=['1.1']),
    user: User = Depends(get_auth_user),
) -> dict:
    if not account_id.startswith(user.name[-1]):
        raise AccountNotFound
    return {'id': account_id, 'owner': user.name}


api_v1 = jsonrpc.Entrypoint(
    '/api/v1/jsonrpc',
    errors=[AuthError, AccountNotFound, *jsonrpc.Entrypoint.default_errors],
    # Resolved once per batch:
    dependencies=[Depends(get_auth_user)],
    # Resolved for every request inside a batch:
    common_dependencies=[Depends(get_account)],
)


@api_v1.method()
def get_balance(account: dict = Depends(get_account)) -> int:
    return 100
```

A few things to notice:

- Parameters declared inside `get_auth_user` become **header** parameters of every method that depends on it, and they are documented as such in Swagger UI.
- Parameters declared inside `get_account` become **JSON-RPC** parameters of every method that depends on it.
- Because `get_account` depends on `get_auth_user`, calling any dependent method also requires the `user-auth-token` header.
- The split between `dependencies` and `common_dependencies` gives you control over how many times each dependency runs in a batch.

## Yield dependencies

Yield-based dependencies work the same way as in FastAPI, including teardown:

```python
async def db_session():
    async with make_session() as session:
        yield session
```

Exceptions raised inside the `yield` block are propagated to the dependency so you can roll transactions back.

## Background tasks

```python
from fastapi import BackgroundTasks


@api_v1.method()
def send_invite(
    email: str = Body(...),
    background_tasks: BackgroundTasks = None,
) -> None:
    background_tasks.add_task(deliver_invite, email)
```

Background tasks are executed after the JSON-RPC response has been sent.
