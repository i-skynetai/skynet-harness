"""Offline scoring and public demo corpus; fake retrieval where math is isolated."""
import copy
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from sky import evals, kbinit
from sky.kbstore import Store, StoreError

REPO = Path(__file__).resolve().parents[2]


class Evaluation(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = Store(self.root)
        self.item = {"id": "one", "question": "cache", "expect_ids": ["a", "b"], "capability": "search", "k": 3}

    def report(self):
        return evals.evaluate(self.store, [self.item], retrieve=lambda _: [{"id": "a", "excerpt": "cache"}, {"id": "c"}])

    def test_recall_precision_math_counts_unique_records(self):
        row = evals.score(self.item, [{"id": "a"}, {"id": "a"}, {"id": "c"}])
        self.assertEqual(row["recall"], 0.5)
        self.assertEqual(row["precision"], 0.5)
        self.assertEqual(row["retrieved"], 2)

    def test_characters_summed_and_tokens_explicitly_estimated(self):
        second = {**self.item, "id": "two"}
        report = evals.evaluate(self.store, [self.item, second], retrieve=lambda _: [{"id": "a", "excerpt": "café"}])
        self.assertEqual(report["overall"]["characters"], sum(row["characters"] for row in report["items"]))
        self.assertEqual(report["overall"]["estimated_tokens"], report["overall"]["characters"] / 4)
        self.assertIn("estimate", report["token_method"])

    def test_no_hits_precision_is_undefined_and_fails(self):
        baseline = self.report()
        report = evals.evaluate(self.store, [self.item], retrieve=lambda _: [])
        self.assertIsNone(report["overall"]["precision"])
        self.assertTrue(evals.compare(report, baseline))

    def test_matching_baseline_passes(self):
        report = self.report()
        self.assertEqual(evals.compare(report, report), [])

    def test_regression_names_item_and_metric(self):
        report = self.report()
        baseline = copy.deepcopy(report)
        baseline["items"][0]["recall"] = 1
        self.assertIn("one: regression in recall", evals.compare(report, baseline))

    def test_tolerances_apply_to_quality_and_characters(self):
        report = self.report()
        baseline = copy.deepcopy(report)
        baseline["items"][0]["recall"] += 0.1
        baseline["items"][0]["precision"] += 0.1
        baseline["items"][0]["characters"] -= 1
        self.assertEqual(evals.compare(report, baseline, recall_tolerance=0.1, precision_tolerance=0.1, characters_tolerance=1), [])

    def test_invalid_tolerance_refused(self):
        with self.assertRaises(StoreError):
            evals.compare(self.report(), self.report(), recall_tolerance=float("nan"))

    def test_required_phrase_failure_names_item(self):
        item = {**self.item, "must_contain": "missing phrase"}
        report = evals.evaluate(self.store, [item], retrieve=lambda _: [{"id": "a"}])
        self.assertIn("one: required phrase missing", evals.compare(report, report))

    def test_baseline_update_refused_under_governed_session(self):
        with self.assertRaisesRegex(StoreError, "person"):
            evals.update_baseline(self.root / "baseline.json", self.report(), env={"SKY_LAUNCHED": "1"})
        self.assertFalse((self.root / "baseline.json").exists())

    def test_golden_duplicate_unknown_field_and_invalid_k_refused(self):
        for items in ([self.item, self.item], [{**self.item, "unknown": 1}], [{**self.item, "k": True}], [{**self.item, "expect_ids": []}], []):
            with self.assertRaises(StoreError):
                evals.validate(items)

    def test_decisions_capability_calls_decision_finder(self):
        from unittest.mock import patch
        with patch("sky.decisions.find", return_value=[{"id": "a"}]) as find:
            evals.evaluate(self.store, [{**self.item, "capability": "decisions"}])
        find.assert_called_once_with(self.store, "cache", k=3)

    def test_public_golden_runs_offline_and_writes_reports(self):
        from unittest.mock import patch
        shutil.copytree(REPO / "examples/demo-docs", self.root / "docs/demo")
        (self.root / ".sky").mkdir()
        (self.root / ".sky/project.yaml").write_bytes(b"managed: true\ncontext: {}\n")
        with patch("sky.recorder.state_dir", return_value=self.root / "state"):
            kbinit.initialize(self.root, add=["docs/demo"])
        directory = self.root / ".sky/runs/eval"
        baseline = REPO / "evals/baseline.json"
        report = evals.run(self.store, golden=REPO / "evals/golden", baseline=baseline, run=SimpleNamespace(directory=directory))
        self.assertTrue(report["passed"], report["failures"])
        self.assertEqual(report["overall"]["recall"], 1)
        self.assertTrue((directory / "eval-report.json").exists())
        self.assertIn("estimate", (directory / "eval-report.txt").read_text())

    def test_person_can_update_complete_baseline(self):
        report = evals.evaluate(self.store, [{**self.item, "expect_ids": ["a"]}], retrieve=lambda _: [{"id": "a"}])
        path = self.root / "baseline.json"
        evals.update_baseline(path, report, env={})
        self.assertEqual(json.loads(path.read_text()), report)

    def test_cli_eval_pass_and_regression_exit_codes(self):
        import io
        from contextlib import redirect_stdout, redirect_stderr
        from unittest.mock import patch
        from sky import cli
        (self.root / ".sky").mkdir(exist_ok=True)
        (self.root / ".sky/project.yaml").write_bytes(b"managed: true\ncontext: {}\n")
        shutil.copytree(REPO / "examples/demo-docs", self.root / "docs/demo")
        with patch("sky.recorder.state_dir", return_value=self.root / "state"):
            kbinit.initialize(self.root, add=["docs/demo"])
        baseline = self.root / "baseline.json"
        baseline.write_bytes((REPO / "evals/baseline.json").read_bytes())
        def command():
            out, err = io.StringIO(), io.StringIO()
            with patch("sky.context_sources.repository", return_value=self.root), redirect_stdout(out), redirect_stderr(err):
                code = cli.main(["eval", "--golden", str(REPO / "evals/golden"), "--baseline", str(baseline)])
            return code, out.getvalue(), err.getvalue()
        code, out, err = command()
        self.assertEqual((code, err), (0, ""))
        self.assertIn("JSON report:", out)
        self.assertIn("estimate", out)
        body = json.loads(baseline.read_text())
        body["items"][0]["characters"] = 0
        baseline.write_bytes(json.dumps(body).encode())
        code, out, err = command()
        self.assertEqual((code, err), (1, ""))
        self.assertIn("local-adr: regression in characters", out)

    def test_cli_eval_baseline_update_requires_person(self):
        import io
        from contextlib import redirect_stdout, redirect_stderr
        from unittest.mock import patch
        from sky import cli
        baseline = self.root / "new-baseline.json"
        with patch("sky.context_sources.repository", return_value=self.root), patch.dict("os.environ", {"SKY_LAUNCHED": "1"}), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()) as err:
            code = cli.main(["eval", "--golden", str(REPO / "evals/golden"), "--baseline", str(baseline), "--update-baseline"])
        self.assertEqual(code, 1)
        self.assertIn("person", err.getvalue())
        self.assertFalse(baseline.exists())
