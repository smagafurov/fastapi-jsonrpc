import pytest
from fastapi import Depends
from fastapi.security import HTTPBasic, HTTPBasicCredentials

import fastapi_jsonrpc as jsonrpc


security = HTTPBasic()


def get_user(credentials: HTTPBasicCredentials = Depends(security)) -> str:
    return credentials.username


class TestMethodLevelSecurity:
    """Security dependency defined on method level."""

    @pytest.fixture
    def ep(self, ep_path):
        ep = jsonrpc.Entrypoint(ep_path)

        @ep.method()
        def probe(user: str = Depends(get_user)) -> str:
            return user

        return ep

    def test_security_schemes_defined(self, app_client):
        schema = app_client.get('/openapi.json').json()

        assert schema['components']['securitySchemes'] == {
            'HTTPBasic': {
                'type': 'http',
                'scheme': 'basic',
            }
        }

    def test_entrypoint_has_no_security(self, app_client):
        schema = app_client.get('/openapi.json').json()

        entrypoint = schema['paths']['/api/v1/jsonrpc']['post']
        assert 'security' not in entrypoint

    def test_method_has_security(self, app_client):
        schema = app_client.get('/openapi.json').json()

        method = schema['paths']['/api/v1/jsonrpc/probe']['post']
        assert method['security'] == [{'HTTPBasic': []}]


class TestEntrypointLevelSecurity:
    """Security dependency defined on entrypoint level (shared deps)."""

    @pytest.fixture
    def ep(self, ep_path):
        ep = jsonrpc.Entrypoint(
            ep_path,
            dependencies=[Depends(get_user)],
        )

        @ep.method()
        def probe() -> str:
            return 'ok'

        return ep

    def test_security_schemes_defined(self, app_client):
        schema = app_client.get('/openapi.json').json()

        assert schema['components']['securitySchemes'] == {
            'HTTPBasic': {
                'type': 'http',
                'scheme': 'basic',
            }
        }

    def test_entrypoint_has_security(self, app_client):
        schema = app_client.get('/openapi.json').json()

        entrypoint = schema['paths']['/api/v1/jsonrpc']['post']
        assert entrypoint['security'] == [{'HTTPBasic': []}]

    def test_method_has_no_security(self, app_client):
        """Method inherits security from entrypoint, not duplicated in schema."""
        schema = app_client.get('/openapi.json').json()

        method = schema['paths']['/api/v1/jsonrpc/probe']['post']
        assert 'security' not in method
