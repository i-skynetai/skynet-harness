"""Offline cited analyses and runtime evidence; no live hand required."""
import json
import io
from contextlib import redirect_stdout, redirect_stderr, contextmanager
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sky import analysis, decisions, ledger, cli
from sky.kbstore import Store, StoreError, document_text
from sky.recorder import Run


class Analyze(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = Store(self.root)
        self.env = patch.dict(os.environ, {}, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.run = Run.start(role="architect", task="analyze", kb="local", agent_id="runtime",
                             root=self.root / ".sky/runs")
        (self.root / "code.py").write_bytes(b"cache = {}\n")

    def metadata(self):
        return {"title": "Cache analysis", "goal": "Understand the cache",
                "intent": {"in_scope": ["cache"], "out_of_scope": ["deployment"]},
                "findings": [{"statement": "A cache exists", "citations": ["code.py:1"]}],
                "open_questions": [], "risks": [], "evidence_revision": "rev1"}

    def save(self, metadata=None, body="# Analysis\nCited facts\n"):
        return analysis.put(self.store, metadata or self.metadata(), body, run=self.run)

    def decision(self, scope=None):
        metadata = {"question": "Which cache?", "title": "Cache", "options": ["memory", "disk"],
                    "chosen_option": "memory", "rationale": "Small lifetime", "scope": scope or ["."],
                    "evidence_revision": "rev1", "citations": ["code.py:1"]}
        (self.root / "proposal.md").write_bytes(document_text(metadata, "# Cache\n").encode())
        entry = decisions.propose(self.store, "proposal.md", run=self.run)
        decisions.transition(self.store, entry["id"], "accept", run=self.run, confirm=lambda _: True)
        return entry["id"]

    def closed_metadata(self, decision_id):
        metadata = self.metadata()
        metadata["open_questions"] = [{"question": "Which cache?",
            "candidates": [{"id": decision_id, "status": "accepted", "closes": True}],
            "closed_by": decision_id, "reason": "Accepted current decision applies"}]
        return metadata

    def test_put_list_show_and_stamps(self):
        entry = self.save()
        record = analysis.show(self.store, entry["id"])
        self.assertEqual(record["metadata"]["sky_run"], self.run.run_id)
        self.assertEqual(len(analysis.list_analyses(self.store)), 1)
        self.assertEqual(record["body"], "# Analysis\nCited facts\n")

    def test_finding_without_citation_refused(self):
        metadata = self.metadata()
        metadata["findings"][0]["citations"] = []
        with self.assertRaises(StoreError):
            self.save(metadata)

    def test_unresolving_file_citation_refused(self):
        metadata = self.metadata()
        metadata["findings"][0]["citations"] = ["code.py:2"]
        with self.assertRaisesRegex(StoreError, "does not resolve"):
            self.save(metadata)

    def test_document_id_citation_resolves(self):
        record = self.store.put({"type": "doc", "title": "Evidence", "project": self.root.name},
                                "Cache evidence", stamp=self.run.stamp())
        metadata = self.metadata()
        metadata["findings"][0]["citations"] = ["id:" + record["id"]]
        self.assertEqual(self.save(metadata)["type"], "analysis")

    def test_closed_by_rechecked_against_store(self):
        decision_id = self.decision()
        self.assertEqual(self.save(self.closed_metadata(decision_id))["type"], "analysis")
        metadata = self.closed_metadata(decision_id)
        metadata["evidence_revision"] = "old"
        with self.assertRaises(StoreError):
            self.save(metadata)

    def test_out_of_scope_decision_cannot_close(self):
        decision_id = self.decision(scope=["core"])
        with self.assertRaises(StoreError):
            self.save(self.closed_metadata(decision_id))

    def test_forged_candidate_closure_refused(self):
        metadata = self.closed_metadata("missing-decision")
        with self.assertRaises(StoreError):
            self.save(metadata)

    def test_closed_by_must_be_an_inspected_candidate(self):
        decision_id = self.decision()
        metadata = self.closed_metadata(decision_id)
        metadata["open_questions"][0]["candidates"] = []
        with self.assertRaisesRegex(StoreError, "inspected"):
            self.save(metadata)

    def test_open_question_with_explanation_is_stored(self):
        metadata = self.metadata()
        metadata["open_questions"] = [{"question": "Which cache?", "candidates": [],
                                        "reason": "No matching accepted decisions"}]
        self.assertEqual(len(analysis.show(self.store, self.save(metadata)["id"])["metadata"]["open_questions"]), 1)

    def test_model_runtime_fields_refused(self):
        for field in ("sky_agent", "sky_run", "approval", "stale", "pins"):
            metadata = self.metadata()
            metadata[field] = "forged"
            with self.assertRaisesRegex(StoreError, "runtime-owned"):
                self.save(metadata)

    def test_model_retrieval_run_refused(self):
        metadata = self.metadata()
        metadata["retrieval"] = {"run": "forged"}
        with self.assertRaisesRegex(StoreError, "runtime-owned"):
            self.save(metadata)

    def test_retrieval_counts_have_valid_shape(self):
        for value in (-1, True, "100"):
            metadata = self.metadata()
            metadata["retrieval"] = {"operations": ["search.keyword"], "characters": value}
            with self.assertRaises(StoreError):
                self.save(metadata)

    def test_non_object_retrieval_refused(self):
        metadata = self.metadata()
        metadata["retrieval"] = None
        with self.assertRaisesRegex(StoreError, "object"):
            self.save(metadata)

    def test_missing_ledger_reports_unknown_measurements(self):
        entry = self.save()
        measured = analysis.show(self.store, entry["id"])["metadata"]["retrieval"]
        self.assertIsNone(measured["hits"])
        self.assertIsNone(measured["characters"])
        self.assertEqual(measured["run"], self.run.run_id)

    def test_retrieval_characters_and_operations_come_from_ledger(self):
        row = {"tool": "mcp__sky_kb__search", "server": "sky_kb", "sequence": 1,
               "input_identity": "a" * 64, "response_chars": 15, "failed": False,
               "counting_method": ledger.COUNTING_METHOD, "operation": "search.keyword"}
        (self.run.directory / "tools.jsonl").write_bytes((json.dumps(row) + "\n").encode())
        metadata = self.metadata()
        metadata["retrieval"] = {"operations": ["fake"], "hits": 999, "characters": 999}
        measured = analysis.show(self.store, self.save(metadata)["id"])["metadata"]["retrieval"]
        self.assertEqual(measured["characters"], 15)
        self.assertEqual(measured["operations"], ["search.keyword"])
        self.assertIsNone(measured["hits"])

    def test_put_text_and_requested_goal_match(self):
        text = document_text(self.metadata(), "# Analysis\n")
        entry = analysis.put_text(self.store, text, run=self.run, goal="Understand the cache")
        self.assertEqual(entry["type"], "analysis")
        with self.assertRaisesRegex(StoreError, "goal differs"):
            analysis.put_text(self.store, text, run=self.run, goal="Another goal")

    def test_analysis_cannot_overwrite_a_decision_by_id(self):
        decision_id = self.decision()
        metadata = self.metadata()
        metadata["id"] = decision_id
        with self.assertRaisesRegex(StoreError, "another record type"):
            self.save(metadata)

    def test_analyze_draft_has_skill_contract(self):
        repo = Path(__file__).resolve().parents[2]
        body = (repo / "plugin/skills/analyze/SKILL.md").read_text(encoding="utf-8")
        for term in ("Use when", "CONFIG.md", "SKILLS.md", "Check your work", "verify"):
            self.assertIn(term, body)
        self.assertNotIn("mcp__", body)
        self.assertNotRegex(body, r"\bSH-\d+\b")

    def command(self, *args, stdin=""):
        out, err = io.StringIO(), io.StringIO()
        with patch.dict(os.environ, {"SKY_STATE_DIR": str(self.root / ".state")}), \
                patch("sys.stdin", io.StringIO(stdin)), redirect_stdout(out), redirect_stderr(err):
            code = cli.main(["kb", "analyze", *args, "--root", str(self.root)])
        return code, out.getvalue(), err.getvalue()

    def test_cli_analyze_put_stdin_list_show(self):
        code, _, error = self.command("put", "--from", "-", "--goal", "Understand the cache",
                                      stdin=document_text(self.metadata(), "# Analysis\n"))
        self.assertEqual(code, 0, error)
        code, output, error = self.command("list")
        self.assertEqual(code, 0, error)
        records = json.loads(output)
        code, output, error = self.command("show", records[0]["metadata"]["id"])
        self.assertEqual(code, 0, error)
        record = json.loads(output)
        self.assertEqual(record["metadata"]["goal"], "Understand the cache")
        self.assertTrue(record["metadata"]["sky_run"])

    def test_cli_analyze_put_from_file(self):
        path = self.root / "analysis.md"
        path.write_bytes(document_text(self.metadata(), "# Analysis\n").encode())
        code, _, error = self.command("put", "--from", str(path))
        self.assertEqual(code, 0, error)

    def test_published_analysis_schema_matches_module(self):
        repo = Path(__file__).resolve().parents[2]
        self.assertEqual(json.loads((repo / "schemas/analysis.schema.json").read_text(encoding="utf-8")), analysis.SCHEMA)

    def test_normal_store_put_validates_analysis_under_writer_lock(self):
        locked = [False]
        original_lock, original_validate = self.store.locked, analysis.validate
        @contextmanager
        def tracking_lock():
            with original_lock():
                locked[0] = True
                try:
                    yield
                finally:
                    locked[0] = False
        def validate(*args):
            self.assertTrue(locked[0])
            return original_validate(*args)
        metadata = dict(self.metadata(), type="analysis", project=self.root.name)
        with patch.object(self.store, "locked", tracking_lock), patch("sky.analysis.validate", side_effect=validate):
            self.store.put(metadata, "# Analysis\n", stamp=self.run.stamp(), run=self.run)

    def test_renamed_module_and_read_only_role_grants(self):
        from sky.policy import Policy
        repo = Path(__file__).resolve().parents[2]
        policy = Policy.load(repo / "plugin/policy.yaml")
        module = (repo / "plugin/skills/module/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("name: module", module)
        self.assertIn("Module Summary Card", module)
        self.assertIn("/sky:module", module)
        for role in ("architect", "developer"):
            self.assertIn("analyze", policy.skills_for(role))
        self.assertIn("plan", policy.skills_for("architect"))
        for skill in ("analyze", "plan"):
            self.assertNotIn("Write", policy.skills[skill]["tools"])
        for role in policy.roles_named():
            line = next(line for line in (repo / "plugin/agents" / (role + ".md")).read_text(encoding="utf-8").splitlines() if line.startswith("tools:"))
            self.assertEqual(set(policy.tools_for(role)), set(line.partition(":")[2].strip().split(", ")), role)
