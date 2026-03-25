"""Tests for domain type guard utilities."""

import pytest

from app.domain.utils.type_guards import (
    ensure_dict,
    ensure_float,
    ensure_int,
    ensure_list,
    ensure_str,
    get_dict_value,
    get_nested_value,
    is_dict,
    is_dict_with_key,
    is_dict_with_keys,
    is_float,
    is_int,
    is_list,
    is_list_of_dicts,
    is_list_of_strings,
    is_non_empty_string,
    is_numeric,
    is_str,
    is_tool_result_dict,
)


@pytest.mark.unit
class TestIsDict:
    def test_dict_true(self) -> None:
        assert is_dict({"a": 1}) is True

    def test_list_false(self) -> None:
        assert is_dict([1, 2]) is False

    def test_none_false(self) -> None:
        assert is_dict(None) is False

    def test_empty_dict_true(self) -> None:
        assert is_dict({}) is True


@pytest.mark.unit
class TestIsList:
    def test_list_true(self) -> None:
        assert is_list([1, 2]) is True

    def test_dict_false(self) -> None:
        assert is_list({"a": 1}) is False

    def test_tuple_false(self) -> None:
        assert is_list((1, 2)) is False

    def test_empty_list_true(self) -> None:
        assert is_list([]) is True


@pytest.mark.unit
class TestIsStr:
    def test_str_true(self) -> None:
        assert is_str("hello") is True

    def test_int_false(self) -> None:
        assert is_str(42) is False

    def test_empty_str_true(self) -> None:
        assert is_str("") is True


@pytest.mark.unit
class TestIsInt:
    def test_int_true(self) -> None:
        assert is_int(42) is True

    def test_bool_false(self) -> None:
        assert is_int(True) is False

    def test_float_false(self) -> None:
        assert is_int(3.14) is False

    def test_zero_true(self) -> None:
        assert is_int(0) is True

    def test_negative_true(self) -> None:
        assert is_int(-5) is True


@pytest.mark.unit
class TestIsFloat:
    def test_float_true(self) -> None:
        assert is_float(3.14) is True

    def test_int_false(self) -> None:
        assert is_float(42) is False

    def test_zero_float_true(self) -> None:
        assert is_float(0.0) is True


@pytest.mark.unit
class TestIsNumeric:
    def test_int_true(self) -> None:
        assert is_numeric(42) is True

    def test_float_true(self) -> None:
        assert is_numeric(3.14) is True

    def test_bool_false(self) -> None:
        assert is_numeric(True) is False

    def test_str_false(self) -> None:
        assert is_numeric("42") is False


@pytest.mark.unit
class TestIsDictWithKey:
    def test_has_key(self) -> None:
        assert is_dict_with_key({"name": "test"}, "name") is True

    def test_missing_key(self) -> None:
        assert is_dict_with_key({"other": 1}, "name") is False

    def test_not_dict(self) -> None:
        assert is_dict_with_key([1, 2], "name") is False


@pytest.mark.unit
class TestIsDictWithKeys:
    def test_all_keys_present(self) -> None:
        assert is_dict_with_keys({"a": 1, "b": 2, "c": 3}, ["a", "b"]) is True

    def test_missing_key(self) -> None:
        assert is_dict_with_keys({"a": 1}, ["a", "b"]) is False

    def test_empty_keys(self) -> None:
        assert is_dict_with_keys({"a": 1}, []) is True


@pytest.mark.unit
class TestIsListOfDicts:
    def test_valid(self) -> None:
        assert is_list_of_dicts([{"a": 1}, {"b": 2}]) is True

    def test_mixed(self) -> None:
        assert is_list_of_dicts([{"a": 1}, "not_dict"]) is False

    def test_empty(self) -> None:
        assert is_list_of_dicts([]) is True


@pytest.mark.unit
class TestIsListOfStrings:
    def test_valid(self) -> None:
        assert is_list_of_strings(["a", "b"]) is True

    def test_mixed(self) -> None:
        assert is_list_of_strings(["a", 1]) is False

    def test_empty(self) -> None:
        assert is_list_of_strings([]) is True


@pytest.mark.unit
class TestIsNonEmptyString:
    def test_non_empty(self) -> None:
        assert is_non_empty_string("hello") is True

    def test_empty(self) -> None:
        assert is_non_empty_string("") is False

    def test_not_string(self) -> None:
        assert is_non_empty_string(42) is False


@pytest.mark.unit
class TestIsToolResultDict:
    def test_valid(self) -> None:
        assert is_tool_result_dict({"success": True, "data": "ok"}) is True

    def test_no_success_key(self) -> None:
        assert is_tool_result_dict({"data": "ok"}) is False

    def test_success_not_bool(self) -> None:
        assert is_tool_result_dict({"success": "yes"}) is False


@pytest.mark.unit
class TestEnsureDict:
    def test_dict_passthrough(self) -> None:
        assert ensure_dict({"a": 1}) == {"a": 1}

    def test_non_dict_returns_default(self) -> None:
        assert ensure_dict("not_dict") == {}

    def test_custom_default(self) -> None:
        assert ensure_dict(42, {"fallback": True}) == {"fallback": True}


@pytest.mark.unit
class TestEnsureList:
    def test_list_passthrough(self) -> None:
        assert ensure_list([1, 2]) == [1, 2]

    def test_non_list_returns_default(self) -> None:
        assert ensure_list("not_list") == []

    def test_custom_default(self) -> None:
        assert ensure_list(42, [99]) == [99]


@pytest.mark.unit
class TestEnsureStr:
    def test_str_passthrough(self) -> None:
        assert ensure_str("hello") == "hello"

    def test_non_str_returns_default(self) -> None:
        assert ensure_str(42) == ""

    def test_custom_default(self) -> None:
        assert ensure_str(None, "fallback") == "fallback"


@pytest.mark.unit
class TestEnsureInt:
    def test_int_passthrough(self) -> None:
        assert ensure_int(42) == 42

    def test_bool_returns_default(self) -> None:
        assert ensure_int(True) == 0

    def test_non_int_returns_default(self) -> None:
        assert ensure_int("42") == 0

    def test_custom_default(self) -> None:
        assert ensure_int(None, -1) == -1


@pytest.mark.unit
class TestEnsureFloat:
    def test_float_passthrough(self) -> None:
        assert ensure_float(3.14) == 3.14

    def test_int_coerced(self) -> None:
        assert ensure_float(42) == 42.0

    def test_bool_returns_default(self) -> None:
        assert ensure_float(True) == 0.0

    def test_non_numeric_returns_default(self) -> None:
        assert ensure_float("3.14") == 0.0


@pytest.mark.unit
class TestGetDictValue:
    def test_key_exists(self) -> None:
        assert get_dict_value({"a": 1}, "a") == 1

    def test_key_missing(self) -> None:
        assert get_dict_value({"a": 1}, "b") is None

    def test_custom_default(self) -> None:
        assert get_dict_value({"a": 1}, "b", "fallback") == "fallback"

    def test_not_dict(self) -> None:
        assert get_dict_value("not_dict", "a") is None


@pytest.mark.unit
class TestGetNestedValue:
    def test_single_level(self) -> None:
        assert get_nested_value({"a": 1}, ["a"]) == 1

    def test_nested(self) -> None:
        assert get_nested_value({"a": {"b": {"c": 42}}}, ["a", "b", "c"]) == 42

    def test_missing_key(self) -> None:
        assert get_nested_value({"a": 1}, ["b"]) is None

    def test_missing_nested_key(self) -> None:
        assert get_nested_value({"a": {"b": 1}}, ["a", "c"]) is None

    def test_non_dict_intermediate(self) -> None:
        assert get_nested_value({"a": "not_dict"}, ["a", "b"]) is None

    def test_empty_keys(self) -> None:
        data = {"a": 1}
        assert get_nested_value(data, []) == data

    def test_custom_default(self) -> None:
        assert get_nested_value({"a": 1}, ["b"], "fallback") == "fallback"
