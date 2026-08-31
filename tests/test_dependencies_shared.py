import pytest
from fastapi import Body, Depends, Header, Query

import fastapi_jsonrpc as jsonrpc


def test_body_param_rejected(ep_path):
    def shared_dep(value: int = Body(...)) -> int:
        return value

    with pytest.raises(RuntimeError, match="shared dependencies can't use 'Body' parameters"):
        jsonrpc.Entrypoint(ep_path, dependencies=[Depends(shared_dep)])


def test_query_param_rejected(ep_path):
    def shared_dep(value: int = Query(...)) -> int:
        return value

    with pytest.raises(RuntimeError, match="shared dependencies can't use 'Query' parameters"):
        jsonrpc.Entrypoint(ep_path, dependencies=[Depends(shared_dep)])


def test_body_param_in_sub_dependency_rejected(ep_path):
    def inner(value: int = Body(...)) -> int:
        return value

    def shared_dep(value: int = Depends(inner)) -> int:
        return value

    with pytest.raises(RuntimeError, match="shared dependencies can't use 'Body' parameters"):
        jsonrpc.Entrypoint(ep_path, dependencies=[Depends(shared_dep)])


def test_header_param_allowed(ep_path):
    def shared_dep(auth_token: str = Header(..., alias='auth-token')) -> str:
        return auth_token

    ep = jsonrpc.Entrypoint(ep_path, dependencies=[Depends(shared_dep)])
    assert ep.entrypoint_route.path == ep_path
