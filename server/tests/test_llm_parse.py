"""Robustness of LLM JSON parsing — auto-adaptation must not fail on a stray
control character or trailing prose in the model's reply."""
import pytest

from app.services.llm import LLMError, _parse_json


def test_raw_control_chars_inside_strings_tolerated():
    text = '{"endpoints":[{"path":"/a","summary":"line1\nline2\ttab"}]}'
    out = _parse_json(text)
    assert out["endpoints"][0]["summary"] == "line1\nline2\ttab"


def test_fenced_json_extracted():
    assert _parse_json("Here you go:\n```json\n{\"a\": 1}\n```\nthanks") == {"a": 1}


def test_trailing_prose_after_object_trimmed():
    assert _parse_json('{"a": 1, "b": 2}\nHope that helps!') == {"a": 1, "b": 2}


def test_leading_prose_before_object_trimmed():
    assert _parse_json('Sure. {"a": 1}') == {"a": 1}


def test_genuinely_broken_json_raises():
    with pytest.raises(LLMError):
        _parse_json("not json at all, no braces")


def test_salvage_structural_error_midway():
    # model emitted an unescaped quote inside the 2nd element → salvage the 1st
    bad = ('{"endpoints":[{"method":"GET","path":"/a"},'
           '{"method":"GET","path":"/b","summary":"has "quote" here"},'
           '{"method":"POST","path":"/c"}]}')
    out = _parse_json(bad)
    assert [e["path"] for e in out["endpoints"]] == ["/a"]
