"""Offline plan inputs, closure checks, ordered steps and computed currency."""
import copy
import io
import json
from contextlib import redirect_stdout, redirect_stderr, contextmanager
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sky import analysis, decisions, plans, cli
from sky.kbstore import Store, StoreError, document_text
from sky.recorder import Run


class Plan(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = Store(self.root)
        self.env = patch.dict(os.environ, {}, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.run = Run.start(role="architect", task="plan", kb="local", agent_id="runtime",
                             root=self.root / ".sky/runs")
        (self.root / "code.py").write_bytes(b"cache = {}\n")
        self.analysis = {"title": "Cache analysis", "goal": "Understand cache",
                         "intent": {"in_scope": ["cache"], "out_of_scope": []},
                         "findings": [{"statement": "A cache exists", "citations": ["code.py:1"]}],
                         "open_questions": [], "risks": [], "evidence_revision": "rev1"}
        self.source = analysis.put(self.store, self.analysis, "# Analysis\n", run=self.run)

    def metadata(self):
        return {"title": "Cache plan", "analysis_id": self.source["id"],
                "steps": [{"id": "implement", "role": "developer", "description": "Bound cache size",
                           "acceptance": ["Eviction test passes"], "inputs": [self.source["id"]]},
                          {"id": "review", "role": "reviewer", "description": "Review the diff",
                           "acceptance": ["Findings resolved"], "inputs": ["implement"]}]}

    def save(self, metadata=None):
        with patch("sky.plans.checkout", return_value="a" * 40):
            return plans.put(self.store, metadata or self.metadata(), "# Plan\n", run=self.run)

    def decision(self):
        metadata = {"title": "Cache", "question": "Which cache?", "options": ["memory", "disk"],
                    "chosen_option": "memory", "rationale": "Small lifetime",
                    "evidence_revision": "rev1", "citations": ["code.py:1"]}
        (self.root / "decision.md").write_bytes(document_text(metadata, "# Cache\n").encode())
        entry = decisions.propose(self.store, "decision.md", run=self.run)
        decisions.transition(self.store, entry["id"], "accept", run=self.run, confirm=lambda _: True)
        return entry

    def test_plan_refuses_with_open_questions(self):
        metadata = copy.deepcopy(self.analysis)
        metadata["open_questions"] = [{"question": "Which cache?", "candidates": [], "reason": "No decision"}]
        analysis.put(self.store, metadata, "# Analysis\nOPEN\n", run=self.run)
        with self.assertRaisesRegex(StoreError, "1 open questions.*run /sky:decide"):
            self.save()

    def test_plan_pins_analysis_and_checkout_digests(self):
        entry = self.save()
        metadata = self.store.get(entry["id"])["metadata"]
        self.assertEqual(metadata["pins"]["analysis"], {"id": self.source["id"], "digest": self.source["digest"]})
        self.assertEqual(metadata["pins"]["checkout"], "a" * 40)
        self.assertEqual([step["id"] for step in metadata["steps"]], ["implement", "review"])

    def test_plan_pins_every_closing_decision(self):
        decision = self.decision()
        metadata = copy.deepcopy(self.analysis)
        metadata["open_questions"] = [{"question": "Which cache?", "candidates": [
            {"id": decision["id"], "status": "accepted", "closes": True}],
            "closed_by": decision["id"], "reason": "Accepted decision"}]
        analysis.put(self.store, metadata, "# Analysis\n", run=self.run)
        record = self.store.get(self.save()["id"])["metadata"]
        self.assertEqual(record["pins"]["decisions"], [plans.pin(self.store.get(decision["id"]))])

    def test_plan_pins_cited_knowledge_records(self):
        knowledge = self.store.put({"type": "knowledge", "title": "Cache observation",
            "project": self.root.name, "scope": ["."], "module": "cache",
            "category": "pattern", "confidence": 0.8, "checkout_digest": "a" * 64,
            "index_digest": "b" * 64, "stale": False, "citations": ["code.py:1"]},
            "A cache is implemented", stamp=self.run.stamp())
        metadata = copy.deepcopy(self.analysis)
        metadata["findings"][0]["citations"] = ["id:" + knowledge["id"]]
        analysis.put(self.store, metadata, "# Analysis\n", run=self.run)
        record = self.store.get(self.save()["id"])["metadata"]
        self.assertEqual(record["pins"]["knowledge"], [{"id": knowledge["id"], "digest": knowledge["digest"]}])

    def test_plan_rechecks_decision_closed_after_analysis_was_written(self):
        decision = self.decision()
        metadata = copy.deepcopy(self.analysis)
        metadata["open_questions"] = [{"question": "Which cache?", "candidates": [
            {"id": decision["id"], "status": "accepted", "closes": True}],
            "closed_by": decision["id"], "reason": "Accepted decision"}]
        analysis.put(self.store, metadata, "# Analysis\n", run=self.run)
        # Replacing the current evidence revision invalidates closure without
        # changing the stored analysis text's assertion.
        current = self.store.get(decision["id"])["metadata"]
        from sky.kbstore import Approval
        clean = {key: value for key, value in current.items() if key not in decisions.RUNTIME_FIELDS}
        clean["evidence_revision"] = "rev2"
        self.store.put(clean, "# Cache\nChanged\n", stamp=self.run.stamp(),
                       approval=Approval("person", "session", "event", "2026-10-06T12:00:00Z"))
        with self.assertRaises(StoreError):
            self.save()

    def test_current_reports_stale_after_analysis_revision_changes(self):
        entry = self.save()
        with patch("sky.plans.checkout", return_value="a" * 40):
            self.assertFalse(plans.current(self.store, entry["id"])["stale"])
        analysis.put(self.store, self.analysis, "# Analysis\nChanged\n", run=self.run)
        with patch("sky.plans.checkout", return_value="a" * 40):
            result = plans.current(self.store, entry["id"])
        self.assertTrue(result["stale"])
        self.assertNotIn("stale", self.store.get(entry["id"])["metadata"])

    def test_unknown_role_is_refused(self):
        metadata = self.metadata()
        metadata["steps"][0]["role"] = "learner"
        with self.assertRaises(StoreError):
            self.save(metadata)

    def test_plan_cannot_overwrite_its_analysis_by_id(self):
        metadata = self.metadata()
        metadata["id"] = self.source["id"]
        with self.assertRaisesRegex(StoreError, "another record type"):
            self.save(metadata)

    def test_duplicate_step_ids_refused(self):
        metadata = self.metadata()
        metadata["steps"][1]["id"] = "implement"
        with self.assertRaisesRegex(StoreError, "duplicate"):
            self.save(metadata)

    def test_step_requires_observable_acceptance(self):
        metadata = self.metadata()
        metadata["steps"][0]["acceptance"] = []
        with self.assertRaises(StoreError):
            self.save(metadata)

    def test_runtime_pins_and_stamps_cannot_be_supplied(self):
        for field in ("pins", "stale", "sky_agent", "sky_run"):
            metadata = self.metadata()
            metadata[field] = "forged"
            with self.assertRaisesRegex(StoreError, "runtime-owned"):
                self.save(metadata)

    def test_current_show_and_list_shapes(self):
        entry = self.save()
        with patch("sky.plans.checkout", return_value="a" * 40):
            result = plans.show(self.store, entry["id"])
            listed = plans.list_plans(self.store)
        self.assertEqual(set(result), {"metadata", "body", "entry", "stale", "stale_reasons"})
        self.assertEqual(listed, [result])

    def test_checkout_unknown_is_explicit(self):
        with patch("sky.plans.subprocess.run", side_effect=OSError("git missing")):
            self.assertEqual(plans.checkout(self.root), "unknown")

    def test_known_checkout_drift_is_stale(self):
        entry = self.save()
        with patch("sky.plans.checkout", return_value="b" * 40):
            self.assertTrue(plans.current(self.store, entry["id"])["stale"])

    def test_plan_put_text_and_requested_analysis_match(self):
        with patch("sky.plans.checkout", return_value="unknown"):
            entry = plans.put_text(self.store, document_text(self.metadata(), "# Plan\n"),
                                   run=self.run, analysis_id=self.source["id"])
        self.assertEqual(entry["type"], "plan")
        with self.assertRaisesRegex(StoreError, "differs"):
            plans.put_text(self.store, document_text(self.metadata(), "# Plan\n"),
                           run=self.run, analysis_id="other")

    def test_plan_draft_has_skill_contract(self):
        repo = Path(__file__).resolve().parents[2]
        body = (repo / "plugin/skills/plan/SKILL.md").read_text(encoding="utf-8")
        for term in ("Use when", "CONFIG.md", "SKILLS.md", "Check your work", "verify"):
            self.assertIn(term, body)
        self.assertNotIn("mcp__", body)
        self.assertNotRegex(body, r"\bSH-\d+\b")

    def command(self, *args, stdin=""):
        out, err = io.StringIO(), io.StringIO()
        with patch.dict(os.environ, {"SKY_STATE_DIR": str(self.root / ".state")}), \
                patch("sys.stdin", io.StringIO(stdin)), patch("sky.plans.checkout", return_value="a" * 40), \
                redirect_stdout(out), redirect_stderr(err):
            code = cli.main(["kb", "plan", *args, "--root", str(self.root)])
        return code, out.getvalue(), err.getvalue()

    def test_cli_plan_put_list_show_with_stale_reason(self):
        code, _, error = self.command("put", "--from", "-", "--analysis", self.source["id"],
                                     stdin=document_text(self.metadata(), "# Plan\n"))
        self.assertEqual(code, 0, error)
        code, output, error = self.command("list")
        self.assertEqual(code, 0, error)
        record = json.loads(output)[0]
        self.assertFalse(record["stale"])
        self.assertEqual(record["stale_reasons"], [])
        analysis.put(self.store, self.analysis, "# Analysis\nChanged\n", run=self.run)
        code, output, error = self.command("show", record["metadata"]["id"])
        self.assertEqual(code, 0, error)
        changed = json.loads(output)
        self.assertTrue(changed["stale"])
        self.assertIn(self.source["id"], changed["stale_reasons"][0])

    def test_cli_plan_refusal_names_open_questions(self):
        metadata = copy.deepcopy(self.analysis)
        metadata["open_questions"] = [{"question": "Which cache?", "candidates": [], "reason": "No decision"}]
        analysis.put(self.store, metadata, "# Analysis\nOPEN\n", run=self.run)
        code, _, error = self.command("put", "--from", "-", "--analysis", self.source["id"],
                                     stdin=document_text(self.metadata(), "# Plan\n"))
        self.assertEqual(code, 1)
        self.assertIn("1 open questions", error)
        self.assertIn("/sky:decide", error)

    def test_published_plan_schema_matches_module(self):
        repo = Path(__file__).resolve().parents[2]
        self.assertEqual(json.loads((repo / "schemas/plan.schema.json").read_text(encoding="utf-8")), plans.SCHEMA)

    def test_normal_store_pins_plan_under_writer_lock(self):
        locked = [False]
        original_lock, original_prepare = self.store.locked, plans.prepare
        @contextmanager
        def tracking_lock():
            with original_lock():
                locked[0] = True
                try:
                    yield
                finally:
                    locked[0] = False
        def prepare(*args, **kwargs):
            self.assertTrue(locked[0])
            return original_prepare(*args, **kwargs)
        metadata = dict(self.metadata(), type="plan", project=self.root.name)
        with patch.object(self.store, "locked", tracking_lock), patch("sky.plans.prepare", side_effect=prepare), \
                patch("sky.plans.checkout", return_value="unknown"):
            self.store.put(metadata, "# Plan\n", stamp=self.run.stamp(), run=self.run)
