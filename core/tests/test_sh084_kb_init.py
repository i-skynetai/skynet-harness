"""SH-084 document initialization and the public offline corpus contract."""
import json
import io
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from contextlib import redirect_stdout, redirect_stderr

from sky import cli, context_sources, kbinit, kbserve, probes, project, recorder, setup, yamlish
from sky.readiness import Brain, Part, State
from sky.kbstore import MAX_DOCUMENT_CHARS, Store, StoreError
from sky.codeport import skygraph_adapter

CORPUS = Path(__file__).resolve().parents[2] / "examples/demo-docs"


class KBInit(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        (self.root / ".sky").mkdir()
        (self.root / ".sky/project.yaml").write_text("managed: true\n", encoding="utf-8")
        self.env = patch.dict(os.environ, {"SKY_STATE_DIR": str(self.root / "state")})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.store = Store(self.root)

    def write(self, relative, text="# Sample\nPublic sample text.\n"):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))
        return path

    def init(self, **kwargs):
        return kbinit.initialize(self.root, **kwargs)

    def test_enumerates_default_sources_and_explicit_additions(self):
        for path in ("README.md", "docs/guide.md", "docs/adr/one.md", ".sky/handovers/one.md", "extra/one.md"):
            self.write(path)
        selected, _ = kbinit.enumerate_sources(self.root, add=["extra"])
        self.assertEqual(len(selected), 5)
        self.assertIn(".sky/handovers/one.md", selected)

    def test_overlapping_directories_are_deduplicated(self):
        self.write("docs/adr/one.md")
        selected, _ = kbinit.enumerate_sources(self.root, add=["docs/adr", "docs/adr/../adr/one.md"])
        self.assertEqual(selected, ["docs/adr/one.md"])

    def test_excludes_store_runs_vcs_and_secret_style_files(self):
        for path in (".sky/kb/private.md", ".sky/runs/run/private.md", ".git/private.md", "docs/.env.local", "docs/cert.pem", "docs/key.key"):
            self.write(path)
        self.write("docs/public.md")
        selected, skipped = kbinit.enumerate_sources(self.root, add=[".sky", ".git"])
        self.assertIn("docs/public.md", selected)
        self.assertNotIn(".sky/kb/private.md", selected)
        self.assertTrue(any(row["source"] == "docs/.env.local" for row in skipped))
        self.assertTrue(any("VCS" in row["reason"] for row in skipped))

    def test_infers_document_type_from_location(self):
        expected = {"README.md": "readme", "docs/adr/one.md": "adr", "docs/features/one.md": "design",
                    ".sky/handovers/one.md": "handover", "docs/guide.md": "doc"}
        for name, kind in expected.items():
            with self.subTest(name=name):
                self.assertEqual(kbinit.infer_type(name), kind)

    def test_plain_document_title_and_runtime_attribution(self):
        self.write("docs/guide.md", "# Cedar title\nPublic content.\n")
        result = self.init()
        record = self.store.records()[0]
        self.assertEqual(record["metadata"]["title"], "Cedar title")
        self.assertEqual(record["metadata"]["sky_agent"], "runtime")
        self.assertEqual(record["metadata"]["sky_run"], result["run_id"])
        events = [json.loads(line) for line in (Path(result["run_directory"]) / "events.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertTrue(any(event["kind"] == "kb.put" for event in events))
        self.assertEqual(events[-1]["kind"], "run.finish")

    def test_frontmatter_type_is_preserved(self):
        self.write("docs/guide.md", '---\ntype: design\ntitle: Specified title\nproject: public-demo\nsource: docs/guide.md\n---\n# Heading\nPublic body.\n')
        self.init()
        self.assertEqual(self.store.records()[0]["metadata"]["type"], "design")

    def test_frontmatter_defaults_use_canonical_source_and_heading(self):
        self.write("docs/adr/one.md", "---\nrelates_to: []\n---\n# Local choice\nPublic body.\n")
        self.init()
        metadata = self.store.records()[0]["metadata"]
        self.assertEqual(metadata["source"], "docs/adr/one.md")
        self.assertEqual(metadata["title"], "Local choice")
        self.assertEqual(metadata["type"], "adr")
        self.assertEqual(metadata["project"], self.root.name)

    def test_frontmatter_cannot_claim_another_source(self):
        self.write("docs/one.md", "---\nsource: docs/other.md\n---\n# Sample\nPublic body.\n")
        result = self.init()
        self.assertEqual(result["stored"], [])
        self.assertIn("canonical input path", result["skipped"][0]["reason"])

    def test_second_run_preserves_manifest_and_revisions(self):
        self.write("README.md")
        first = self.init()
        before = (self.root / ".sky/kb/manifest.json").read_bytes()
        revisions = sorted(self.root.glob(".sky/kb/documents/*/*.md"))
        second = self.init()
        self.assertEqual(second["stored"], [])
        self.assertEqual(second["unchanged"], ["README.md"])
        self.assertEqual((self.root / ".sky/kb/manifest.json").read_bytes(), before)
        self.assertEqual(sorted(self.root.glob(".sky/kb/documents/*/*.md")), revisions)
        self.assertNotEqual(first["run_id"], second["run_id"])

    def test_changed_source_keeps_id_and_creates_revision(self):
        path = self.write("README.md")
        self.init()
        original = self.store.records()[0]["entry"]
        path.write_bytes(b"# Sample\nChanged public content.\n")
        result = self.init()
        changed = self.store.records()[0]["entry"]
        self.assertEqual(result["stored"], ["README.md"])
        self.assertEqual(original["id"], changed["id"])
        self.assertNotEqual(original["digest"], changed["digest"])
        self.assertTrue((self.root / original["path"]).is_file())

    def test_removed_source_is_stale_and_never_deleted(self):
        path = self.write("README.md")
        self.init()
        record_id = self.store.records()[0]["metadata"]["id"]
        path.unlink()
        self.init()
        manifest = self.store.manifest()
        self.assertTrue(manifest["documents"][record_id]["stale"])
        self.assertTrue(manifest["init_sources"]["README.md"]["stale"])
        self.assertTrue((self.root / manifest["documents"][record_id]["path"]).exists())

    def test_returning_source_clears_stale_without_new_revision(self):
        path = self.write("README.md")
        original = path.read_bytes()
        self.init()
        digest = self.store.records()[0]["entry"]["digest"]
        path.unlink()
        self.init()
        path.write_bytes(original)
        self.init()
        entry = self.store.records()[0]["entry"]
        self.assertFalse(entry["stale"])
        self.assertEqual(entry["digest"], digest)

    def test_secret_shaped_content_is_skipped_and_listed(self):
        self.write("docs/secret.md", "# Example\n" + "api_" + "key=" + "q7Zk2pLm9VbT4xRw1sYd")
        result = self.init()
        self.assertEqual(result["stored"], [])
        self.assertIn("redaction", result["skipped"][0]["reason"])
        self.assertEqual(self.store.records(), [])

    def test_binary_file_is_skipped(self):
        path = self.write("docs/binary.md")
        path.write_bytes(b"\xff\x00")
        result = self.init()
        self.assertIn("binary", result["skipped"][0]["reason"])

    def test_over_cap_document_is_skipped(self):
        self.write("docs/large.md", "x" * (MAX_DOCUMENT_CHARS + 1))
        result = self.init()
        self.assertIn("size cap", result["skipped"][0]["reason"])

    def test_missing_added_source_is_listed(self):
        result = self.init(add=["missing.md"])
        self.assertEqual(result["skipped"][0], {"source": "missing.md", "reason": "source absent"})

    def test_source_configuration_overrides_defaults(self):
        self.write("README.md")
        self.write("manual/guide.md")
        self.write(".sky/project.yaml", "managed: true\ncontext:\n  sources: [manual]\n")
        selected, _ = kbinit.enumerate_sources(self.root)
        self.assertEqual(selected, ["manual/guide.md"])

    def test_source_configuration_refuses_escape(self):
        self.write(".sky/project.yaml", 'managed: true\ncontext:\n  sources: ["../elsewhere"]\n')
        from sky.policy import PolicyError
        with self.assertRaises(PolicyError):
            kbinit.enumerate_sources(self.root)

    def test_absent_index_records_no_code_index(self):
        self.write("core/module.py", "pass\n")
        self.init()
        observation = self.store.manifest()["code_coverage"]["observation"]
        self.assertEqual(observation["status"], "no code index")
        self.assertEqual(observation["uncovered"], ["core/"])
        self.assertEqual(observation["covered"], [])

    def code_context(self):
        return context_sources.Context(self.root, {"servers": {"code": {"command": "fake"}},
            "sources": {"code": skygraph_adapter(self.root.name)}})

    def fake_coverage(self, spec, tool, args, **kwargs):
        if tool == "list_repos":
            return {"repos": [{"repo": self.root.name, "branch": "main", "files": 1}]}
        if tool == "repo_summary":
            return {"repo": self.root.name, "files": 1, "indexed": True}
        return {"children": [{"name": "core", "files": 1, "definitions": 1}]}

    def test_index_coverage_records_covered_and_uncovered_modules(self):
        self.write("core/a.py", "pass\n")
        self.write("other/a.py", "pass\n")
        with patch("sky.kbinit.context_sources.load", return_value=self.code_context()):
            self.init(call=self.fake_coverage)
        result = self.store.manifest()["code_coverage"]["observation"]
        self.assertEqual(result["covered"], ["core/"])
        self.assertEqual(result["uncovered"], ["other/"])
        self.assertFalse(result["complete"])

    def test_unreachable_index_is_recorded_as_unavailable(self):
        def failed(*args, **kwargs):
            raise OSError("unreachable")
        with patch("sky.kbinit.context_sources.load", return_value=self.code_context()):
            self.init(call=failed)
        self.assertEqual(self.store.manifest()["code_coverage"]["observation"]["status"], "unavailable")

    def test_repository_not_in_index_is_not_claimed_covered(self):
        result = kbinit.coverage(self.root, self.code_context(), call=lambda *a, **k: {"repos": []})
        self.assertEqual(result["status"], "repository not indexed")
        self.assertEqual(result["covered"], [])

    def test_discover_notice_does_not_create_store_or_run(self):
        with patch("sky.kbinit.recorder.Run.start") as start:
            result = self.init(discover=True)
        self.assertEqual(result["notice"], "codebase discovery lands with SH-088")
        self.assertFalse((self.root / ".sky/kb").exists())
        start.assert_not_called()

    def corpus(self):
        target = self.root / "examples/demo-docs"
        shutil.copytree(CORPUS, target)
        self.init(add=["examples/demo-docs"])
        return kbserve.Server(self.store)

    def test_demo_search_finds_known_phrase_offline(self):
        server = self.corpus()
        hits = server.search("cedar context trail")
        self.assertTrue(any(hit["id"] == "demo-adr-local-context" for hit in hits))
        self.assertEqual(len(self.store.records()), 5)

    def test_demo_graph_follows_adr_relationship(self):
        server = self.corpus()
        hits = server.neighbours("demo-adr-local-context")["hits"]
        self.assertTrue(any(hit["id"] == "demo-design-context" for hit in hits))

    def test_demo_reports_absent_code_and_tickets(self):
        self.corpus()
        context_sources.write_adapter(self.root)
        names = {"search", "neighbours", "decisions_find", "decisions_record", "ingest"}
        rows = context_sources.capabilities(context_sources.load(root=self.root), query=lambda *a, **k: names)
        self.assertEqual(next(row[1] for row in rows if row[0] == "code"), "absent")
        self.assertEqual(next(row[1] for row in rows if row[0] == "tickets"), "absent")

    def test_demo_malformed_adapter_refuses_before_store_write(self):
        self.write(".sky/context.yaml", "servers:\n  broken:\n    args: []\n")
        with self.assertRaises(context_sources.ContextError):
            self.init(add=["examples/demo-docs"])
        self.assertFalse((self.root / ".sky/kb").exists())

    def test_malformed_frontmatter_is_skipped_not_reinterpreted(self):
        self.write("docs/bad.md", "---\ntype: adr\n# missing closing delimiter\n")
        result = self.init()
        self.assertEqual(result["stored"], [])
        self.assertTrue(result["skipped"])


class InitCLI(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        subprocess.run(["git", "init", "-q", str(self.root)], check=True, capture_output=True)
        previous = Path.cwd()
        os.chdir(self.root)
        self.addCleanup(os.chdir, previous)
        self.env = patch.dict(os.environ, {"SKY_STATE_DIR": str(self.root / "state")})
        self.env.start()
        self.addCleanup(self.env.stop)

    def command(self, *arguments):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(list(arguments))
        return code, out.getvalue(), err.getvalue()

    def local(self):
        self.assertEqual(self.command("setup", "init", "--local")[0], 0)

    def test_local_setup_writes_only_project_config_without_remote_calls(self):
        with patch("sky.cli._read_token", side_effect=AssertionError("no token")), patch("sky.setup.init", side_effect=AssertionError("no remote setup")):
            code, out, err = self.command("setup", "init", "--local")
        self.assertEqual((code, err), (0, ""))
        self.assertIn("project.yaml", out)
        body = project.read_mapping(self.root / ".sky/project.yaml")
        self.assertEqual(body, {"managed": True, "project": self.root.name, "context": {}})
        self.assertEqual([p.name for p in (self.root / ".sky").iterdir()], ["project.yaml"])
        self.assertFalse((self.root / "state").exists())

    def test_local_setup_refuses_existing_config_without_force(self):
        self.local()
        path = self.root / ".sky/project.yaml"
        before = path.read_bytes()
        code, _, err = self.command("setup", "init", "--local")
        self.assertEqual(code, 1)
        self.assertIn("--force", err)
        self.assertEqual(path.read_bytes(), before)

    def test_local_setup_force_replaces_only_config(self):
        self.local()
        config = self.root / ".sky/project.yaml"
        config.write_text("managed: false\n", encoding="utf-8")
        unrelated = self.root / ".sky/keep.txt"
        unrelated.write_bytes(b"keep")
        self.assertEqual(self.command("setup", "init", "--local", "--force")[0], 0)
        self.assertTrue(project.read_mapping(config)["managed"])
        self.assertEqual(unrelated.read_bytes(), b"keep")
        self.assertEqual({p.name for p in config.parent.iterdir()}, {"project.yaml", "keep.txt"})

    def test_local_setup_from_subdirectory_uses_git_root(self):
        nested = self.root / "nested"
        nested.mkdir()
        os.chdir(nested)
        self.local()
        self.assertTrue((self.root / ".sky/project.yaml").exists())
        self.assertFalse((nested / ".sky").exists())

    def test_remote_setup_still_requires_profile(self):
        code, _, err = self.command("setup", "init")
        self.assertEqual(code, 2)
        self.assertIn("--profile", err)
        self.assertFalse((self.root / ".sky").exists())

    def test_project_sources_validate_preserve_and_publish(self):
        body = {"managed": True, "project": self.root.name,
                "context": {"sources": ["README.md", "docs"], "max_chars": 1234}}
        self.assertEqual(project.validate_config(body, self.root)["context"], body["context"])
        published = Path(__file__).resolve().parents[2] / "schemas/project.schema.json"
        self.assertEqual(json.loads(published.read_text(encoding="utf-8")), project.schema())

    def test_project_sources_refuse_absolute_parent_and_wrong_types(self):
        from sky.policy import PolicyError
        invalid = ["docs", [True], [""], [str(self.root)], ["C:/elsewhere"], ["../outside"], ["docs/../README.md"], ["docs\\..\\README.md"]]
        for sources in invalid:
            with self.subTest(sources=sources), self.assertRaises(PolicyError):
                project.validate_config({"managed": True, "context": {"sources": sources}}, self.root)

    def test_empty_mapping_literal_parses_but_nonempty_flow_mapping_refuses(self):
        self.assertEqual(yamlish.parse("context: {}\n"), {"context": {}})
        with self.assertRaises(yamlish.YamlishError):
            yamlish.parse("context: {max_chars: 10}\n")

    def test_init_command_counts_and_idempotence(self):
        self.local()
        (self.root / "README.md").write_bytes(b"# Local title\nPublic content.\n")
        code, out, err = self.command("kb", "init")
        self.assertEqual((code, err), (0, ""))
        self.assertIn("stored: 1; unchanged: 0; skipped: 0", out)
        self.assertIn("no code index", out)
        self.assertIn("run record:", out)
        code, out, _ = self.command("kb", "init")
        self.assertEqual(code, 0)
        self.assertIn("stored: 0; unchanged: 1", out)

    def test_init_command_repeated_add_and_skip_reasons(self):
        self.local()
        for name in ("one.md", "two.md"):
            (self.root / name).write_bytes(b"# Public title\nPublic content.\n")
        code, out, err = self.command("kb", "init", "--add", "one.md", "--add", "two.md", "--add", "missing.md")
        self.assertEqual((code, err), (0, ""))
        self.assertIn("stored: 2", out)
        self.assertIn("skipped missing.md: source absent", out)

    def test_init_command_prints_module_coverage(self):
        self.local()
        (self.root / "core").mkdir()
        (self.root / "other").mkdir()
        (self.root / "core/a.py").write_bytes(b"pass\n")
        (self.root / "other/a.py").write_bytes(b"pass\n")
        context = context_sources.Context(self.root, {"servers": {"code": {"command": "fake"}},
                  "sources": {"code": skygraph_adapter(self.root.name)}})
        def code_read(spec, tool, arguments, **kwargs):
            if tool == "list_repos":
                return {"repos": [{"repo": self.root.name, "branch": "main"}]}
            if tool == "repo_summary":
                return {"files": 1}
            return {"children": [{"name": "core", "files": 1}]}
        with patch("sky.kbinit.context_sources.load", return_value=context), patch("sky.kbinit.context_sources.stdio_call", side_effect=code_read):
            code, out, err = self.command("kb", "init")
        self.assertEqual((code, err), (0, ""))
        self.assertIn(f"{self.root.name}: 1 covered, 1 uncovered modules", out)

    def test_init_command_prints_unavailable_index_reason(self):
        self.local()
        context = context_sources.Context(self.root, {"servers": {"code": {"command": "fake"}},
                  "sources": {"code": skygraph_adapter(self.root.name)}})
        with patch("sky.kbinit.context_sources.load", return_value=context), patch("sky.kbinit.context_sources.stdio_call", side_effect=OSError("server unreachable")):
            code, out, err = self.command("kb", "init")
        self.assertEqual((code, err), (0, ""))
        self.assertIn("code index unavailable: server unreachable", out)

    def test_discover_command_only_prints_notice(self):
        code, out, err = self.command("kb", "init", "--discover")
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(out.strip(), kbinit.DISCOVER_NOTICE)
        self.assertFalse((self.root / ".sky").exists())
        self.assertFalse((self.root / "state").exists())

    def test_init_outside_managed_project_refuses(self):
        code, _, err = self.command("kb", "init")
        self.assertEqual(code, 1)
        self.assertIn(".sky/project.yaml", err)

    def test_init_uses_project_source_override(self):
        self.local()
        (self.root / "README.md").write_bytes(b"# Excluded\nNot selected.\n")
        (self.root / "chosen.md").write_bytes(b"# Selected\nPublic content.\n")
        (self.root / ".sky/project.yaml").write_text("managed: true\ncontext:\n  sources: [chosen.md]\n", encoding="utf-8")
        self.assertEqual(self.command("kb", "init")[0], 0)
        self.assertEqual(Store(self.root).records()[0]["metadata"]["title"], "Selected")

    def focus(self):
        context_sources.write_adapter(self.root)
        context = context_sources.load(root=self.root)
        brain = Brain()
        return context, brain

    def test_focus_searches_stored_title_and_reports_query(self):
        self.local()
        (self.root / "README.md").write_bytes(b"# Cedar retrieval\nNo unrelated query word.\n")
        self.command("kb", "init")
        context, brain = self.focus()
        def search(spec, tool, arguments):
            self.assertEqual(arguments["query"], "Cedar retrieval")
            return kbserve.Server(Store(self.root)).search(arguments["query"], k=1)
        with patch("sky.context_sources.stdio_call", side_effect=search):
            probes.probe_local(brain, context, [("search", "ok", "")])
        self.assertEqual(brain.state_of(Part.FOCUS), State.OK)
        self.assertIn("Cedar retrieval", brain.table())
        self.assertIn("1 hit(s)", brain.table())

    def test_empty_focus_reports_no_documents_and_project_query(self):
        self.local()
        context, brain = self.focus()
        with patch("sky.context_sources.stdio_call", return_value=[]) as search:
            probes.probe_local(brain, context, [("search", "ok", "")])
        self.assertEqual(search.call_args.args[2]["query"], self.root.name)
        self.assertIn("no documents yet", brain.table())
        self.assertIn("0 hit(s)", brain.table())

    def test_focus_chooses_most_recent_document_title(self):
        self.local()
        older = self.root / "older.md"
        older.write_bytes(b"# Older title\nPublic content.\n")
        self.command("kb", "init", "--add", "older.md")
        newer = self.root / "newer.md"
        newer.write_bytes(b"# Newer title\nPublic content.\n")
        self.command("kb", "init", "--add", "older.md", "--add", "newer.md")
        context, brain = self.focus()
        with patch("sky.context_sources.stdio_call", return_value=[{"id": "fixture"}]) as search:
            probes.probe_local(brain, context, [("search", "ok", "")])
        self.assertEqual(search.call_args.args[2]["query"], "Newer title")

    def test_nonempty_store_with_no_search_evidence_does_not_pass_focus(self):
        self.local()
        (self.root / "README.md").write_bytes(b"# Cedar\nPublic content.\n")
        self.command("kb", "init")
        context, brain = self.focus()
        with patch("sky.context_sources.stdio_call", return_value=[]):
            probes.probe_local(brain, context, [("search", "ok", "")])
        self.assertEqual(brain.state_of(Part.FOCUS), State.MISSING)
        self.assertNotIn("0 hit(s)", brain.table())


if __name__ == "__main__":
    unittest.main()
