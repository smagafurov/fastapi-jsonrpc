from typing import Dict, List, Optional

import pytest
from starlette.testclient import TestClient

import fastapi_jsonrpc as jsonrpc
from fastapi import Body
from pydantic import BaseModel, Field, Extra


def test_basic(ep, app, app_client):
    @ep.method()
    def probe(
        data: List[str] = Body(..., examples=['111', '222']),
        amount: int = Body(..., gt=5, examples=[10]),
    ) -> List[int]:
        del data, amount
        return [1, 2, 3]

    app.bind_entrypoint(ep)

    resp = app_client.get('/openrpc.json')

    assert resp.json()['methods'] == [
        {
            'name': 'probe',
            'params': [
                {
                    'name': 'data',
                    'schema': {
                        'title': 'Data',
                        'examples': [
                            '111',
                            '222'
                        ],
                        'type': 'array',
                        'items': {
                            'type': 'string'
                        }
                    },
                    'required': True
                },
                {
                    'name': 'amount',
                    'schema': {
                        'title': 'Amount',
                        'exclusiveMinimum': 5,
                        'examples': [10],
                        'type': 'integer'
                    },
                    'required': True
                }
            ],
            'result': {
                'name': 'probe_Result',
                'schema': {
                    'title': 'Result',
                    'type': 'array',
                    'items': {
                        'type': 'integer'
                    }
                }
            },
            'tags': [],
            'errors': []
        }
    ]


def test_info_block(app, app_client):
    app.title = 'Test App'
    app.version = '1.2.3'
    app.servers = [{'test': 'https://test.dev'}]

    resp = app_client.get('/openrpc.json')

    assert resp.json() == {
        'openrpc': '1.2.6',
        'info': {
            'version': app.version,
            'title': app.title,
        },
        'servers': app.servers,
        'methods': [],
        'components': {
            'schemas': {},
            'errors': {},
        }
    }


def test_component_schemas(ep, app, app_client):
    class Input(BaseModel):
        x: int = Field(
            ...,
            title='x',
            description='X field',
            gt=1,
            lt=10,
            multiple_of=3,
        )
        y: Optional[str] = Field(
            None,
            alias='Y',
            min_length=1,
            max_length=5,
            pattern=r'^[a-z]{4}$',
        )
        class Config:
            extra = Extra.forbid


    class Output(BaseModel):
        result: List[int] = Field(
            ...,
            min_items=1,
            max_items=10,
        )

    @ep.method()
    def my_method(inp: Input) -> Output:
        return Output(result=[inp.x])

    app.bind_entrypoint(ep)

    resp = app_client.get('/openrpc.json')
    schema = resp.json()

    assert len(schema['methods']) == 1
    assert schema['methods'][0]['params'] == [
        {
            'name': 'inp',
            'schema': {
                '$ref': '#/components/schemas/Input'
            },
            'required': True
        }
    ]
    assert schema['methods'][0]['result'] == {
        'name': 'my_method_Result',
        'schema': {
            '$ref': '#/components/schemas/Output'
        }
    }

    assert schema['components']['schemas'] == {
        'Input': {
            'title': 'Input',
            'type': 'object',
            'properties': {
                'x': {
                    'title': 'x',
                    'description': 'X field',
                    'exclusiveMinimum': 1,
                    'exclusiveMaximum': 10,
                    'multipleOf': 3,
                    'type': 'integer'
                },
                'Y': {
                    'anyOf': [
                        {
                            'maxLength': 5,
                            'minLength': 1,
                            'pattern': '^[a-z]{4}$',
                            'type': 'string'
                        },
                        {'type': 'null'}
                    ],
                    'default': None,
                    'title': 'Y'
                }
            },
            'required': ['x'],
            'additionalProperties': False
        },
        'Output': {
            'title': 'Output',
            'type': 'object',
            'properties': {
                'result': {
                    'title': 'Result',
                    'minItems': 1,
                    'maxItems': 10,
                    'type': 'array',
                    'items': {
                        'type': 'integer'
                    }
                }
            },
            'required': ['result']
        }
    }


def test_tags(ep, app, app_client):
    @ep.method(tags=['tag1', 'tag2'])
    def my_method__with_tags() -> None:
        return None

    app.bind_entrypoint(ep)

    resp = app_client.get('/openrpc.json')
    schema = resp.json()

    assert len(schema['methods']) == 1
    assert schema['methods'][0]['tags'] == [
        {'name': 'tag1'},
        {'name': 'tag2'},
    ]


def test_errors(ep, app, app_client):
    class MyError(jsonrpc.BaseError):
        CODE = 5000
        MESSAGE = 'My error'

        class DataModel(BaseModel):
            details: str

    @ep.method(errors=[MyError])
    def my_method__with_errors() -> None:
        return None

    app.bind_entrypoint(ep)

    resp = app_client.get('/openrpc.json')
    schema = resp.json()

    assert len(schema['methods']) == 1
    assert schema['methods'][0]['errors'] == [
        {'$ref': '#/components/errors/5000'},
    ]
    assert schema['components']['errors']['5000'] == {
        'code': 5000,
        'message': 'My error',
        'data': {
            'title': 'MyError.Data',
            'type': 'object',
            'properties': {
                'details': {
                    'title': 'Details',
                    'type': 'string'
                }
            },
            'required': ['details']
        }
    }


def test_errors_merging(ep, app, app_client):
    class FirstError(jsonrpc.BaseError):
        CODE = 5000
        MESSAGE = 'My error'

        class DataModel(BaseModel):
            x: str

    class SecondError(jsonrpc.BaseError):
        CODE = 5000
        MESSAGE = 'My error'

        class DataModel(BaseModel):
            y: int

    @ep.method(errors=[FirstError, SecondError])
    def my_method__with_mergeable_errors() -> None:
        return None

    app.bind_entrypoint(ep)

    resp = app_client.get('/openrpc.json')
    schema = resp.json()

    assert len(schema['methods']) == 1
    assert schema['methods'][0]['errors'] == [{'$ref': '#/components/errors/5000'}]
    assert schema['components']['errors']['5000'] == {
        'code': 5000,
        'message': 'My error',
        'data': {
            'title': 'ERROR_5000',
            'anyOf': [
                {'$ref': '#/components/schemas/FirstError.Data'},
                {'$ref': '#/components/schemas/SecondError.Data'},
            ],
        }
    }
    assert schema['components']['schemas']['FirstError.Data'] == {
        'title': 'FirstError.Data',
        'type': 'object',
        'properties': {
            'x': {'type': 'string', 'title': 'X'},
        },
        'required': ['x']
    }
    assert schema['components']['schemas']['SecondError.Data'] == {
        'title': 'SecondError.Data',
        'type': 'object',
        'properties': {
            'y': {'type': 'integer', 'title': 'Y'},
        },
        'required': ['y']
    }


def test_type_hints(ep, app, app_client):
    Input = List[str]
    Output = Dict[str, List[List[float]]]

    @ep.method()
    def my_method__with_typehints(arg: Input) -> Output:
        return {}

    app.bind_entrypoint(ep)

    resp = app_client.get('/openrpc.json')
    schema = resp.json()

    assert len(schema['methods']) == 1
    assert schema['methods'][0]['params' ] == [
        {
            'name': 'arg',
            'schema': {
                'title': 'Arg',
                'type': 'array',
                'items': {
                    'type': 'string'
                }
            },
            'required': True
        }
    ]
    assert schema['methods'][0]['result'] == {
        'name': 'my_method__with_typehints_Result',
        'schema': {
            'title': 'Result',
            'type': 'object',
            'additionalProperties': {
                'type': 'array',
                'items': {
                    'type': 'array',
                    'items': {
                        'type': 'number'
                    }
                }
            }
        }
    }


@pytest.mark.parametrize('fastapi_jsonrpc_components_fine_names', [True, False])
def test_no_entrypoints__ok(fastapi_jsonrpc_components_fine_names):
    app = jsonrpc.API(fastapi_jsonrpc_components_fine_names=fastapi_jsonrpc_components_fine_names)
    app_client = TestClient(app)
    resp = app_client.get('/openrpc.json')
    resp.raise_for_status()
    assert resp.status_code == 200