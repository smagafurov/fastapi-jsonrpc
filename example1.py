import fastapi_jsonrpc as jsonrpc
from pydantic import BaseModel
from fastapi import Body


app = jsonrpc.API()

api_v1 = jsonrpc.Entrypoint('/api/v1/jsonrpc')


class MyError(jsonrpc.BaseError):
    CODE = 5000
    MESSAGE = 'My error'

    class DataModel(BaseModel):
        details: str


@api_v1.method(errors=[MyError])
def echo(
    data: str = Body(..., examples=['123']),
) -> str:
    if data == 'error':
        raise MyError(data={'details': 'error'})
    else:
        return data


app.bind_entrypoint(api_v1)


if __name__ == '__main__':
    import uvicorn
    uvicorn.run('example1:app', port=5000, debug=True, access_log=False)
