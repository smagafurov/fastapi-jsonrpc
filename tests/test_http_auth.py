import contextlib
import contextvars
from json import dumps as json_dumps

import pytest
from fastapi import HTTPException, Depends
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from starlette.status import HTTP_401_UNAUTHORIZED

from fastapi_jsonrpc import JsonRpcContext


security = HTTPBasic()


def auth_user(
    credentials: HTTPBasicCredentials = Depends(security)
) -> HTTPBasicCredentials:
    if (credentials.username, credentials.password) != ('user', 'password'):
        raise HTTPException(
            status_code=HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={'WWW-Authenticate': 'Basic'},
        )
    return credentials


@pytest.fixture
def body():
    return json_dumps({
        'id': 1,
        'jsonrpc': '2.0',
        'method': 'probe',
        'params': {},
    })


@pytest.fixture
def ep_method_auth(ep):
    @ep.method()
    def probe(
        user: HTTPBasicCredentials = Depends(auth_user)
    ) -> str:
        return user.username

    return ep


def test_method_auth(ep_method_auth, raw_request, body):
    resp = raw_request(body, auth=('user', 'password'))
    assert resp.status_code == 200
    assert resp.json() == {'id': 1, 'jsonrpc': '2.0', 'result': 'user'}


def test_method_wrong_auth(ep_method_auth, raw_request, body):
    resp = raw_request(body, auth=('user', 'wrong-password'))
    assert resp.status_code == 401
    assert resp.json() == {'detail': 'Incorrect username or password'}


def test_method_no_auth(ep_method_auth, raw_request, body):
    resp = raw_request(body)
    assert resp.status_code == 401
    assert resp.json() == {'detail': 'Not authenticated'}


@pytest.fixture
def ep_middleware_auth(ep):
    credentials_var = contextvars.ContextVar('credentials')

    @contextlib.asynccontextmanager
    async def ep_middleware(ctx: JsonRpcContext):
        credentials = await security(ctx.http_request)
        credentials = auth_user(credentials)
        credentials_var_token = credentials_var.set(credentials)

        try:
            yield
        finally:
            credentials_var.reset(credentials_var_token)

    ep.middlewares.append(ep_middleware)

    @ep.method()
    def probe() -> str:
        return credentials_var.get().username

    return ep


def test_middleware_auth(ep_middleware_auth, raw_request, body):
    resp = raw_request(body, auth=('user', 'password'))
    assert resp.status_code == 200
    assert resp.json() == {'id': 1, 'jsonrpc': '2.0', 'result': 'user'}


def test_middleware_wrong_auth(ep_middleware_auth, raw_request, body):
    resp = raw_request(body, auth=('user', 'wrong-password'))
    assert resp.status_code == 401
    assert resp.json() == {'detail': 'Incorrect username or password'}


def test_middleware_no_auth(ep_middleware_auth, raw_request, body):
    resp = raw_request(body)
    assert resp.status_code == 401
    assert resp.json() == {'detail': 'Not authenticated'}
