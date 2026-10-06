"""A very small, very strict YAML reader.

Core has no third-party dependencies — Ethan depends on core and carries none
either — but the policy file is YAML, because a human edits it and the rest of
the plugin's content is YAML. So core needs to read YAML without PyYAML.

**The danger in a hand-written YAML reader is not failing to parse. It is
parsing something differently from every other YAML tool** — quietly. That
matters more here than almost anywhere else, because the file this reads is the
security policy, and an editor, a linter or a future PyYAML-based tool reading
the same file must reach the same answer.

So the rule is: *refuse what is not understood.* Anchors, aliases, flow
mappings, block scalars, multiple documents, tabs, merge keys — every one is an
error, not a guess. A construct this cannot handle correctly stops the load
instead of being misread.

The same rule kills the classic trap. **Every scalar is a string** unless it is
in an explicit, tiny list: `true`, `false`, `null`, `~`, and whole numbers. The
words YAML versions disagree about — `no`, `yes`, `on`, `off` — are refused
outright rather than resolved one way, and so is anything that starts like a
number without being a whole one: `1.0`, `2026-09-14`, `0x10`. Picking a side
on those would leave two readers of one policy file disagreeing in silence,
which is the failure this whole module is trying to avoid. The cross-check
against PyYAML found all three of these, and refusing them is what made the two
readers agree on every case.

What it supports, and nothing else:

    key: value                  mappings, nested by two-space indentation
    - item                      block sequences, under a key or at the root
    - key: value                a mapping as a sequence item
    key: [a, b, "c d"]          single-line flow sequences
    "quoted"  'quoted'          both quote styles
    # comment                   to end of line, when outside quotes

`parse` is cross-checked against PyYAML in the test suite on the real policy
file and on a corpus of awkward cases, wherever PyYAML happens to be installed.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

#: A mapping key. Deliberately narrow: a value like "Bash(git add:*)" contains a
#: colon, and a looser rule would read it as a key and silently restructure the
#: document. Quoted string keys also support literal tool patterns.
_KEY = re.compile(r'''^([A-Za-z_][A-Za-z0-9_.\-]*|"(?:[^"\\]|\\.)*"|'(?:[^']|'')*')\s*:(?:\s+(.*))?$''')
_INT = re.compile(r"^-?\d+$")

#: Words different YAML versions disagree about. YAML 1.1 (which PyYAML still
#: implements) reads `no` as False; YAML 1.2 reads it as the string "no". Rather
#: than pick a side and have two readers of one policy file disagree in silence,
#: both are refused and the author is asked to be explicit.
_AMBIGUOUS = frozenset({"yes", "no", "on", "off", "y", "n"})

#: A plain scalar that could be read as a number must BE a whole number.
#: Otherwise `1.0`, `2026-09-14` and `0x10` each mean different things to
#: different readers — a float, a date, an integer — and a version field is
#: exactly where that bites.
#:
#: "Could be read as a number" means a digit, optionally behind a sign or a
#: decimal point. An earlier version tested only the first character, which
#: refused `+kb_read` — a string no parser would read as a number. Refusing
#: the genuinely ambiguous is the point; refusing more than that is just an
#: obstacle.
_NUMERIC_LOOKING = re.compile(r"^[-+]?\.?\d")

#: Characters that begin a YAML feature this reader does not implement. Meeting
#: one is an error rather than a guess.
_REFUSED_STARTS = {
    "&": "anchors", "*": "aliases", "|": "block scalars", ">": "folded scalars",
    "{": "flow mappings", "!": "tags", "?": "explicit keys", "%": "directives",
}


class YamlishError(Exception):
    """Always names the line, because a policy file is edited by hand."""

    def __init__(self, line_number: int, message: str):
        self.line_number = line_number
        super().__init__(f"line {line_number}: {message}")


@dataclass(frozen=True)
class _Line:
    number: int
    indent: int
    text: str


def _strip_comment(raw: str, number: int) -> str:
    """Remove a trailing comment without touching a `#` inside quotes."""
    out: list[str] = []
    quote = ""
    i = 0
    while i < len(raw):
        ch = raw[i]
        if quote:
            if ch == "\\" and quote == '"' and i + 1 < len(raw):
                out.append(raw[i:i + 2])
                i += 2
                continue
            if ch == quote:
                quote = ""
            out.append(ch)
        elif ch in "\"'":
            quote = ch
            out.append(ch)
        elif ch == "#" and (not out or raw[i - 1] in " \t"):
            break
        else:
            out.append(ch)
        i += 1
    if quote:
        raise YamlishError(number, "a quote is opened and never closed")
    return "".join(out).rstrip()


def _lines(text: str) -> list[_Line]:
    out: list[_Line] = []
    for number, raw in enumerate(text.splitlines(), start=1):
        if raw.strip() in ("---", ""):
            # A leading document marker is harmless. A second document is not
            # something a single return value can represent, so it is refused
            # below rather than silently dropping everything after it.
            if raw.strip() == "---" and out:
                raise YamlishError(number, "multiple documents are not supported")
            continue
        if raw.lstrip().startswith("#"):
            continue
        if raw.strip() == "...":
            raise YamlishError(number, "document end markers are not supported")
        if "\t" in raw[:len(raw) - len(raw.lstrip())]:
            raise YamlishError(number, "tabs cannot be used to indent YAML")
        body = _strip_comment(raw, number)
        if not body.strip():
            continue
        out.append(_Line(number, len(body) - len(body.lstrip(" ")), body.strip()))
    return out


def _scalar(raw: str, number: int) -> Any:
    """One value. Everything is a string unless it is explicitly something else."""
    text = raw.strip()
    if not text:
        return None
    if text[0] in _REFUSED_STARTS:
        raise YamlishError(number, f"{_REFUSED_STARTS[text[0]]} are not supported")
    if text.startswith("<<"):
        raise YamlishError(number, "merge keys are not supported")
    if text[0] == "[":
        return _flow_sequence(text, number)
    if text[0] == '"':
        return _quoted(text, number, '"')
    if text[0] == "'":
        return _quoted(text, number, "'")
    # The explicit list, and nothing else.
    if text in ("true", "false"):
        return text == "true"
    if text in ("null", "~"):
        return None
    if text.lower() in _AMBIGUOUS:
        raise YamlishError(
            number,
            f"{text!r} means different things to different YAML readers. "
            f"Write true or false, or quote it to mean the word.")
    if _NUMERIC_LOOKING.match(text):
        if not _INT.match(text):
            raise YamlishError(
                number,
                f"{text!r} starts like a number but is not a whole one. A "
                f"decimal point, a date or a hex prefix is read differently by "
                f"different YAML readers — quote it.")
        return int(text)
    if ": " in text or text.endswith(":"):
        raise YamlishError(
            number,
            f"{text!r} contains a colon and is not quoted. YAML readers "
            f"disagree about this — put it in quotes.")
    return text


def _quoted(text: str, number: int, quote: str) -> str:
    if len(text) < 2 or text[-1] != quote:
        raise YamlishError(number, "a quoted value is not closed on the same line")
    body = text[1:-1]
    if quote == "'":
        return body.replace("''", "'")
    out, i = [], 0
    while i < len(body):
        if body[i] == "\\" and i + 1 < len(body):
            out.append({"n": "\n", "t": "\t", '"': '"', "\\": "\\"}
                       .get(body[i + 1], body[i + 1]))
            i += 2
        else:
            out.append(body[i])
            i += 1
    return "".join(out)


def _flow_sequence(text: str, number: int) -> list:
    if not text.endswith("]"):
        raise YamlishError(
            number,
            "a flow sequence must open and close on one line. For a long list, "
            "write it as a block sequence instead — one `- item` per line, "
            "indented under the key.")
    items: list[Any] = []
    current: list[str] = []
    quote = ""
    for ch in text[1:-1]:
        if quote:
            current.append(ch)
            if ch == quote:
                quote = ""
        elif ch in "\"'":
            quote = ch
            current.append(ch)
        elif ch == ",":
            items.append("".join(current))
            current = []
        elif ch == "[":
            raise YamlishError(number, "nested flow sequences are not supported")
        else:
            current.append(ch)
    if quote:
        raise YamlishError(number, "a quote is opened and never closed")
    tail = "".join(current).strip()
    if tail:
        items.append(tail)
    elif items:
        raise YamlishError(number, "a flow sequence ends with a stray comma")
    return [_scalar(item, number) for item in items]


def _block(lines: list[_Line], i: int, indent: int) -> tuple[Any, int]:
    if lines[i].text.startswith("- ") or lines[i].text == "-":
        return _sequence(lines, i, indent)
    return _mapping(lines, i, indent)


def _sequence(lines: list[_Line], i: int, indent: int) -> tuple[list, int]:
    items: list[Any] = []
    while i < len(lines) and lines[i].indent == indent:
        line = lines[i]
        if not (line.text.startswith("- ") or line.text == "-"):
            break
        rest = line.text[1:].strip()
        i += 1
        # Lines belonging to this item: anything indented past the dash.
        owned = []
        while i < len(lines) and lines[i].indent > indent:
            owned.append(lines[i])
            i += 1
        if rest and (_KEY.match(rest) or owned):
            # `- key: value` and any deeper lines form one mapping. The dash's
            # content is re-presented as a line two columns in, which is where
            # the following lines sit.
            virtual = [_Line(line.number, indent + 2, rest)] + \
                      [_Line(l.number, l.indent, l.text) for l in owned]
            value, used = _block(virtual, 0, indent + 2)
            if used != len(virtual):
                raise YamlishError(virtual[used].number, "inconsistent indentation")
            items.append(value)
        elif rest:
            items.append(_scalar(rest, line.number))
        elif owned:
            value, used = _block(owned, 0, owned[0].indent)
            if used != len(owned):
                raise YamlishError(owned[used].number, "inconsistent indentation")
            items.append(value)
        else:
            items.append(None)
    return items, i


def _mapping(lines: list[_Line], i: int, indent: int) -> tuple[dict, int]:
    out: dict[str, Any] = {}
    while i < len(lines) and lines[i].indent == indent:
        line = lines[i]
        if line.text.startswith("- "):
            break
        match = _KEY.match(line.text)
        if not match:
            raise YamlishError(
                line.number,
                f"expected `key: value`, got {line.text!r}. This reader takes a "
                f"small subset of YAML on purpose")
        key, inline = match.group(1), (match.group(2) or "").strip()
        if key.startswith(('"', "'")):
            key = _quoted(key, line.number, key[0])
        if key in out:
            # PyYAML takes the last one silently. In a policy file a duplicated
            # key means two rules were written and one is being ignored.
            raise YamlishError(line.number, f"{key!r} is set twice")
        i += 1
        if inline:
            out[key] = _scalar(inline, line.number)
            continue
        # A block value: deeper lines, or a sequence whose dashes sit at the
        # same column as the key, which is valid YAML and commonly written.
        owned = []
        while i < len(lines) and lines[i].indent > indent:
            owned.append(lines[i])
            i += 1
        if owned:
            value, used = _block(owned, 0, owned[0].indent)
            if used != len(owned):
                raise YamlishError(owned[used].number, "inconsistent indentation")
            out[key] = value
        elif i < len(lines) and lines[i].indent == indent and \
                (lines[i].text.startswith("- ") or lines[i].text == "-"):
            out[key], i = _sequence(lines, i, indent)
        else:
            out[key] = None
    return out, i


def parse(text: str) -> Any:
    """Read the subset, or raise. Never guesses at a construct it does not know."""
    lines = _lines(text)
    if not lines:
        return {}
    if lines[0].indent != 0:
        raise YamlishError(lines[0].number, "the document starts indented")
    value, used = _block(lines, 0, 0)
    if used != len(lines):
        raise YamlishError(lines[used].number, "inconsistent indentation")
    return value
