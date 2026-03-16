from __future__ import annotations

import json

from bmad_orchestrator.utils.json_repair import parse_stringified_list, repair_json_string

# ── repair_json_string ────────────────────────────────────────────────────────

def test_repair_escapes_triple_quotes():
    """Triple-quoted docstrings inside JSON content should be escaped."""
    raw = (
        '[{"action": "create", "path": "a.py", '
        '"content": "def f():\n    """\n    doc\n    """\n    pass\n"}]'
    )
    repaired = repair_json_string(raw)
    parsed = json.JSONDecoder(strict=False).decode(repaired)
    assert len(parsed) == 1
    assert parsed[0]["path"] == "a.py"
    assert "doc" in parsed[0]["content"]


def test_repair_fixes_invalid_escapes():
    """Regex patterns like \\d, \\w inside generated code must be double-escaped."""
    raw = (
        r'[{"action": "create", "path": "t.py", '
        r'"content": "import re\npattern = re.compile(r\"\d+\w+\")"}]'
    )
    repaired = repair_json_string(raw)
    parsed = json.JSONDecoder(strict=False).decode(repaired)
    assert len(parsed) == 1
    assert parsed[0]["path"] == "t.py"
    assert "\\d+" in parsed[0]["content"]
    assert "\\w+" in parsed[0]["content"]


def test_repair_handles_colon_in_code_content():
    """Dict literals like {"key": val} in code must not break JSON structure."""
    raw = (
        '[{"action": "create", "path": "app.py", '
        '"content": "data = {\n  \"name\": \"test\"\n}\n"}]'
    )
    repaired = repair_json_string(raw)
    parsed = json.JSONDecoder(strict=False).decode(repaired)
    assert len(parsed) == 1
    assert parsed[0]["path"] == "app.py"
    assert "name" in parsed[0]["content"]


def test_repair_handles_array_bracket_in_code():
    """JS arrays like ["hello"] inside code must not close the JSON string."""
    raw = (
        '[{"action": "create", "path": "app.js", '
        '"content": "const arr = [\\"hello\\", \\"world\\"];\nconsole.log(arr);\n"}]'
    )
    repaired = repair_json_string(raw)
    parsed = json.JSONDecoder(strict=False).decode(repaired)
    assert len(parsed) == 1
    assert "hello" in parsed[0]["content"]
    assert "world" in parsed[0]["content"]


def test_repair_handles_comma_in_code():
    """Function args like ("a", "b") inside code must not close the JSON string."""
    raw = (
        '[{"action": "create", "path": "app.js", '
        '"content": "console.log(\\"hello\\", \\"world\\");\n"}]'
    )
    repaired = repair_json_string(raw)
    parsed = json.JSONDecoder(strict=False).decode(repaired)
    assert len(parsed) == 1
    assert "hello" in parsed[0]["content"]


def test_repair_handles_unescaped_quotes_with_comma_in_code():
    """Unescaped quotes around function args should be repaired, not treated as boundary."""
    raw = (
        '[{"action": "create", "path": "app.js", '
        '"content": "log(\\"a\\");\nlog(\\"b\\");\n"}]'
    )
    repaired = repair_json_string(raw)
    parsed = json.JSONDecoder(strict=False).decode(repaired)
    assert len(parsed) == 1
    assert "log" in parsed[0]["content"]


def test_repair_leaves_valid_json_alone():
    """Valid JSON should pass through unchanged."""
    raw = '[{"action": "create", "path": "b.py", "content": "x = 1"}]'
    assert repair_json_string(raw) == raw


# ── parse_stringified_list ────────────────────────────────────────────────────

def test_parse_stringified_list_returns_list_as_is():
    """Actual list values pass through unchanged."""
    v = [{"a": 1}, {"b": 2}]
    assert parse_stringified_list(v) is v


def test_parse_stringified_list_decodes_json_string():
    """A valid JSON string representing a list should be decoded."""
    raw = '["item1", "item2", "item3"]'
    result = parse_stringified_list(raw)
    assert result == ["item1", "item2", "item3"]


def test_parse_stringified_list_handles_control_chars():
    """JSON strings with control characters (newlines, tabs) should parse."""
    raw = '[{"action": "create", "path": "a.py", "content": "x = 1\\n\\ty = 2"}]'
    result = parse_stringified_list(raw)
    assert len(result) == 1
    assert result[0]["path"] == "a.py"


def test_parse_stringified_list_repairs_unescaped_quotes():
    """Unescaped quotes inside JSON strings should be repaired."""
    raw = '[{"action": "create", "path": "t.py", "content": "x = ""hello""\n"}]'
    result = parse_stringified_list(raw)
    assert len(result) == 1
    assert result[0]["path"] == "t.py"


def test_parse_stringified_list_repairs_invalid_escapes():
    """Invalid escape sequences should be double-escaped."""
    raw = r'[{"path": "test.py", "content": "re.compile(r\"\d+\")"}]'
    result = parse_stringified_list(raw)
    assert len(result) == 1
    assert "\\d+" in result[0]["content"]
