import pytest
from fastapi import Depends
from starlette.testclient import TestClient

import fastapi_jsonrpc as jsonrpc


def get_method_dep() -> str:
    return 'method-real'


def get_common_dep() -> str:
    return 'common-real'


def get_shared_dep() -> str:
    return 'shared-real'


@pytest.fixture
def ep(ep_path):
    ep = jsonrpc.Entrypoint(
        ep_path,
        dependencies=[Depends(get_shared_dep)],
        common_dependencies=[Depends(get_common_dep)],
    )

    @ep.method()
    def probe(
        method_dep: str = Depends(get_method_dep),
        common_dep: str = Depends(get_common_dep),
        shared_dep: str = Depends(get_shared_dep),
    ) -> list:
        return [method_dep, common_dep, shared_dep]

    return ep


def _probe(json_request):
    return json_request({'id': 1, 'jsonrpc': '2.0', 'method': 'probe', 'params': {}})


def test_without_overrides(json_request):
    assert _probe(json_request) == {
        'id': 1, 'jsonrpc': '2.0',
        'result': ['method-real', 'common-real', 'shared-real'],
    }


def test_method_dependency_overridden(app, json_request):
    app.dependency_overrides[get_method_dep] = lambda: 'method-fake'
    assert _probe(json_request)['result'] == ['method-fake', 'common-real', 'shared-real']


def test_common_dependency_overridden(app, json_request):
    app.dependency_overrides[get_common_dep] = lambda: 'common-fake'
    assert _probe(json_request)['result'] == ['method-real', 'common-fake', 'shared-real']


def test_shared_dependency_overridden(app, json_request):
    app.dependency_overrides[get_shared_dep] = lambda: 'shared-fake'
    assert _probe(json_request)['result'] == ['method-real', 'common-real', 'shared-fake']


def test_method_added_after_bind_entrypoint_overridden(ep_path):
    app = jsonrpc.API()
    late_ep = jsonrpc.Entrypoint(ep_path)
    app.bind_entrypoint(late_ep)

    @late_ep.method()
    def late(method_dep: str = Depends(get_method_dep)) -> str:
        return method_dep

    app.dependency_overrides[get_method_dep] = lambda: 'method-fake'

    with TestClient(app) as client:
        resp = client.post(ep_path, json={'id': 1, 'jsonrpc': '2.0', 'method': 'late', 'params': {}})

    assert resp.json() == {'id': 1, 'jsonrpc': '2.0', 'result': 'method-fake'}
