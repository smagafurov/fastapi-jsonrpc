"""`python -c`, exec() and notebook cells run in code that has no module of its own."""

from fastapi import Body, Depends

import fastapi_jsonrpc as jsonrpc

SOURCE = 'ep = jsonrpc.Entrypoint(ep_path, common_dependencies=[Depends(get_common_dep)])'


def get_common_dep(common_dep: int = Body(...)) -> int:
    return common_dep


def _exec_in(namespace, ep_path):
    namespace.update(jsonrpc=jsonrpc, Depends=Depends, get_common_dep=get_common_dep, ep_path=ep_path)
    exec(compile(SOURCE, '<string>', 'exec'), namespace)
    return namespace['ep']


def test_callee_module_taken_from_frame_globals(ep_path):
    ep = _exec_in({'__name__': 'callee_module_probe'}, ep_path)

    assert ep.callee_module == 'callee_module_probe'


def test_no_module_name_at_all(ep_path):
    ep = _exec_in({}, ep_path)

    assert ep.callee_module is None


def test_entrypoint_from_exec_serves_requests(ep_path):
    from starlette.testclient import TestClient

    ep = _exec_in({'__name__': 'callee_module_probe_app'}, ep_path)

    @ep.method()
    def probe(value: int = Body(...)) -> int:
        return value

    app = jsonrpc.API()
    app.bind_entrypoint(ep)

    with TestClient(app) as client:
        resp = client.post(
            ep_path,
            json={'id': 1, 'jsonrpc': '2.0', 'method': 'probe', 'params': {'value': 5, 'common_dep': 7}},
        )

    assert resp.json() == {'id': 1, 'jsonrpc': '2.0', 'result': 5}
