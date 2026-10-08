"""Workflow execution uses fake runner; ship never reaches that runner."""
import unittest
from unittest.mock import Mock

from sky import workflows
from tests.test_sh075_workflows import policy


def result(summary="Facts\nVERDICT: APPROVED", outcome="completed"):
    return {"run_id": "run", "agent_id": "agent", "outcome": outcome, "summary": summary}


class Execution(unittest.TestCase):
    def setUp(self):
        self.workflow = workflows.validate(policy())["feature"]
        self.recorder = Mock()
        self.output = []

    def run_steps(self, runner, **kwargs):
        return workflows.run(self.workflow, runner, self.recorder, print_fn=self.output.append, **kwargs)

    def test_failed_architect_gate_stops_before_developer(self):
        called = []
        def runner(step):
            called.append(step["id"])
            return result("Unsafe design\nVERDICT: BLOCKED" if step["id"] == "architect" else "Context")
        outcome = self.run_steps(runner, available=set())
        self.assertFalse(outcome["completed"])
        self.assertNotIn("developer", called)
        self.assertEqual(outcome["stopped_at"], "architect")

    def test_gate_without_verdict_fails_closed(self):
        outcome = self.run_steps(lambda _: result("No verdict"), available=set())
        self.assertEqual(outcome["stopped_at"], "architect")

    def test_blocked_outcome_cannot_be_approved_by_verdict(self):
        outcome = self.run_steps(lambda _: result(outcome="failed"))
        self.assertFalse(outcome["completed"])

    def test_absent_duplicate_capabilities_are_skipped_and_said(self):
        outcome = self.run_steps(lambda _: result(), available=set())
        self.assertTrue(outcome["completed"])
        self.assertEqual(sum(row["status"] == "skipped" for row in outcome["steps"]), 3)
        self.assertTrue(all(any(capability + " absent" in line for line in self.output) for capability in ("tickets", "prs", "kb")))

    def test_missing_optional_session_skips_but_required_stops(self):
        def absent(_):
            raise workflows.MissingSession("session gone")
        for optional in (True, False):
            workflow = workflows.validate(policy([{"id": "review", "session": "review", "optional": optional}]), sessions={"review"})["feature"]
            outcome = workflows.run(workflow, absent, self.recorder, print_fn=self.output.append)
            self.assertEqual(outcome["completed"], optional)
        self.assertTrue(any("skipped" in line for line in self.output))

    def test_ship_prints_commands_and_executes_none(self):
        called = []
        outcome = self.run_steps(lambda step: called.append(step["id"]) or result(), ship_commands=["sky ship", "sky ingest handover.json"])
        self.assertTrue(outcome["completed"])
        self.assertNotIn("ship", called)
        self.assertEqual(self.output, ["sky ship", "sky ingest handover.json"])

    def test_every_step_records_result_and_verdict(self):
        outcome = self.run_steps(lambda _: result(), available=set())
        self.assertEqual(len(self.recorder.event.call_args_list), len(outcome["steps"]))
        for call in self.recorder.event.call_args_list:
            self.assertIn("status", call.kwargs)
            self.assertIn("verdict", call.kwargs)

    def test_ambiguous_or_nonterminal_verdict_refused(self):
        for text in ("VERDICT: APPROVED\nVERDICT: BLOCKED", "VERDICT: APPROVED\nMore work"):
            with self.assertRaises(workflows.WorkflowError):
                workflows.parse_result(result(text))

    def test_result_schema_validation_refuses_malformed_outcome(self):
        with self.assertRaisesRegex(workflows.WorkflowError, "agent-result"):
            workflows.parse_result(result(outcome="success"))
