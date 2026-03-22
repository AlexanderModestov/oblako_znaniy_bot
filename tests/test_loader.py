from src.core.services.loader import _bool_field, _int_or_none, _str


def test_str_basic():
    assert _str({"key": "  hello  "}, "key") == "hello"


def test_str_missing_key():
    assert _str({}, "key") == ""


def test_str_non_string_value():
    assert _str({"key": 123}, "key") == "123"


def test_int_or_none_valid():
    assert _int_or_none({"key": "42"}, "key") == 42


def test_int_or_none_empty():
    assert _int_or_none({"key": ""}, "key") is None


def test_int_or_none_invalid():
    assert _int_or_none({"key": "abc"}, "key") is None


def test_int_or_none_missing():
    assert _int_or_none({}, "key") is None


def test_bool_field_true_values():
    assert _bool_field({"k": "1"}, "k") is True
    assert _bool_field({"k": "true"}, "k") is True
    assert _bool_field({"k": "True"}, "k") is True
    assert _bool_field({"k": "да"}, "k") is True
    assert _bool_field({"k": "yes"}, "k") is True


def test_bool_field_false_values():
    assert _bool_field({"k": "0"}, "k") is False
    assert _bool_field({"k": ""}, "k") is False
    assert _bool_field({"k": "нет"}, "k") is False
    assert _bool_field({}, "k") is False
