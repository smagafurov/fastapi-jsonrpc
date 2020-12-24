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
    def requester(body, path_postfix=''):
        resp = app_client.post(
            url=ep_path + path_postfix,
            data=body,
        )
        return resp
    return requester


@pytest.fixture
def json_request(raw_request):
    def requester(data, path_postfix=''):
        resp = raw_request(json_dumps(data), path_postfix=path_postfix)
        return resp.json()
    return requester


@pytest.fixture(params=[False, True])
def add_path_postfix(request):
    return request.param


@pytest.fixture
def method_request(json_request, add_path_postfix):
    def requester(method, params, request_id=0):
        if add_path_postfix:
            path_postfix = '/' + method
        else:
            path_postfix = ''
        return json_request({
            'id': request_id,
            'jsonrpc': '2.0',
            'method': method,
            'params': params,
        }, path_postfix=path_postfix)
    return requester
