import pytest

from fastapi_jsonrpc import API, Entrypoint


@pytest.fixture
def ep1(ep_path):
    ep = Entrypoint(ep_path)

    @ep.method()
    def probe1() -> str:
        return "probe1"

    return ep


@pytest.fixture
def ep2(ep_path):
    ep = Entrypoint(ep_path)

    @ep.method()
    def probe2() -> str:
        return "probe2"

    return ep


@pytest.fixture
def ep_path_v2():
    return '/api/v2/jsonrpc'


@pytest.fixture
def ep3(ep_path_v2):
    ep = Entrypoint(ep_path_v2)

    @ep.method()
    def probe() -> str:
        return "probe3"

    return ep


@pytest.fixture
def app(ep1, ep2, ep3):
    app = API()
    app.bind_entrypoint(ep1)
    app.bind_entrypoint(ep2, add_to_existing_path=True)
    app.bind_entrypoint(ep3)
    return app


def test_basic(json_request):
    resp = json_request({
        'id': 0,
        'jsonrpc': '2.0',
        'method': 'probe1',
        'params': {},
    })
    assert resp == {'id': 0, 'jsonrpc': '2.0', 'result': 'probe1'}


def test_method_from_second_ep(json_request):
    resp = json_request({
        'id': 0,
        'jsonrpc': '2.0',
        'method': 'probe2',
        'params': {},
    })
    assert resp == {'id': 0, 'jsonrpc': '2.0', 'result': 'probe2'}


def test_method_from_wrong_path_ep(json_request):
    resp = json_request({
        'id': 0,
        'jsonrpc': '2.0',
        'method': 'probe3',
        'params': {},
    })
    assert resp == {'id': 0, 'jsonrpc': '2.0', 'error': {'code': -32601, 'message': 'Method not found'}}