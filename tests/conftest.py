import platform
from json import dumps as json_dumps

import pytest
from starlette.testclient import TestClient
import fastapi_jsonrpc as jsonrpc


# Workaround for osx systems
# https://stackoverflow.com/questions/58597334/unittest-performance-issue-when-using-requests-mock-on-osx
if platform.system() == 'Darwin':
    import socket
    socket.gethostbyname = lambda x: '127.0.0.1'


@pytest.fixture
def ep_path():
    return '/api/v1/jsonrpc'


@pytest.fixture
def ep(ep_path):
    return jsonrpc.Entrypoint(ep_path)


@pytest.fixture
def app(ep):
    app = jsonrpc.API()
    app.bind_entrypoint(ep)
    return app


@pytest.fixture
def app_client(app):
    return TestClient(app)


@pytest.fixture
def raw_request(app_client, ep_path):
    def requester(body):
        resp = app_client.post(
            url=ep_path,
            data=body,
        )
        return resp
    return requester


@pytest.fixture
def json_request(raw_request):
    def requester(data):
        resp = raw_request(json_dumps(data))
        return resp.json()
    return requester


@pytest.fixture
def method_request(json_request):
    def requester(method, params, request_id=0):
        return json_request({
            'id': request_id,
            'jsonrpc': '2.0',
            'method': method,
            'params': params,
        })
    return requester
