"""Tests for APIResponse generic schema."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest
from pydantic import BaseModel

from app.interfaces.schemas.base import APIResponse


@pytest.mark.unit
class TestAPIResponseDefaults:
    def test_default_construction(self) -> None:
        resp: APIResponse[Any] = APIResponse()
        assert resp.code == 0
        assert resp.msg == "success"
        assert resp.data is None

    def test_default_code_is_zero(self) -> None:
        resp: APIResponse[Any] = APIResponse()
        assert resp.code == 0

    def test_default_msg_is_success(self) -> None:
        resp: APIResponse[Any] = APIResponse()
        assert resp.msg == "success"

    def test_default_data_is_none(self) -> None:
        resp: APIResponse[Any] = APIResponse()
        assert resp.data is None


@pytest.mark.unit
class TestAPIResponseSuccessFactory:
    def test_success_no_args(self) -> None:
        resp = APIResponse.success()
        assert resp.code == 0
        assert resp.msg == "success"
        assert resp.data is None

    def test_success_with_dict_data(self) -> None:
        payload = {"key": "value", "count": 42}
        resp = APIResponse.success(data=payload)
        assert resp.code == 0
        assert resp.msg == "success"
        assert resp.data == payload

    def test_success_with_string_data(self) -> None:
        resp = APIResponse.success(data="hello world")
        assert resp.code == 0
        assert resp.data == "hello world"

    def test_success_with_int_data(self) -> None:
        resp = APIResponse.success(data=99)
        assert resp.data == 99

    def test_success_with_list_data(self) -> None:
        items = [1, 2, 3]
        resp = APIResponse.success(data=items)
        assert resp.data == [1, 2, 3]

    def test_success_with_custom_msg(self) -> None:
        resp = APIResponse.success(data=None, msg="Operation completed")
        assert resp.code == 0
        assert resp.msg == "Operation completed"
        assert resp.data is None

    def test_success_with_data_and_custom_msg(self) -> None:
        resp = APIResponse.success(data={"id": 1}, msg="Created")
        assert resp.code == 0
        assert resp.msg == "Created"
        assert resp.data == {"id": 1}

    def test_success_with_none_data_explicit(self) -> None:
        resp = APIResponse.success(data=None)
        assert resp.code == 0
        assert resp.data is None

    def test_success_with_false_data(self) -> None:
        resp = APIResponse.success(data=False)
        assert resp.data is False

    def test_success_with_zero_data(self) -> None:
        resp = APIResponse.success(data=0)
        assert resp.data == 0

    def test_success_with_empty_list_data(self) -> None:
        resp = APIResponse.success(data=[])
        assert resp.data == []

    def test_success_with_pydantic_model_data(self) -> None:
        class Inner(BaseModel):
            name: str
            value: int

        inner = Inner(name="test", value=7)
        resp = APIResponse.success(data=inner)
        assert resp.code == 0
        assert resp.data is inner


@pytest.mark.unit
class TestAPIResponseErrorFactory:
    def test_error_basic(self) -> None:
        resp = APIResponse.error(code=400, msg="Bad Request")
        assert resp.code == 400
        assert resp.msg == "Bad Request"
        assert resp.data is None

    def test_error_data_is_always_none(self) -> None:
        resp = APIResponse.error(code=500, msg="Internal Server Error")
        assert resp.data is None

    def test_error_404(self) -> None:
        resp = APIResponse.error(code=404, msg="Not Found")
        assert resp.code == 404
        assert resp.msg == "Not Found"

    def test_error_401(self) -> None:
        resp = APIResponse.error(code=401, msg="Unauthorized")
        assert resp.code == 401
        assert resp.msg == "Unauthorized"

    def test_error_422(self) -> None:
        resp = APIResponse.error(code=422, msg="Validation error in field X")
        assert resp.code == 422
        assert resp.msg == "Validation error in field X"

    def test_error_negative_code(self) -> None:
        resp = APIResponse.error(code=-1, msg="Unknown failure")
        assert resp.code == -1

    def test_error_custom_code_1001(self) -> None:
        resp = APIResponse.error(code=1001, msg="Rate limit exceeded")
        assert resp.code == 1001
        assert resp.msg == "Rate limit exceeded"

    def test_error_empty_msg(self) -> None:
        resp = APIResponse.error(code=500, msg="")
        assert resp.code == 500
        assert resp.msg == ""


@pytest.mark.unit
class TestAPIResponseDirectConstruction:
    def test_explicit_code_and_msg(self) -> None:
        resp: APIResponse[str] = APIResponse(code=200, msg="OK", data="payload")
        assert resp.code == 200
        assert resp.msg == "OK"
        assert resp.data == "payload"

    def test_zero_code_with_data(self) -> None:
        resp: APIResponse[list[int]] = APIResponse(code=0, msg="success", data=[1, 2, 3])
        assert resp.data == [1, 2, 3]

    def test_none_data_explicit(self) -> None:
        resp: APIResponse[None] = APIResponse(code=0, msg="success", data=None)
        assert resp.data is None

    def test_non_zero_code_with_none_data(self) -> None:
        resp: APIResponse[None] = APIResponse(code=403, msg="Forbidden", data=None)
        assert resp.code == 403
        assert resp.data is None


@pytest.mark.unit
class TestAPIResponseSerialization:
    def test_model_dump_defaults(self) -> None:
        resp: APIResponse[Any] = APIResponse()
        data = resp.model_dump()
        assert data["code"] == 0
        assert data["msg"] == "success"
        assert data["data"] is None

    def test_model_dump_with_data(self) -> None:
        resp = APIResponse.success(data={"items": [1, 2]}, msg="Listed")
        data = resp.model_dump()
        assert data["code"] == 0
        assert data["msg"] == "Listed"
        assert data["data"] == {"items": [1, 2]}

    def test_model_dump_error(self) -> None:
        resp = APIResponse.error(code=404, msg="Not Found")
        data = resp.model_dump()
        assert data["code"] == 404
        assert data["msg"] == "Not Found"
        assert data["data"] is None

    def test_json_roundtrip_success(self) -> None:
        resp = APIResponse.success(data={"id": 42, "name": "test"}, msg="OK")
        json_str = resp.model_dump_json()
        resp2: APIResponse[Any] = APIResponse.model_validate_json(json_str)
        assert resp2.code == 0
        assert resp2.msg == "OK"
        assert resp2.data == {"id": 42, "name": "test"}

    def test_json_roundtrip_error(self) -> None:
        resp = APIResponse.error(code=500, msg="Server error")
        json_str = resp.model_dump_json()
        resp2: APIResponse[Any] = APIResponse.model_validate_json(json_str)
        assert resp2.code == 500
        assert resp2.msg == "Server error"
        assert resp2.data is None

    def test_model_validate_from_dict(self) -> None:
        raw = {"code": 0, "msg": "success", "data": [1, 2, 3]}
        resp: APIResponse[Any] = APIResponse.model_validate(raw)
        assert resp.code == 0
        assert resp.data == [1, 2, 3]

    def test_model_validate_error_dict(self) -> None:
        raw = {"code": 400, "msg": "Bad Request", "data": None}
        resp: APIResponse[Any] = APIResponse.model_validate(raw)
        assert resp.code == 400
        assert resp.msg == "Bad Request"
        assert resp.data is None

    def test_model_dump_keys_present(self) -> None:
        resp: APIResponse[Any] = APIResponse()
        keys = set(resp.model_dump().keys())
        assert keys == {"code", "msg", "data"}


@pytest.mark.unit
class TestAPIResponseSuccessVsError:
    def test_success_code_zero_error_nonzero(self) -> None:
        ok = APIResponse.success(data="result")
        err = APIResponse.error(code=500, msg="fail")
        assert ok.code == 0
        assert err.code != 0

    def test_success_has_data_error_has_none(self) -> None:
        ok = APIResponse.success(data={"x": 1})
        err = APIResponse.error(code=400, msg="bad")
        assert ok.data is not None
        assert err.data is None

    def test_instances_are_independent(self) -> None:
        r1 = APIResponse.success(data={"a": 1})
        r2 = APIResponse.success(data={"b": 2})
        assert r1.data != r2.data
