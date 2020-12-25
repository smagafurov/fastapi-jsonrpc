from json import dumps as json_dumps

import pytest
from fastapi import HTTPException, Depends
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from starlette.status import HTTP_401_UNAUTHORIZED

from fastapi_jsonrpc import Entrypoint


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
def ep(ep_path):
    ep = Entrypoint(
        ep_path,
        dependencies=[Depends(auth_user)],
    )

    @ep.method()
    def probe() -> str:
        return 'ok'

    return ep


def test_method_auth(ep, raw_request, body):
    resp = raw_request(body, auth=('user', 'password'))
    assert resp.status_code == 200
    assert resp.json() == {'id': 1, 'jsonrpc': '2.0', 'result': 'ok'}


def test_method_wrong_auth(ep, raw_request, body):
    resp = raw_request(body, auth=('user', 'wrong-password'))
    assert resp.status_code == 401
    assert resp.json() == {'detail': 'Incorrect username or password'}


def test_method_no_auth(ep, raw_request, body):
    resp = raw_request(body)
    assert resp.status_code == 401
    assert resp.json() == {'detail': 'Not authenticated'}
