"""Utilities for repairing malformed JSON that Claude produces in tool_use responses."""

from __future__ import annotations

import json
from typing import Any

_VALID_JSON_ESCAPES = frozenset('"\\/bfnrtu')


def _is_json_key(text: str) -> bool:
    """Check if *text* looks like a JSON object key (short identifier)."""
    return (
        len(text) <= 30
        and "\n" not in text
        and all(c.isalnum() or c == "_" for c in text)
    )


def _followed_by_structural(raw: str, pos: int, n: int) -> bool:
    """True when char at *pos* is followed (after whitespace) by , ] } or end."""
    k = pos + 1
    while k < n and raw[k] in " \t\n\r":
        k += 1
    return k >= n or raw[k] in ",]}"


def _comma_continues_json(raw: str, comma_pos: int, n: int) -> bool:
    """True when comma at *comma_pos* is followed by a JSON key or structure.

    After ``,`` in JSON the next non-whitespace is one of:
    - ``"key":`` — a new key in an object
    - ``{`` or ``[`` — start of a nested value
    """
    k = comma_pos + 1
    while k < n and raw[k] in " \t\n\r":
        k += 1
    if k >= n:
        return True
    if raw[k] in "{[":
        return True
    if raw[k] != '"':
        return False
    # Look for "key": pattern
    m = k + 1
    while m < n and raw[m] != '"':
        if raw[m] == "\\":
            m += 2
            continue
        m += 1
    if m >= n:
        return False
    candidate = raw[k + 1 : m]
    if not _is_json_key(candidate):
        return False
    p = m + 1
    while p < n and raw[p] in " \t\n\r":
        p += 1
    return p < n and raw[p] == ":"


def repair_json_string(raw: str) -> str:
    """Repair malformed JSON that Claude produces when stringifying operations.

    Handles three classes of problems (inside JSON string values only):

    1. **Invalid escape sequences** — e.g. ``\\d``, ``\\w``, ``\\s`` from
       regex patterns in generated code.  Fixed by doubling the backslash
       so ``\\d`` becomes ``\\\\d`` (literal backslash + d).

    2. **Unescaped double-quotes** — e.g. Python triple-quoted docstrings
       ``\"\"\"`` that Claude forgets to escape.  Fixed by escaping any
       ``"`` that does *not* look like a JSON string boundary.

    3. **Structural chars in code** — ``,``, ``]``, ``}``, ``:`` after a
       quote inside code content (JS arrays, Python dicts, function args).
       Multi-level look-ahead verifies the surrounding context before
       deciding to close the string.
    """
    result: list[str] = []
    in_string = False
    string_start = 0
    i = 0
    n = len(raw)

    while i < n:
        ch = raw[i]

        # Inside a string, handle backslash sequences.
        if ch == "\\" and in_string and i + 1 < n:
            next_ch = raw[i + 1]
            if next_ch in _VALID_JSON_ESCAPES:
                # Valid JSON escape — keep as-is.
                result.append(ch)
                result.append(next_ch)
            else:
                # Invalid escape like \d, \w — double the backslash
                # so the JSON parser sees a literal backslash + char.
                result.append("\\\\")
                result.append(next_ch)
            i += 2
            continue

        if ch == '"':
            if not in_string:
                in_string = True
                string_start = i
                result.append(ch)
            else:
                # Look ahead past whitespace to decide if this closes
                # the string.
                j = i + 1
                while j < n and raw[j] in " \t\n\r":
                    j += 1
                if j >= n:
                    # End of input — close the string.
                    in_string = False
                    result.append(ch)
                elif raw[j] in "]}":
                    # Could be a real JSON close or code (e.g. arr = ["v"]).
                    # Verify: ] or } must itself be followed by , ] } or end.
                    if _followed_by_structural(raw, j, n):
                        in_string = False
                        result.append(ch)
                    else:
                        result.append('\\"')
                elif raw[j] == ",":
                    # Could be a JSON separator ("path": "a.py", "content":)
                    # or code (func("a", "b")).  Real JSON commas are
                    # followed by "key": patterns or { / [.
                    if _comma_continues_json(raw, j, n):
                        in_string = False
                        result.append(ch)
                    else:
                        result.append('\\"')
                elif raw[j] == ":":
                    # Could be a real JSON key close ("path":) or code
                    # content containing "key": patterns.  Real JSON keys
                    # are short alphanumeric identifiers.
                    content = raw[string_start + 1 : i]
                    if _is_json_key(content):
                        in_string = False
                        result.append(ch)
                    else:
                        result.append('\\"')
                else:
                    # Unescaped quote inside a string value — escape it.
                    result.append('\\"')
            i += 1
            continue

        result.append(ch)
        i += 1

    return "".join(result)


def parse_stringified_list(v: Any) -> Any:
    """Parse a value that may be a JSON-stringified list.

    Used as a Pydantic ``field_validator(mode="before")`` for list fields
    returned by Claude's tool_use, which sometimes arrives as a JSON string
    instead of an actual list.

    Strategy 1: ``strict=False`` tolerates control characters.
    Strategy 2: ``repair_json_string`` fixes unescaped quotes and
    invalid escape sequences.
    """
    if isinstance(v, str):
        decoder = json.JSONDecoder(strict=False)
        try:
            return decoder.decode(v)
        except json.JSONDecodeError:
            pass
        # Fallback: repair unescaped quotes / invalid escapes and retry
        return decoder.decode(repair_json_string(v))
    return v
