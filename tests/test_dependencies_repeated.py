from typing import Tuple

import pytest
from fastapi import Body, Depends, Header

import fastapi_jsonrpc as jsonrpc


def get_auth_token(
    auth_token: str = Header(..., alias='auth-token'),
) -> str:
    return auth_token


def get_value(
    value: int = Body(...),
) -> int:
    return value


def left(
    auth_token: str = Depends(get_auth_token),
    value: int = Depends(get_value),
) -> str:
    return f'left-{auth_token}-{value}'


def right(
    auth_token: str = Depends(get_auth_token),
    value: int = Depends(get_value),
) -> str:
    return f'right-{auth_token}-{value}'


@pytest.fixture
def ep(ep_path):
    # `left` is reachable twice: as a common dependency and from the method itself,
    # and both branches lead to the same `get_auth_token` / `get_value`
    ep = jsonrpc.Entrypoint(ep_path, common_dependencies=[Depends(left)])

    @ep.method()
    def probe(
        left_result: str = Depends(left),
        right_result: str = Depends(right),
    ) -> Tuple[str, str]:
        return left_result, right_result

    return ep


def test_params_gathered_once(app_client, ep_path):
    schema = app_client.get('/openapi.json').json()

    assert schema['components']['schemas']['_Params[probe]']['properties'] == {
        'value': {'title': 'Value', 'type': 'integer'},
    }
    assert schema['components']['schemas']['_Params[probe]']['required'] == ['value']
    assert schema['paths'][f'{ep_path}/probe']['post']['parameters'] == [{
        'in': 'header',
        'name': 'auth-token',
        'required': True,
        'schema': {'title': 'Auth-Token', 'type': 'string'},
    }]


def test_solved_once_per_request(json_request):
    resp = json_request(
        {'id': 1, 'jsonrpc': '2.0', 'method': 'probe', 'params': {'value': 7}},
        headers={'auth-token': 'secret'},
    )
    assert resp == {
        'id': 1,
        'jsonrpc': '2.0',
        'result': ['left-secret-7', 'right-secret-7'],
    }
