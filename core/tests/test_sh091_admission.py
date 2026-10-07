"""Admission state tests: fake plan currency, real store locking and writes."""
import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

from sky import admission
from sky.kbstore import Store, StoreError


class Admission(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(Path(self.temp.name))
        self.now = datetime(2026, 10, 7, tzinfo=timezone.utc)
        self.current = {"entry": {"digest": "a" * 64}, "stale": False, "stale_reasons": []}
        self.currency = patch("sky.plans.current", return_value=self.current)
        self.currency.start()
        self.addCleanup(self.currency.stop)

    def issue(self, **kwargs):
        return admission.issue(self.store, "plan-a", run_id="admit-a", env={}, now=self.now, **kwargs)

    def consume(self, **kwargs):
        values = dict(admission_run="admit-a", launch_run="launch-a", role="developer", now=self.now)
        values.update(kwargs)
        return admission.consume(self.store, **values)

    def test_issue_and_consume_records_single_use_and_run_identity(self):
        record = self.issue()
        self.assertFalse(record["used"])
        consumed = self.consume(token=record["token"])
        self.assertTrue(consumed["used"])
        self.assertEqual(consumed["launch_run"], "launch-a")

    def test_second_launch_refused(self):
        self.issue()
        self.consume()
        with self.assertRaisesRegex(StoreError, "already used"):
            self.consume(launch_run="launch-b")

    def test_missing_admission_refused_with_next_step(self):
        with self.assertRaisesRegex(StoreError, "no admitted plan.*sky plan admit"):
            self.consume()

    def test_stale_plan_issue_refused_with_reasons(self):
        self.current.update(stale=True, stale_reasons=["1 knowledge pins stale"])
        with self.assertRaisesRegex(StoreError, "1 knowledge pins stale"):
            self.issue()

    def test_stale_plan_at_launch_does_not_consume(self):
        self.issue()
        self.current.update(stale=True, stale_reasons=["code checkout changed"])
        with self.assertRaisesRegex(StoreError, "code checkout changed"):
            self.consume()
        self.assertFalse(json.loads(admission.path(self.store, "admit-a").read_text())["used"])

    def test_plan_digest_mismatch_refused(self):
        self.issue()
        self.current["entry"]["digest"] = "b" * 64
        with self.assertRaisesRegex(StoreError, "digest mismatch"):
            self.consume()

    def test_ttl_expires_at_boundary_and_can_be_configured(self):
        self.issue()
        with self.assertRaisesRegex(StoreError, "expired"):
            self.consume(now=self.now + timedelta(seconds=60), ttl=60)
        self.assertTrue(self.consume(now=self.now + timedelta(seconds=60), ttl=61)["used"])

    def test_non_implementation_roles_not_gated(self):
        for role in ("architect", "reviewer", "security"):
            self.assertIsNone(self.consume(role=role))

    def test_developer_plan_step_gates_another_launch_role(self):
        with self.assertRaisesRegex(StoreError, "no admitted plan"):
            self.consume(role="architect", step_role="developer")

    def test_explicit_policy_override_does_not_bypass(self):
        with self.assertRaisesRegex(StoreError, "no admitted plan"):
            self.consume(explicit_policy=True)

    def test_governed_agent_cannot_issue(self):
        with self.assertRaisesRegex(StoreError, "person"):
            admission.issue(self.store, "plan-a", run_id="admit-a", env={"SKY_LAUNCHED": ""})

    def test_wrong_token_refused(self):
        self.issue()
        with self.assertRaisesRegex(StoreError, "token mismatch"):
            self.consume(token="b" * 64)

    def test_wrong_project_or_malformed_state_refused(self):
        record = self.issue()
        record["project_root"] = "another-project"
        target = admission.path(self.store, "admit-a")
        self.store._atomic(target, json.dumps(record))
        with self.assertRaisesRegex(StoreError, "another project"):
            self.consume()
        self.store._atomic(target, "[]")
        with self.assertRaisesRegex(StoreError, "malformed"):
            self.consume()

    def test_concurrent_consumers_only_one_succeeds(self):
        self.issue()
        def attempt(number):
            try:
                self.consume(launch_run="launch-" + str(number))
                return True
            except StoreError:
                return False
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sum(pool.map(attempt, (1, 2))), 1)

    def test_events_record_issue_consume_and_refusal_without_token(self):
        run = Mock()
        self.issue(run=run)
        self.consume(run=run)
        with self.assertRaises(StoreError):
            self.consume(run=run)
        self.assertEqual([call.args[0] for call in run.event.call_args_list], list(admission.EVENTS.values()))
        self.assertTrue(all("token" not in call.kwargs for call in run.event.call_args_list))

    def test_run_path_escape_refused(self):
        with self.assertRaisesRegex(StoreError, "run id"):
            self.consume(admission_run="../elsewhere")

    def test_read_only_check_does_not_consume_or_rewrite_state(self):
        record = self.issue()
        target = admission.path(self.store, "admit-a")
        before = target.read_bytes()
        run = Mock()
        checked = admission.check(self.store, admission_run="admit-a", launch_run="launch-a",
                                  role="developer", now=self.now, run=run)
        self.assertFalse(checked["used"])
        self.assertEqual(checked["token"], record["token"])
        self.assertEqual(before, target.read_bytes())
        run.event.assert_not_called()

    def test_consumption_rechecks_token_after_read_only_preflight(self):
        first = self.issue()
        admission.check(self.store, admission_run="admit-a", launch_run="launch-a", role="developer", now=self.now)
        self.issue()
        with self.assertRaisesRegex(StoreError, "token mismatch"):
            self.consume(token=first["token"])

    def test_event_kinds_are_registered_in_runtime_and_published_schema(self):
        from sky import schemas
        repo = Path(__file__).resolve().parents[2]
        published = json.loads((repo / "schemas/run-event.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(published, schemas.json_schema(schemas.RUN_EVENT))
        for kind in admission.EVENTS.values():
            self.assertIn(kind, schemas.EVENT_KINDS)


class AdmissionCLI(unittest.TestCase):
    def setUp(self):
        import os
        from sky import analysis, plans
        from sky.recorder import Run
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.store = Store(self.root)
        self.env = patch.dict(os.environ, {}, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)
        for item in (patch("sky.context_sources.repository", return_value=self.root),
                     patch("sky.recorder.state_dir", return_value=self.root / "state"),
                     patch("sky.plans.checkout", return_value="unknown")):
            item.start()
            self.addCleanup(item.stop)
        (self.root / "code.py").write_bytes(b"cache = {}\n")
        run = Run.start(role="architect", task="plan", kb="local", agent_id="runtime", root=self.root / ".sky/runs")
        source = analysis.put(self.store, {"title": "Cache analysis", "goal": "Understand cache",
            "intent": {"in_scope": ["cache"], "out_of_scope": []},
            "findings": [{"statement": "A cache exists", "citations": ["code.py:1"]}],
            "open_questions": [], "risks": [], "evidence_revision": "rev1"}, "Analysis", run=run)
        self.plan = plans.put(self.store, {"title": "Cache plan", "analysis_id": source["id"],
            "steps": [{"id": "implement", "role": "developer", "description": "Bound cache",
                       "acceptance": ["Test passes"], "inputs": [source["id"]]}]}, "Plan", run=run)

    def command(self, *argv):
        import io
        from contextlib import redirect_stdout, redirect_stderr
        from sky import cli
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def healthy(self):
        from contextlib import ExitStack
        from types import SimpleNamespace
        stack = ExitStack()
        stack.enter_context(patch("sky.cli._resolve_kb", return_value=(SimpleNamespace(catalogue=lambda: None), SimpleNamespace(name="local", code_url=""), None)))
        stack.enter_context(patch("sky.cli._load_policy", return_value=SimpleNamespace(path=None, tools_for=lambda role: ())))
        stack.enter_context(patch("sky.cli.check_definition", return_value=self.root / "agent.md"))
        stack.enter_context(patch("sky.probes.run_all", return_value=Mock(blockers=lambda kind: [])))
        stack.enter_context(patch("sky.launcher.build_env", return_value=Mock(variables={})))
        stack.enter_context(patch("sky.launcher.prove_git_blocked", return_value=(True, "fake proof")))
        stack.enter_context(patch("sky.launcher.write_mcp_config", return_value=self.root / "mcp.json"))
        stack.enter_context(patch("sky.launcher.hand_command", return_value=["fake-hand"]))
        stack.enter_context(patch("sky.hand.run", side_effect=AssertionError("dry run cannot start a hand")))
        return stack

    def test_admit_developer_dry_run_then_second_refused(self):
        code, out, err = self.command("plan", "admit", self.plan["id"])
        self.assertEqual((code, err), (0, ""))
        self.assertIn("expires_at", out)
        token = json.loads(admission.path(self.store, admission.CURRENT_RUN).read_text())["token"]
        self.assertNotIn(token, out)
        with self.healthy():
            code, out, err = self.command("build", "--dry-run", "--role", "developer")
            self.assertEqual((code, err), (0, ""))
            self.assertIn("admission  ok", out)
            code, out, err = self.command("build", "--dry-run", "--role", "developer")
        self.assertEqual(code, 1)
        self.assertIn("already used", err)

    def events(self):
        return [json.loads(line) for path in (self.root / "state/runs").glob("*/events.jsonl")
                for line in path.read_text(encoding="utf-8").splitlines()]

    def test_readiness_refusal_preserves_token_then_retry_consumes_once(self):
        from sky.launcher import Refused
        self.assertEqual(self.command("plan", "admit", self.plan["id"])[0], 0)
        target = admission.path(self.store, admission.CURRENT_RUN)
        before = target.read_bytes()
        with self.healthy():
            with patch("sky.launcher.check_readiness", side_effect=Refused("test runner unavailable")):
                code, _, err = self.command("build", "--dry-run", "--role", "developer")
            self.assertEqual(code, 1)
            self.assertIn("test runner unavailable", err)
            self.assertEqual(target.read_bytes(), before)
            self.assertTrue(any(row["kind"] == "plan.admission_refused" and row.get("reason") == "test runner unavailable" for row in self.events()))
            self.assertFalse(any(row["kind"] == "plan.admission_consumed" for row in self.events()))
            self.assertEqual(self.command("build", "--dry-run", "--role", "developer")[0], 0)
            self.assertTrue(json.loads(target.read_text())["used"])
            code, _, err = self.command("build", "--dry-run", "--role", "developer")
        self.assertEqual(code, 1)
        self.assertIn("already used", err)
        self.assertEqual(sum(row["kind"] == "plan.admission_consumed" for row in self.events()), 1)

    def test_definition_refusal_records_reason_without_consuming(self):
        from sky.agent_definitions import DefinitionError
        self.command("plan", "admit", self.plan["id"])
        target = admission.path(self.store, admission.CURRENT_RUN)
        before = target.read_bytes()
        with self.healthy(), patch("sky.cli.check_definition", side_effect=DefinitionError("definition drift")):
            code, _, err = self.command("build", "--dry-run", "--role", "developer")
        self.assertEqual(code, 1)
        self.assertIn("definition drift", err)
        self.assertEqual(before, target.read_bytes())
        self.assertTrue(any(row["kind"] == "plan.admission_refused" and row.get("reason") == "definition drift" for row in self.events()))

    def test_reviewer_dry_run_unaffected_without_admission(self):
        with self.healthy():
            code, out, err = self.command("build", "--dry-run", "--role", "reviewer")
        self.assertEqual((code, err), (0, ""))

    def test_route_developer_dry_run_requires_admission(self):
        with self.healthy():
            code, _, err = self.command("route", "--dry-run", "--role", "developer")
        self.assertEqual(code, 1)
        self.assertIn("no admitted plan", err)

    def test_admission_cli_human_only_and_status_hides_token(self):
        with patch.dict("os.environ", {"SKY_LAUNCHED": "1"}):
            code, _, err = self.command("plan", "admit", self.plan["id"])
        self.assertEqual(code, 1)
        self.assertIn("person", err)
        self.command("plan", "admit", self.plan["id"], "--ttl", "1")
        code, out, err = self.command("plan", "admission")
        self.assertEqual((code, err), (0, ""))
        self.assertNotIn("token", out)
        self.assertIn('"used": false', out)

    def test_policy_override_still_requires_admission(self):
        with self.healthy(), patch.dict("os.environ", {"SKY_POLICY": "fixture"}):
            code, _, err = self.command("--policy", "fixture", "build", "--dry-run")
        self.assertEqual(code, 1)
        self.assertIn("no admitted plan", err)
