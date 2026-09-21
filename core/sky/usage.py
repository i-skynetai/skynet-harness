"""What a run cost — taken from the hand's own report, never estimated.

One of the three purposes of this system is that a hand should not burn tokens
*finding* context, and that has to be visible as a number: per run here, per
task on Ethan's console. This module produces the per-run number.

**The rule, decided 2026-09-14: record everything, show money, judge on
tokens.** Everything the hand reports is recorded. Money is what a person
reads on the console, because it is comparable across hands. Learning is
judged on tokens per task kind *within one hand*, because a Claude token, a
Codex token and a Kimi token are not the same unit and pricing moves.

Two things this refuses to do, and why:

*It never estimates.* If the hand did not report usage, the answer is "not
available" with the reason — not a guess from the log length. A guessed number
on a dashboard is worse than a blank, because it gets believed.

*It never reads the hand's text as usage.* The report is the structured result
object the hand emits, not anything the model wrote. A model can write "this
cost $0.02"; that is a claim, not a measurement.

The shape parsed here is Claude Code's result message in `stream-json` output:
a final line `{"type": "result", "subtype": "success", "total_cost_usd": …,
"num_turns": …, "duration_ms": …, "usage": {"input_tokens": …, …}, "result":
"<the text>"}`. **Verified against a real result object on 2026-09-14** (a
not-logged-in run, so every number was zero — but the shape is the shape): the
usage fields sit under `usage`, the text is in `result`, and the object also
carries `is_error`, `permission_denials`, `modelUsage`, `stop_reason`,
`terminal_reason` and more. The parser is
tolerant: a missing field is `None`, never an exception, and a run whose
usage cannot be read still finishes and still records *why*.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path


@dataclass(frozen=True)
class Usage:
    hand: str
    source: str                     # e.g. "claude:stream-json"
    subtype: str                    # success · error_max_turns · error_during_execution …
    cost_usd: float | None
    input_tokens: int | None
    output_tokens: int | None
    cache_read_tokens: int | None
    cache_write_tokens: int | None
    turns: int | None
    duration_ms: int | None
    duration_api_ms: int | None
    result_text: str = ""           # the hand's final text — for display, never for usage
    #: The real shape (seen 2026-09-14) can say `subtype: success` AND
    #: `is_error: true` — a run that did nothing, such as "Not logged in".
    #: Both are kept as reported; `is_error` is what to trust.
    is_error: bool = False
    #: Tools the host refused during the run. This is tier A enforcing itself,
    #: in machine-readable form — the evidence G6 is about.
    denials: tuple = ()
    #: Which models the run used, so "tokens within one hand" can be "within
    #: one model" when a hand mixes them.
    models: tuple = ()

    @property
    def tokens(self) -> int | None:
        """The number learning is judged on: tokens the model actually worked
        through, input plus output.

        Cache reads and writes are recorded but kept out of this number on
        purpose. They are billed at a fraction of the rate and they rise and
        fall with prompt caching, so including them would let a caching change
        look like the knowledge base getting better. That is a refinement of
        the owner's rule, stated here so it can be overruled.
        """
        if self.input_tokens is None and self.output_tokens is None:
            return None
        return (self.input_tokens or 0) + (self.output_tokens or 0)

    def as_event(self) -> dict:
        """What goes into `events.jsonl` as `run.usage`."""
        body = asdict(self)
        body.pop("result_text")     # the text is in the hand's log; the event is numbers
        body["tokens"] = self.tokens
        body["available"] = True
        return body

    def __str__(self) -> str:
        cost = f"${self.cost_usd:.4f}" if self.cost_usd is not None else "cost n/a"
        toks = f"{self.tokens:,} tokens" if self.tokens is not None else "tokens n/a"
        turns = f"{self.turns} turns" if self.turns is not None else ""
        err = "error" if self.is_error else ""
        den = f"{len(self.denials)} denied" if self.denials else ""
        return " · ".join(x for x in (err, cost, toks, turns, den) if x)


@dataclass(frozen=True)
class NoUsage:
    """The hand reported nothing this module can read — and here is why."""
    hand: str
    reason: str
    result_text: str = ""

    @property
    def tokens(self) -> None:
        return None

    def as_event(self) -> dict:
        return {"hand": self.hand, "available": False, "reason": self.reason}

    def __str__(self) -> str:
        return f"usage not available — {self.reason}"


#: Hands whose output this module knows how to read.
READABLE = {"claude"}


def from_log(hand: str, log_path: Path) -> Usage | NoUsage:
    """Read the hand's log after the run and find its result object.

    Reads the durable file rather than an in-memory tail: the tail is capped,
    and the log is what a person opens later when the number looks wrong.
    """
    if hand not in READABLE:
        return NoUsage(hand, f"{hand} does not yet report usage in a form core reads; "
                             f"only claude's stream-json result is parsed today")
    try:
        text = log_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return NoUsage(hand, f"cannot read {log_path}: {exc}")
    return from_lines(hand, text.splitlines())


def from_lines(hand: str, lines: list[str]) -> Usage | NoUsage:
    """Find the result object. Last one wins, scanned from the end.

    Two shapes are accepted: `stream-json` (one JSON object per line, the
    result last) and `json` (one object for the whole output, which may span
    lines). The second is not what the launcher asks for — see `launcher` for
    why — but a log produced that way should still be readable.
    """
    if hand not in READABLE:
        return NoUsage(hand, f"{hand} is not a hand whose usage core reads")
    candidates = [ln for ln in lines if ln.strip()]
    if not candidates:
        return NoUsage(hand, "the hand produced no output at all")

    # stream-json: the result is the last well-formed object with type=result.
    for line in reversed(candidates):
        obj = _object(line)
        if obj is not None and obj.get("type") == "result":
            return _claude_result(hand, obj, "claude:stream-json")

    # json: the whole output is one object.
    obj = _object("\n".join(candidates))
    if obj is not None and obj.get("type") == "result":
        return _claude_result(hand, obj, "claude:json")

    if any(_object(ln) is not None for ln in candidates):
        return NoUsage(hand, "the hand emitted JSON but no result object — it may have "
                             "been stopped before finishing")
    return NoUsage(hand, "the hand's output is not JSON — was it started with "
                         "--output-format stream-json?")


def _object(text: str) -> dict | None:
    text = text.strip()
    if not text.startswith("{"):
        return None
    try:
        value = json.loads(text)
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


def _int(value) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return int(value)


def _float(value) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _claude_result(hand: str, obj: dict, source: str) -> Usage:
    usage = obj.get("usage") if isinstance(obj.get("usage"), dict) else {}
    result_text = obj.get("result")
    raw_denials = obj.get("permission_denials")
    denials = tuple(
        str(d.get("tool_name") or d.get("tool") or "?") if isinstance(d, dict) else str(d)
        for d in raw_denials) if isinstance(raw_denials, list) else ()
    model_usage = obj.get("modelUsage")
    models = tuple(sorted(model_usage)) if isinstance(model_usage, dict) else ()
    return Usage(
        hand=hand,
        source=source,
        subtype=str(obj.get("subtype") or ("error" if obj.get("is_error") else "unknown")),
        cost_usd=_float(obj.get("total_cost_usd")),
        input_tokens=_int(usage.get("input_tokens")),
        output_tokens=_int(usage.get("output_tokens")),
        cache_read_tokens=_int(usage.get("cache_read_input_tokens")),
        cache_write_tokens=_int(usage.get("cache_creation_input_tokens")),
        turns=_int(obj.get("num_turns")),
        duration_ms=_int(obj.get("duration_ms")),
        duration_api_ms=_int(obj.get("duration_api_ms")),
        result_text=result_text if isinstance(result_text, str) else "",
        is_error=bool(obj.get("is_error")),
        denials=denials,
        models=models,
    )
