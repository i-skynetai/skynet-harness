"""Tests for the bill — what a run cost, from the hand's own report.

The two rules under test: it never estimates, and it never reads the model's
prose as a measurement. Every number here is invented; the shape is Claude
Code's documented result message, whose field names were found in the
installed executable.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sky import usage  # noqa: E402

# The shape of a real result object, as pasted from a terminal on 2026-09-14.
# Numbers are invented; keys are the real ones, including the many this module
# does not use — the parser must tolerate the whole thing.
RESULT = {
    "type": "result", "subtype": "success", "is_error": False,
    "api_error_status": None,
    "duration_ms": 41200, "duration_api_ms": 38900, "num_turns": 7,
    "result": "Added the endpoint and its tests. Branch ready.",
    "stop_reason": "end_turn", "session_id": "s-1", "total_cost_usd": 0.0123,
    "usage": {"input_tokens": 1000, "cache_creation_input_tokens": 200,
              "cache_read_input_tokens": 9000, "output_tokens": 500,
              "server_tool_use": {"web_search_requests": 0, "web_fetch_requests": 0},
              "service_tier": "standard",
              "cache_creation": {"ephemeral_1h_input_tokens": 0,
                                 "ephemeral_5m_input_tokens": 200},
              "inference_geo": "", "iterations": [], "speed": "standard"},
    "modelUsage": {"claude-x": {"inputTokens": 1000}},
    "permission_denials": [],
    "terminal_reason": "completed", "fast_mode_state": "off", "uuid": "u-1",
}

#: Exactly what came back from `claude -p --verbose --output-format stream-json`
#: on a machine whose CLI was not logged in. `subtype` says success; `is_error`
#: says otherwise. Kept verbatim (session ids aside) as the regression corpus.
NOT_LOGGED_IN = {
    "type": "result", "subtype": "success", "is_error": True,
    "api_error_status": None, "duration_ms": 27, "duration_api_ms": 0,
    "num_turns": 1, "result": "Not logged in \u00b7 Please run /login",
    "stop_reason": "stop_sequence", "session_id": "s-0", "total_cost_usd": 0,
    "usage": {"input_tokens": 0, "cache_creation_input_tokens": 0,
              "cache_read_input_tokens": 0, "output_tokens": 0,
              "server_tool_use": {"web_search_requests": 0, "web_fetch_requests": 0},
              "service_tier": "standard",
              "cache_creation": {"ephemeral_1h_input_tokens": 0,
                                 "ephemeral_5m_input_tokens": 0},
              "inference_geo": "", "iterations": [], "speed": "standard"},
    "modelUsage": {}, "permission_denials": [], "terminal_reason": "completed",
    "fast_mode_state": "off", "uuid": "u-0",
}

STREAM = [
    json.dumps({"type": "system", "subtype": "init", "session_id": "s-1"}),
    json.dumps({"type": "assistant", "message": {"content": [{"type": "text",
                "text": "this cost $99.00"}]}}),          # a claim, not a measurement
    json.dumps(RESULT),
]


class ItReadsTheHandsReport(unittest.TestCase):
    def test_the_stream_json_result_line_is_parsed(self):
        u = usage.from_lines("claude", STREAM)
        self.assertIsInstance(u, usage.Usage)
        self.assertEqual(u.cost_usd, 0.0123)
        self.assertEqual(u.input_tokens, 1000)
        self.assertEqual(u.output_tokens, 500)
        self.assertEqual(u.cache_read_tokens, 9000)
        self.assertEqual(u.cache_write_tokens, 200)
        self.assertEqual(u.turns, 7)
        self.assertEqual(u.duration_ms, 41200)
        self.assertEqual(u.subtype, "success")
        self.assertEqual(u.source, "claude:stream-json")

    def test_the_final_text_is_kept_for_display(self):
        u = usage.from_lines("claude", STREAM)
        self.assertEqual(u.result_text, "Added the endpoint and its tests. Branch ready.")

    def test_the_last_result_wins(self):
        first = dict(RESULT, total_cost_usd=0.5)
        u = usage.from_lines("claude", [json.dumps(first), json.dumps(RESULT)])
        self.assertEqual(u.cost_usd, 0.0123)

    def test_json_mode_output_is_also_readable(self):
        """Not what the launcher asks for, but a log made that way still reads."""
        u = usage.from_lines("claude", json.dumps(RESULT, indent=2).splitlines())
        self.assertIsInstance(u, usage.Usage)
        self.assertEqual(u.source, "claude:json")
        self.assertEqual(u.turns, 7)

    def test_it_reads_from_the_log_file(self):
        log = Path(tempfile.mkdtemp()) / "hand.log"
        log.write_text("\n".join(STREAM) + "\n")
        self.assertEqual(usage.from_log("claude", log).cost_usd, 0.0123)


class TheJudgingNumber(unittest.TestCase):
    """Record everything; show money; judge on tokens."""

    def test_tokens_is_input_plus_output(self):
        self.assertEqual(usage.from_lines("claude", STREAM).tokens, 1500)

    def test_cache_tokens_are_recorded_but_not_judged_on(self):
        """A caching change must not be able to look like learning."""
        u = usage.from_lines("claude", STREAM)
        self.assertEqual(u.cache_read_tokens, 9000)
        self.assertEqual(u.tokens, 1500)

    def test_the_event_carries_every_number_and_not_the_text(self):
        event = usage.from_lines("claude", STREAM).as_event()
        for key in ("cost_usd", "input_tokens", "output_tokens", "cache_read_tokens",
                    "cache_write_tokens", "turns", "duration_ms", "tokens"):
            self.assertIn(key, event)
        self.assertTrue(event["available"])
        self.assertNotIn("result_text", event, "the text belongs in the log, not the event")

    def test_it_prints_money_first(self):
        self.assertTrue(str(usage.from_lines("claude", STREAM)).startswith("$0.0123"))


class TheRealShape(unittest.TestCase):
    """What a terminal actually returned, and what the fixture had missed."""

    def test_the_verbatim_not_logged_in_result_parses(self):
        u = usage.from_lines("claude", [json.dumps(NOT_LOGGED_IN)])
        self.assertIsInstance(u, usage.Usage)
        self.assertEqual(u.cost_usd, 0.0)
        self.assertEqual(u.tokens, 0)
        self.assertEqual(u.turns, 1)
        self.assertEqual(u.result_text, "Not logged in \u00b7 Please run /login")

    def test_subtype_success_with_is_error_true_is_reported_as_an_error(self):
        """The one that would have lied on a dashboard."""
        u = usage.from_lines("claude", [json.dumps(NOT_LOGGED_IN)])
        self.assertEqual(u.subtype, "success")          # kept as reported
        self.assertTrue(u.is_error)                     # what to trust
        self.assertTrue(str(u).startswith("error"))
        self.assertTrue(u.as_event()["is_error"])

    def test_permission_denials_are_recorded_by_tool_name(self):
        """The host refusing a tool is tier A enforcing itself — G6's evidence."""
        denied = dict(RESULT, permission_denials=[
            {"tool_name": "Edit", "tool_use_id": "t1", "tool_input": {"file_path": "x"}},
            {"tool_name": "Write", "tool_use_id": "t2", "tool_input": {}}])
        u = usage.from_lines("claude", [json.dumps(denied)])
        self.assertEqual(u.denials, ("Edit", "Write"))
        self.assertIn("2 denied", str(u))
        self.assertEqual(list(u.as_event()["denials"]), ["Edit", "Write"])

    def test_models_used_are_recorded(self):
        u = usage.from_lines("claude", [json.dumps(RESULT)])
        self.assertEqual(u.models, ("claude-x",))


class ItNeverEstimates(unittest.TestCase):
    def test_a_hand_that_only_wrote_prose_yields_no_usage_not_a_guess(self):
        """`this cost $99.00` in the text is a claim. It is not read."""
        r = usage.from_lines("claude", ["I did the work.", "This cost $99.00."])
        self.assertIsInstance(r, usage.NoUsage)
        self.assertIn("not JSON", r.reason)
        self.assertIsNone(r.tokens)

    def test_a_run_stopped_before_its_result_says_so(self):
        r = usage.from_lines("claude", STREAM[:2])
        self.assertIsInstance(r, usage.NoUsage)
        self.assertIn("no result object", r.reason)

    def test_an_empty_log_says_so(self):
        r = usage.from_lines("claude", [])
        self.assertIsInstance(r, usage.NoUsage)
        self.assertIn("no output", r.reason)

    def test_a_hand_core_cannot_read_yet_is_named_not_faked(self):
        for hand in ("codex", "kimi"):
            with self.subTest(hand=hand):
                r = usage.from_log(hand, Path("/nonexistent"))
                self.assertIsInstance(r, usage.NoUsage)
                self.assertIn(hand, r.reason)
                self.assertFalse(r.as_event()["available"])

    def test_a_missing_field_is_none_never_a_crash(self):
        thin = {"type": "result", "subtype": "success", "result": "ok"}
        u = usage.from_lines("claude", [json.dumps(thin)])
        self.assertIsInstance(u, usage.Usage)
        self.assertIsNone(u.cost_usd)
        self.assertIsNone(u.tokens)
        self.assertIsNone(u.turns)

    def test_a_bool_is_not_a_number(self):
        """isinstance(True, int) is True; a flag must not become a token count."""
        odd = dict(RESULT, num_turns=True, total_cost_usd=False)
        u = usage.from_lines("claude", [json.dumps(odd)])
        self.assertIsNone(u.turns)
        self.assertIsNone(u.cost_usd)

    def test_an_error_result_still_reports_what_it_cost(self):
        """A failed run is not free; the bill must include it."""
        err = dict(RESULT, subtype="error_max_turns", is_error=True)
        u = usage.from_lines("claude", [json.dumps(err)])
        self.assertEqual(u.subtype, "error_max_turns")
        self.assertEqual(u.cost_usd, 0.0123)


if __name__ == "__main__":
    unittest.main(verbosity=2)
