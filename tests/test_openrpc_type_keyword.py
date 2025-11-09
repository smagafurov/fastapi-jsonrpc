from typing import List

from pydantic import BaseModel


def test_type_keyword_field(ep, app, app_client):
    class Model1(BaseModel):
        x: int

    class Model2(BaseModel):
        y: int

    type Model = Model1 | Model2

    class Input(BaseModel):
        data: Model

    class Output(BaseModel):
        result: List[int]

    @ep.method()
    def my_method_type_keyword(inp: Input) -> Output:
        if isinstance(inp.data, Model1):
            return Output(result=[inp.data.x])
        return Output(result=[inp.data.y])

    app.bind_entrypoint(ep)

    resp = app_client.get('/openrpc.json')
    schema = resp.json()

    assert len(schema['methods']) == 1
    assert schema['methods'][0]['params'] == [
        {
            'name': 'inp',
            'schema': {'$ref': '#/components/schemas/Input'},
            'required': True,
        }
    ]
    assert schema['methods'][0]['result'] == {
        'name': 'my_method_type_keyword_Result',
        'schema': {'$ref': '#/components/schemas/Output'},
    }

    assert schema['components']['schemas'] == {
        'Input': {
            'properties': {'data': {'$ref': '#/components/schemas/Model'}},
            'required': ['data'],
            'title': 'Input',
            'type': 'object',
        },
        'Model': {
            'anyOf': [
                {'$ref': '#/components/schemas/Model1'},
                {'$ref': '#/components/schemas/Model2'},
            ]
        },
        'Model1': {
            'properties': {'x': {'title': 'X', 'type': 'integer'}},
            'required': ['x'],
            'title': 'Model1',
            'type': 'object',
        },
        'Model2': {
            'properties': {'y': {'title': 'Y', 'type': 'integer'}},
            'required': ['y'],
            'title': 'Model2',
            'type': 'object',
        },
        'Output': {
            'properties': {
                'result': {
                    'items': {'type': 'integer'},
                    'title': 'Result',
                    'type': 'array',
                }
            },
            'required': ['result'],
            'title': 'Output',
            'type': 'object',
        },
    }
