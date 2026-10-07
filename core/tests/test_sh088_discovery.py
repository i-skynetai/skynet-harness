"""Fake index and pinned-checkout fixtures; no server or network required."""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from sky import discovery
from sky.kbstore import Store, StoreError, canonical, digest, document_text
from sky.recorder import Run


class Discovery(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = Store(self.root)
        self.run = Run.start(role="architect", task="discover", kb="local", agent_id="runtime",
                             root=self.root / ".sky/runs")
        for directory in ("large", "small"):
            (self.root / directory).mkdir()
            (self.root / directory / "code.py").write_bytes(b"cache = {}\n")
        self.head = "a" * 40
        self.patches = [patch("sky.discovery.checkout", return_value=self.head),
                        patch("sky.discovery.git", side_effect=lambda root, *args: "cache = {}\n")]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)
        self.context = SimpleNamespace(sources={"code": {"server": "code",
            "code.find": {"defaults": {"repo": "demo", "branch": "main"}}}},
            servers={"code": {"command": "fake"}})
        self.calls = []

    def call(self, spec, tool, args, **kwargs):
        self.calls.append((tool, args))
        if tool == "list_repos":
            return {"repos": [{"repo": "demo", "branch": "main"}]}
        if tool == "repo_summary":
            return {"files": 3, "version": "index-v1"}
        if tool == "map_coverage":
            return {"children": [{"name": "small", "files": 1, "definitions": 1},
                                 {"name": "large", "files": 2, "definitions": 5}]}
        if tool == "list_files":
            return {"files": [{"path": args["prefix"] + "/code.py"}]}
        if tool == "outline_file":
            return {"signatures": [{"name": "cache", "line": 1, "end_line": 1}]}
        raise AssertionError(tool)

    def work(self, **kwargs):
        return discovery.worklist(self.root, run=self.run, context=self.context, call=self.call, **kwargs)

    def metadata(self):
        return {"type": "knowledge", "module": "large", "category": "pattern",
                "confidence": 0.8, "statement": "A cache is implemented",
                "citations": ["large/code.py:1"]}

    def test_worklist_order_files_symbols_budget_and_run_artifact(self):
        work = self.work()
        self.assertEqual([item["module"] for item in work["modules"]], ["large", "small"])
        self.assertEqual(work["modules"][0]["files"], ["large/code.py"])
        self.assertEqual(work["modules"][0]["symbols"][0]["name"], "cache")
        self.assertTrue(all(len(canonical(item)) <= item["budget"] for item in work["modules"]))
        self.assertEqual(json.loads((self.run.directory / "discovery-worklist.json").read_text(encoding="utf-8")), work)
        self.assertEqual(self.store.records(), [])

    def test_unindexed_file_outline_marks_module_partial_and_names_the_file(self):
        # The live index answers an unresolvable path with an error object, not an
        # empty signature list; that is a fact about the index, not a broken server.
        original = self.call
        def call(spec, tool, args, **kwargs):
            if tool == "outline_file" and args["filepath"] == "large/code.py":
                return {"error": "large/code.py is not indexed in demo: no such file, or more than one file ends with that path."}
            return original(spec, tool, args, **kwargs)
        work = discovery.worklist(self.root, run=self.run, context=self.context, call=call)
        large = work["modules"][0]
        self.assertEqual(large["module"], "large")
        self.assertTrue(large["partial"])
        self.assertEqual(large["unoutlined"], ["large/code.py"])
        self.assertEqual(large["symbols"], [])
        self.assertEqual(work["modules"][1]["symbols"][0]["name"], "cache")

    def test_worklist_reports_partial_and_unvisited_modules(self):
        work = self.work(max_modules=1)
        self.assertTrue(work["modules"][0]["partial"])
        self.assertEqual(work["unvisited"], ["small"])

    def test_worklist_no_index_refused(self):
        with self.assertRaisesRegex(StoreError, "no code index"):
            discovery.worklist(self.root, run=self.run, context=SimpleNamespace(sources={}), call=self.call)

    def test_index_digest_uses_reported_version_else_module_map(self):
        self.assertEqual(self.work()["index_digest"], digest("index-v1"))
        self.assertEqual(discovery.index_identity({}, mapping={"children": []}),
                         (digest(canonical({"children": []})), "module_map"))

    def test_knowledge_put_pins_checkout_and_is_observation(self):
        work = self.work()
        entry = discovery.put(self.store, self.metadata(), "observation", run=self.run, work=work)
        record = discovery.show(self.store, entry["id"])
        self.assertEqual(record["metadata"]["type"], "knowledge")
        self.assertEqual(record["metadata"]["checkout_digest"], digest(self.head))
        self.assertEqual(record["metadata"]["index_digest"], work["index_digest"])
        self.assertEqual(record["body"], "A cache is implemented")

    def test_citation_must_resolve(self):
        metadata = self.metadata()
        metadata["citations"] = ["large/code.py:2"]
        with self.assertRaises(StoreError):
            discovery.put(self.store, metadata, "text", run=self.run)

    def test_citation_must_match_pinned_checkout(self):
        (self.root / "large/code.py").write_bytes(b"cache = changed\n")
        with self.assertRaisesRegex(StoreError, "pinned checkout"):
            discovery.put(self.store, self.metadata(), "text", run=self.run)

    def test_module_must_belong_to_worklist(self):
        metadata = self.metadata()
        metadata["module"] = "unknown"
        with self.assertRaisesRegex(StoreError, "not in discovery worklist"):
            discovery.put(self.store, metadata, "text", run=self.run, work=self.work())

    def test_decision_type_is_refused(self):
        metadata = self.metadata()
        metadata["type"] = "decision"
        with self.assertRaisesRegex(StoreError, "never a decision"):
            discovery.put(self.store, metadata, "text", run=self.run)

    def test_duplicate_normalised_statement_is_unchanged(self):
        first = discovery.put(self.store, self.metadata(), "text", run=self.run)
        before = self.store.manifest()
        metadata = self.metadata()
        metadata["statement"] = "  A CACHE   is implemented  "
        second = discovery.put(self.store, metadata, "text", run=self.run)
        self.assertTrue(second["unchanged"])
        self.assertEqual(first["digest"], second["digest"])
        self.assertEqual(self.store.manifest(), before)

    def test_manual_put_without_index_and_list_show_filters(self):
        entry = discovery.put_text(self.store, document_text(self.metadata(), "text"), run=self.run)
        self.assertEqual(len(discovery.list_knowledge(self.store, module="large", category="pattern", stale=False)), 1)
        self.assertEqual(discovery.list_knowledge(self.store, module="small"), [])
        self.assertEqual(discovery.show(self.store, entry["id"])["metadata"]["module"], "large")

    def test_stale_worklist_refused(self):
        work = self.work()
        work["checkout_revision"] = "b" * 40
        with self.assertRaisesRegex(StoreError, "stale"):
            discovery.put(self.store, self.metadata(), "text", run=self.run, work=work)

    def test_forged_runtime_stamp_refused(self):
        metadata = self.metadata()
        metadata["sky_agent"] = "someone"
        with self.assertRaisesRegex(StoreError, "runtime-owned"):
            discovery.put(self.store, metadata, "text", run=self.run)

    def test_empty_or_doc_id_citations_refused(self):
        for citations in ([], ["id:any"]):
            metadata = self.metadata()
            metadata["citations"] = citations
            with self.assertRaises(StoreError):
                discovery.put(self.store, metadata, "text", run=self.run)

    def test_discover_skill_contract(self):
        repo = Path(__file__).resolve().parents[2]
        body = (repo / "plugin/skills/discover/SKILL.md").read_text(encoding="utf-8")
        for term in ("Use when", "SKILLS.md", "CONFIG.md", "Check your work", "verify"):
            self.assertIn(term, body)
        self.assertNotIn("mcp__", body)
        self.assertNotRegex(body, r"\bSH-\d+\b")

    def test_stale_duplicate_revalidated_keeps_id_and_clears_stale(self):
        from sky import freshness
        first = discovery.put(self.store, self.metadata(), "text", run=self.run)
        freshness.refresh(self.root, paths=["large/code.py"], context=SimpleNamespace(sources={}, servers={}), run=self.run)
        self.assertTrue(self.store.get(first["id"])["metadata"]["stale"])
        second = discovery.put(self.store, self.metadata(), "text", run=self.run)
        self.assertEqual(first["id"], second["id"])
        self.assertFalse(second["unchanged"])
        self.assertFalse(self.store.get(first["id"])["metadata"]["stale"])

    def test_knowledge_provenance_uses_one_manifest_commit(self):
        with patch.object(self.store, "_atomic", wraps=self.store._atomic) as atomic:
            entry = discovery.put(self.store, self.metadata(), "text", run=self.run)
        commits = [call for call in atomic.call_args_list if Path(call.args[0]).name == "manifest.json"]
        self.assertEqual(len(commits), 1)
        saved = self.store.manifest()["documents"][entry["id"]]
        self.assertEqual(saved["checkout_revision"], self.head)
        self.assertIn("large/code.py", saved["citation_digests"])

    def test_context_resolver_accepts_separate_runtime_refresh_mapping(self):
        from sky import context_sources
        path = self.root / ".sky/context.yaml"
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(b'version: 1\nservers:\n  code:\n    command: fake\nsources:\n  index:\n    server: code\n    index.refresh:\n      tool: refresh_index\n')
        context = context_sources.load(root=self.root)
        self.assertEqual(context.sources["index"]["index.refresh"]["tool"], "refresh_index")

    def test_discover_grant_preserves_all_role_tool_sets(self):
        from sky.policy import Policy
        repo = Path(__file__).resolve().parents[2]
        policy = Policy.load(repo / "plugin/policy.yaml")
        self.assertIn("discover", policy.skills_for("architect"))
        for role in policy.roles_named():
            agent = (repo / "plugin/agents" / (role + ".md")).read_text(encoding="utf-8")
            tools = next(line[7:] for line in agent.splitlines() if line.startswith("tools: "))
            self.assertEqual(set(policy.tools_for(role)), set(tools.split(", ")))

    def test_runtime_refresh_cannot_be_granted_to_skill(self):
        from sky.policy import Policy, PolicyError
        repo = Path(__file__).resolve().parents[2]
        from sky import yamlish
        body = yamlish.parse((repo / "plugin/policy.yaml").read_text(encoding="utf-8"))
        body["skills"]["discover"]["tools"].append("index.refresh")
        with self.assertRaisesRegex(PolicyError, "runtime-only"):
            Policy.from_dict(body)

    def test_cli_knowledge_put_list_show_and_refresh(self):
        import io
        from contextlib import redirect_stdout, redirect_stderr
        from sky import cli
        def invoke(*args, text=""):
            out, err = io.StringIO(), io.StringIO()
            with patch("sys.stdin", io.StringIO(text)), redirect_stdout(out), redirect_stderr(err):
                code = cli.main(["kb", *args, "--root", str(self.root)])
            self.assertEqual(code, 0, err.getvalue())
            return out.getvalue()
        with patch("sky.recorder.state_dir", return_value=self.root / "state"), patch.dict("os.environ", {}, clear=True):
            invoke("knowledge", "put", "--from", "-", text=document_text(self.metadata(), "text"))
            rows = json.loads(invoke("knowledge", "list", "--module", "large"))
            self.assertEqual(len(rows), 1)
            shown = json.loads(invoke("knowledge", "show", rows[0]["metadata"]["id"]))
            self.assertEqual(shown["metadata"]["module"], "large")
            with patch("sky.context_sources.load", return_value=SimpleNamespace(sources={}, servers={})):
                output = invoke("refresh", "--paths", "large/code.py")
            self.assertIn("stale", output)

    def test_cli_discovery_builds_worklist_with_fake_index(self):
        import io
        from contextlib import redirect_stdout, redirect_stderr
        from sky import cli
        out, err = io.StringIO(), io.StringIO()
        with patch("sky.context_sources.load", return_value=self.context), patch("sky.context_sources.stdio_call", side_effect=self.call), patch("sky.recorder.state_dir", return_value=self.root / "state"), patch.dict("os.environ", {}, clear=True), redirect_stdout(out), redirect_stderr(err):
            code = cli.main(["kb", "init", "--discover", "--root", str(self.root)])
        self.assertEqual(code, 0, err.getvalue())
        self.assertIn("worklist", out.getvalue())
        self.assertTrue(list((self.root / "state/runs").glob("*/discovery-worklist.json")))
