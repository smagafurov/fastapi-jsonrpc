from fastapi_jsonrpc import clone_dependant
from fastapi_jsonrpc import Dependant


def test_clone_dependant():
    original_dependant = Dependant(
        dependencies=[Dependant()],
        name="some name",
        call=lambda c: c,
        request_param_name="ss",
        websocket_param_name="ss",
        response_param_name="aaa",
        background_tasks_param_name="ss",
        security_scopes_param_name="sss",
        security_scopes=["sss", ],
        use_cache=False,
        path="some path",
        body_params=["some path"],
    )

    cloned_dependant = clone_dependant(original_dependant)

    assert type(cloned_dependant) == Dependant

    # all fields from original represented in cloned
    assert list(original_dependant.__dict__.keys()) == list(cloned_dependant.__dict__.keys())

    for key in original_dependant.__dict__.keys():
        if key == "dependencies":  # not checking copied array of classes (cause it's new generated)
            continue

        assert original_dependant.__dict__.get(key) == cloned_dependant.__dict__.get(key)

    original_dependant.name = "not some name"
    assert cloned_dependant.name == "some name"

    original_dependant.body_params.append("some value that should be in copied")
    assert cloned_dependant.body_params == ["some path"]
