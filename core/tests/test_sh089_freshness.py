"""Refresh snapshot/queue tests with fake Git and fake local index."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from sky import discovery, freshness
from sky.kbstore import Store, StoreError
from sky.recorder import Run


class Freshness(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = Store(self.root)
        self.run = Run.start(role="runtime", task="refresh", kb="local", agent_id="runtime",
                             root=self.root / ".sky/runs")
        for name in ("a.py", "b.py"):
            (self.root / name).write_bytes(b"cache = {}\n")
        self.head = patch("sky.discovery.checkout", return_value="a" * 40)
        self.git = patch("sky.discovery.git", side_effect=lambda root, *args:
                         "a.py\n" if args[0] == "diff" else "cache = {}\n")
        for item in (self.head, self.git):
            item.start()
            self.addCleanup(item.stop)
        self.ids = {}
        for name in ("a.py", "b.py"):
            entry = discovery.put(self.store, {"module": ".", "category": "pattern", "confidence": 0.8,
                "statement": name + " has a cache", "citations": [name + ":1"]}, "text", run=self.run)
            self.ids[name] = entry["id"]
        self.context = SimpleNamespace(sources={}, servers={})

    def refresh(self, paths=None, call=None, context=None):
        return freshness.refresh(self.root, paths=paths, call=call,
                                 context=context or self.context, run=self.run)

    def test_edit_hook_only_enqueues_and_records_ledger(self):
        from sky import refresh_hooks
        path = self.root / "hooks/tools.jsonl"
        payload = {"cwd": str(self.root), "tool_name": "Edit", "tool_input": {"file_path": str(self.root / "a.py")}}
        with patch("sky.refresh_hooks.repository", return_value=self.root), patch("sky.ledger.resolve_path", return_value=path), patch("sky.freshness.refresh") as refresh:
            refresh_hooks.handle("enqueue", payload)
        refresh.assert_not_called()
        self.assertIn("a.py", freshness.read_json(self.store, freshness.PENDING, {}))
        self.assertIn('"failed": false', path.read_text(encoding="utf-8"))

    def test_stop_hook_refreshes_and_never_blocks_on_failure(self):
        from sky import refresh_hooks
        path = self.root / "hooks/tools.jsonl"
        with patch("sky.refresh_hooks.repository", return_value=self.root), patch("sky.ledger.resolve_path", return_value=path), patch("sky.freshness.refresh", side_effect=StoreError("failure")) as refresh:
            refresh_hooks.handle("stop", {"cwd": str(self.root)})
        refresh.assert_called_once_with(self.root)
        self.assertIn('"failed": true', path.read_text(encoding="utf-8"))

    def test_refresh_hook_wrappers_and_matchers_coexist(self):
        import json
        repo = Path(__file__).resolve().parents[2]
        hooks = json.loads((repo / "plugin/hooks/hooks.json").read_text(encoding="utf-8"))["hooks"]
        self.assertEqual({row["matcher"] for row in hooks["PostToolUse"]}, {"Bash", "mcp__.*", "Edit|Write|MultiEdit"})
        self.assertIn("sky-refresh", hooks["Stop"][0]["hooks"][0]["command"])
        for name, action in (("sky-refresh-enqueue", "enqueue"), ("sky-refresh", "stop")):
            body = (repo / "plugin/bin" / name).read_text(encoding="utf-8")
            self.assertTrue(body.startswith("#!/bin/sh\n"))
            self.assertIn("refresh-hook " + action, body)
            self.assertTrue(body.rstrip().endswith("exit 0"))

    def test_refresh_hook_outside_project_stands_aside(self):
        from sky import refresh_hooks
        from sky.context_sources import NotManaged
        with patch("sky.refresh_hooks.repository", side_effect=NotManaged("outside")), patch("sky.freshness.refresh") as refresh:
            refresh_hooks.handle("stop", {})
        refresh.assert_not_called()

    def test_plans_report_stale_knowledge_pins(self):
        from sky import plans
        knowledge = self.store.get(self.ids["a.py"])
        record = {"metadata": {"type": "plan", "pins": {
            "analysis": {"id": "analysis", "digest": "same"},
            "decisions": [], "knowledge": [{"id": self.ids["a.py"], "digest": knowledge["entry"]["digest"]}], "checkout": "unknown"}}, "body": "plan"}
        self.refresh(paths=["a.py"])
        def get(key):
            if key == "plan":
                return record
            if key == "analysis":
                return {"metadata": {}, "entry": {"digest": "same"}}
            return self.store.get(key)
        fake = SimpleNamespace(root=self.root, get=get)
        with patch("sky.plans.validate_schema"), patch("sky.plans.checkout", return_value="unknown"):
            current = plans.current(fake, "plan")
        self.assertIn("1 knowledge pins stale", current["stale_reasons"])

    def index(self, remote=False):
        return SimpleNamespace(sources={"index": {"server": "code", "index.refresh": {
            "tool": "refresh_index", "defaults": {"repo": "demo"}, "args": {"paths": "paths"}}}},
            servers={"code": {"url": "https://stub.invalid"} if remote else {"command": "fake"}})

    def test_refresh_marks_only_cited_changed_paths_and_keeps_revision(self):
        before = self.store.get(self.ids["a.py"])
        result = self.refresh(paths=["a.py"])
        self.assertEqual(result["checked"], 2)
        self.assertEqual(result["stale"], 1)
        self.assertTrue(self.store.get(self.ids["a.py"])["metadata"]["stale"])
        self.assertFalse(self.store.get(self.ids["b.py"])["metadata"]["stale"])
        self.assertTrue((self.root / before["entry"]["path"]).exists())

    def test_refresh_calls_mapped_index_and_updates_digest(self):
        calls = []
        def call(spec, tool, args, **kwargs):
            calls.append((tool, args))
            return {"version": "index-v2"}
        result = self.refresh(paths=["a.py"], call=call, context=self.index())
        self.assertEqual(result["refreshed"], 1)
        self.assertEqual(calls, [("refresh_index", {"repo": "demo", "paths": ["a.py"]})])
        self.assertEqual(self.store.get(self.ids["a.py"])["metadata"]["index_digest"], discovery.digest("index-v2"))

    def test_index_error_recorded_and_pending_preserved(self):
        freshness.enqueue(self.root, ["a.py"])
        def fail(*args, **kwargs):
            raise OSError("server unavailable")
        result = self.refresh(call=fail, context=self.index())
        self.assertEqual(result["failed"], 1)
        self.assertIn("a.py", freshness.read_json(self.store, freshness.PENDING, {}))
        events = (self.run.directory / "events.jsonl").read_text(encoding="utf-8")
        self.assertIn("run.refused", events)
        self.assertIn("kb.refresh", events)

    def test_idempotent_refresh_short_circuits_without_index_call(self):
        calls = []
        def call(*args, **kwargs):
            calls.append(args)
            return {"version": "v2"}
        self.refresh(paths=["a.py"], call=call, context=self.index())
        before = self.store.manifest()
        result = self.refresh(paths=["a.py"], call=call, context=self.index())
        self.assertTrue(result["short_circuit"])
        self.assertEqual(len(calls), 1)
        self.assertEqual(self.store.manifest(), before)

    def test_digest_reconciliation_detects_edit_without_hook(self):
        self.refresh(paths=[])
        (self.root / "a.py").write_bytes(b"cache = changed\n")
        result = self.refresh()
        self.assertFalse(result["short_circuit"])
        self.assertTrue(self.store.get(self.ids["a.py"])["metadata"]["stale"])

    def test_git_diff_detects_checkout_changes(self):
        with patch("sky.discovery.checkout", return_value="b" * 40):
            result = self.refresh()
        self.assertEqual(result["stale"], 1)

    def test_deleted_citation_can_be_marked_stale(self):
        (self.root / "a.py").unlink()
        self.refresh(paths=["a.py"])
        self.assertTrue(self.store.get(self.ids["a.py"])["metadata"]["stale"])

    def test_pending_queue_dedupes_and_rejects_escape(self):
        freshness.enqueue(self.root, ["a.py", "a.py"])
        self.assertEqual(list(freshness.read_json(self.store, freshness.PENDING, {})), ["a.py"])
        with self.assertRaises(StoreError):
            freshness.enqueue(self.root, ["../outside"])

    def test_success_removes_only_unchanged_pending_snapshot(self):
        freshness.enqueue(self.root, ["a.py"])
        def call(*args, **kwargs):
            (self.root / "a.py").write_bytes(b"cache = changed\n")
            freshness.enqueue(self.root, ["a.py", "b.py"])
            return {"version": "v2"}
        self.refresh(paths=["a.py"], call=call, context=self.index())
        self.assertEqual(set(freshness.read_json(self.store, freshness.PENDING, {})), {"a.py", "b.py"})

    def test_success_clears_processed_pending_paths(self):
        freshness.enqueue(self.root, ["a.py"])
        self.refresh(paths=["a.py"], call=lambda *args, **kwargs: {"version": "v2"}, context=self.index())
        self.assertEqual(freshness.read_json(self.store, freshness.PENDING, {}), {})

    def test_remote_refresh_refuses_without_calling_server(self):
        calls = []
        result = self.refresh(paths=["a.py"], call=lambda *args, **kwargs: calls.append(args), context=self.index(remote=True))
        self.assertEqual(result["failed"], 1)
        self.assertEqual(calls, [])

    def test_line_ending_only_change_has_same_digest(self):
        before = freshness.file_digest(self.store, "a.py")
        (self.root / "a.py").write_bytes(b"cache = {}\r\n")
        self.assertEqual(before, freshness.file_digest(self.store, "a.py"))
