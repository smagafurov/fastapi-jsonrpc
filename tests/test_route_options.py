"""Route options the JSON-RPC envelope owns must be refused by name."""

import pytest
from fastapi import Body

import fastapi_jsonrpc as jsonrpc


@pytest.mark.parametrize(
    ('kwarg', 'value'),
    [('methods', ['GET']), ('response_model', int)],
)
def test_entrypoint_rejects_protocol_owned_option(ep_path, kwarg, value):
    with pytest.raises(TypeError, match=f"JSON-RPC route fixes '{kwarg}'"):
        jsonrpc.Entrypoint(ep_path, **{kwarg: value})


@pytest.mark.parametrize(
    ('kwarg', 'value'),
    [('methods', ['GET']), ('response_model', int)],
)
def test_method_rejects_protocol_owned_option(ep, kwarg, value):
    with pytest.raises(TypeError, match=f"JSON-RPC route fixes '{kwarg}'"):
        @ep.method(**{kwarg: value})
        def probe(value_: int = Body(..., alias='value')) -> int:
            return value_


def test_route_metadata_still_accepted(ep, app_client, ep_path):
    """Options fastapi owns keep working: this is the interface we mirror."""
    schema = app_client.get('/openapi.json').json()
    operation = schema['paths'][f'{ep_path}/probe']['post']

    assert operation['tags'] == ['probes']
    assert operation['summary'] == 'Probe summary'


@pytest.fixture
def ep(ep_path):
    ep = jsonrpc.Entrypoint(ep_path)

    @ep.method(tags=['probes'], summary='Probe summary')
    def probe(value: int = Body(...)) -> int:
        return value

    return ep
