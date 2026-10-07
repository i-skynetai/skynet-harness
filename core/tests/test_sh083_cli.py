"""SH-083 slice 2: local CLI, adapters and observed readiness; no network."""
from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import ExitStack, redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from sky import cli, context_sources, inventory, kbserve, probes, recorder, schemas, yamlish
from sky.kbstore import MAX_DOCUMENT_CHARS, Store, digest
from sky.policy import Policy
from sky.readiness import Brain, Kind, Part, State

SHIPPED = Path(__file__).resolve().parents[2] / "plugin/policy.yaml"


class LocalCLI(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.previous = Path.cwd()
        os.chdir(self.root)
        self.addCleanup(os.chdir, self.previous)
        self.env = patch.dict(os.environ, {"SKY_STATE_DIR": str(self.root / "state")})
        self.env.start()
        self.addCleanup(self.env.stop)
        for key in ("SKY_LAUNCHED", "SKY_RUN_ID", "SKY_RUN_DIR", "SKY_AGENT_ID", "SKY_ROLE", "SKY_TASK", "SKY_KB_NAME", "SKY_POLICY"):
            os.environ.pop(key, None)
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True, capture_output=True)
        (self.root / ".sky").mkdir()
        (self.root / ".sky/project.yaml").write_text("managed: true\n", encoding="utf-8")
        self.store = Store(self.root)

    def policy_fixture(self, *, without_local=False):
        """Render temp copies through the public API; never edit shipped agents."""
        plugin = self.root / ("fixture-nonlocal-plugin" if without_local else "fixture-plugin")
        (plugin / "agents").mkdir(parents=True)
        text = SHIPPED.read_text(encoding="utf-8")
        if without_local:
            for tool in ("search", "neighbours", "decisions_find"):
                text = text.replace(f"    - mcp__sky_kb__{tool}\n", "")
        path = plugin / "policy.yaml"
        path.write_text(text, encoding="utf-8")
        for source in (SHIPPED.parent / "agents").glob("*.md"):
            shutil.copyfile(source, plugin / "agents" / source.name)
        Policy.load(path).render(plugin / "agents")
        return path

    def command(self, *argv, stdin=None):
        out, err = io.StringIO(), io.StringIO()
        with ExitStack() as stack:
            stack.enter_context(redirect_stdout(out))
            stack.enter_context(redirect_stderr(err))
            if stdin is not None:
                stack.enter_context(patch("sys.stdin", io.StringIO(stdin)))
            code = cli.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def run_stamp(self):
        run = recorder.Run.start(role="architect", task="TASK-1", kb="local", agent_id="fixture-agent")
        os.environ.update(SKY_RUN_ID=run.run_id, SKY_RUN_DIR=str(run.directory),
                          SKY_AGENT_ID=run.agent_id, SKY_ROLE=run.role, SKY_TASK=run.task, SKY_KB_NAME=run.kb)
        return run

    def document(self, **changes):
        meta = {"type": "doc", "title": "Project HTTP conventions", "project": "fixture", **changes}
        path = self.root / "input.md"
        path.write_bytes(("---\n" + json.dumps(meta) + "\n---\nUse HTTP clients.\n").encode("utf-8"))
        return path

    def adapter(self):
        context_sources.write_adapter(self.root)
        return context_sources.load(root=self.root)

    def inventory(self, spec, timeout=5):
        return {tool["name"]: {} for tool in kbserve.TOOLS}

    def healthy_host(self):
        stack = ExitStack()
        def hand(brain, host):
            brain.add(Part.SHORT_TERM, State.OK, "fake host version answered")
            brain.add(Part.THINKING, State.OK, "fake host model option answered")
        stack.enter_context(patch("sky.probes.probe_hand", hand))
        stack.enter_context(patch("sky.probes.probe_quality", lambda b, cwd: b.add(Part.QUALITY, State.OK, "fake runner reported zero tests")))
        stack.enter_context(patch("sky.probes.probe_habits", lambda b, h: b.add(Part.HABITS, State.OK, "fake host skills listed")))
        stack.enter_context(patch("sky.context_sources.inventory.query_server", self.inventory))
        stack.enter_context(patch("sky.context_sources.stdio_call", return_value=[]))
        return stack

    def test_serve_handshake_over_fake_stdio_has_only_json_rpc_output(self):
        frames = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-03-26"}},
                  {"jsonrpc": "2.0", "method": "notifications/initialized"},
                  {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}]
        code, out, err = self.command("kb", "serve", stdin="\n".join(map(json.dumps, frames)) + "\n")
        self.assertEqual((code, err), (0, ""))
        responses = [json.loads(line) for line in out.splitlines()]
        self.assertEqual([r["id"] for r in responses], [1, 2])
        self.assertEqual(responses[0]["result"]["serverInfo"]["name"], "sky-kb")
        self.assertIn("search", [t["name"] for t in responses[1]["result"]["tools"]])

    def test_stdio_read_client_initializes_calls_search_and_reaps_child(self):
        class Process:
            def __init__(self):
                self.stdin = io.StringIO()
                self.stdout = io.StringIO(json.dumps({"id": 1, "result": {}}) + "\n" +
                    json.dumps({"id": 2, "result": {"content": [{"type": "text", "text": "[]"}], "isError": False}}) + "\n")
                self.terminated = False
                self.frames = []
            def terminate(self):
                self.frames = [json.loads(line) for line in self.stdin.getvalue().splitlines()]
                self.terminated = True
            def wait(self, timeout=None):
                return 0
        process = Process()
        with patch("sky.context_sources.subprocess.Popen", return_value=process):
            hits = context_sources.stdio_call({"command": "fake-server"}, "search", {"query": "HTTP", "k": 1})
        self.assertEqual(hits, [])
        self.assertTrue(process.terminated)
        self.assertEqual([f["method"] for f in process.frames], ["initialize", "notifications/initialized", "tools/call"])
        self.assertEqual(process.frames[-1]["params"]["name"], "search")
        self.assertTrue(process.stdout.closed)

    def test_stdio_read_client_reports_early_exit_and_reaps_child(self):
        class Process:
            stdin = io.StringIO()
            stdout = io.StringIO("")
            terminated = False
            def terminate(self):
                self.terminated = True
            def wait(self, timeout=None):
                return 0
        process = Process()
        with patch("sky.context_sources.subprocess.Popen", return_value=process):
            with self.assertRaisesRegex(context_sources.ContextError, "exited before answering"):
                context_sources.stdio_call({"command": "fake-server"}, "search", {"query": "HTTP"})
        self.assertTrue(process.terminated)
        self.assertTrue(process.stdout.closed)

    def test_put_refuses_without_runtime_stamp_and_does_not_create_manifest(self):
        # A launched session must not silently fall back to interactive identity.
        os.environ["SKY_LAUNCHED"] = "1"
        path = self.document()
        code, _, err = self.command("kb", "put", str(path))
        self.assertEqual(code, 1)
        self.assertIn("runtime stamp", err)
        self.assertEqual(self.store.manifest()["generation"], 0)

    def test_put_refuses_input_outside_repository_and_records_refusal(self):
        run = self.run_stamp()
        with tempfile.TemporaryDirectory() as outside:
            path = Path(outside) / "input.md"
            path.write_bytes(self.document().read_bytes())
            code, _, err = self.command("kb", "put", str(path))
        self.assertEqual(code, 1)
        self.assertIn("outside repository", err)
        events = [json.loads(line) for line in (run.directory / "events.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(events[-1]["kind"], "run.refused")
        self.assertEqual(events[-1]["operation"], "kb.put")
        self.assertEqual(self.store.manifest()["generation"], 0)

    def test_put_attributes_to_current_run_and_records_committed_digest(self):
        run = self.run_stamp()
        code, out, err = self.command("kb", "put", str(self.document()))
        self.assertEqual((code, err), (0, ""))
        record = self.store.records()[0]
        self.assertEqual(record["metadata"]["sky_run"], run.run_id)
        self.assertEqual(record["metadata"]["sky_agent"], run.agent_id)
        events = [json.loads(line) for line in (run.directory / "events.jsonl").read_text(encoding="utf-8").splitlines()]
        event = events[-1]
        self.assertEqual(event["kind"], "kb.put")
        self.assertEqual(event["run_id"], run.run_id)
        self.assertEqual(event["digest"], record["entry"]["digest"])
        self.assertEqual(event["type"], "doc")
        self.assertEqual(schemas.validate_event(event), [])
        self.assertIn(record["metadata"]["id"], out)
        self.assertEqual([e["kind"] for e in events], ["run.start", "kb.put"])
        self.assertFalse((run.directory / "kb-writes").exists())

    def test_interactive_put_uses_runtime_identity_and_records_one_write(self):
        code, out, err = self.command("kb", "put", str(self.document()))
        self.assertEqual((code, err), (0, ""))
        record = self.store.records()[0]
        self.assertEqual(record["metadata"]["sky_agent"], "runtime")
        self.assertEqual(record["metadata"]["sky_role"], "runtime")
        events = self.root / "state/runs" / record["metadata"]["sky_run"] / "events.jsonl"
        rows = [json.loads(line) for line in events.read_text(encoding="utf-8").splitlines()]
        self.assertEqual([e["kind"] for e in rows], ["run.start", "kb.put", "run.finish"])
        self.assertIn("stored", out)

    def test_put_refuses_stamp_that_disagrees_with_runtime_record(self):
        self.run_stamp()
        os.environ["SKY_AGENT_ID"] = "different-agent"
        code, _, err = self.command("kb", "put", str(self.document()))
        self.assertEqual(code, 1)
        self.assertIn("differs from", err)
        self.assertEqual(self.store.manifest()["generation"], 0)

    def test_put_malformed_yaml_reports_refusal_instead_of_raising(self):
        run = self.run_stamp()
        path = self.document()
        path.write_bytes(b"---\ntitle: [unterminated\n---\nBody\n")
        code, _, err = self.command("kb", "put", str(path))
        self.assertEqual(code, 1)
        self.assertIn("sky kb:", err)
        record = run.directory / "events.jsonl"
        self.assertIn('"kind": "run.refused"', record.read_text(encoding="utf-8"))
        self.assertEqual(self.store.manifest()["generation"], 0)

    def test_put_type_fills_missing_type_and_refuses_conflict(self):
        self.run_stamp()
        path = self.document(type=None)
        code, _, err = self.command("kb", "put", str(path), "--type", "doc")
        self.assertEqual((code, err), (0, ""))
        code, _, err = self.command("kb", "put", str(self.document()), "--type", "adr")
        self.assertEqual(code, 1)
        self.assertIn("conflicts", err)

    def test_plain_markdown_with_type_synthesizes_metadata_and_is_searchable(self):
        path = self.root / "docs/webhooks.md"
        path.parent.mkdir()
        body = "# Webhooks\n\nDeliver callbacks through HTTP.\n"
        path.write_bytes(body.encode("utf-8"))
        code, _, err = self.command("kb", "put", str(path), "--type", "doc")
        self.assertEqual((code, err), (0, ""))
        record = self.store.records()[0]
        meta = record["metadata"]
        self.assertEqual(meta["project"], self.root.name)
        self.assertEqual(meta["source"], "docs/webhooks.md")
        self.assertEqual(meta["id"], "doc-" + digest(self.root.name + "\0docs/webhooks.md")[:24])
        self.assertEqual((meta["title"], meta["type"], meta["schema_version"]), ("Webhooks", "doc", 1))
        self.assertEqual(meta["sky_agent"], "runtime")
        self.assertEqual(record["body"], body)
        code, out, err = self.command("kb", "search", "callbacks")
        self.assertEqual((code, err), (0, ""))
        self.assertIn("id:" + meta["id"], out)

    def test_real_cli_put_search_show_work_with_no_local_store_directory(self):
        # A nested project also exercises the longer paths used by real
        # checkouts, rather than only the short top-level temporary fixture.
        root = self.root / ("managed-project-" + "x" * 45)
        (root / ".sky").mkdir(parents=True)
        (root / ".sky/project.yaml").write_text("managed: true\n", encoding="utf-8")
        subprocess.run(["git", "init", "-q"], cwd=root, check=True, capture_output=True)
        self.assertFalse((root / ".sky/kb").exists())
        path = root / "docs/webhooks.md"
        path.parent.mkdir()
        body = "# Webhooks\n\nDeliver callbacks through HTTP.\n"
        path.write_bytes(body.encode("utf-8"))
        env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1])}

        def command(*argv):
            result = subprocess.run([sys.executable, "-m", "sky", *argv], cwd=root,
                env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            return result.stdout

        output = command("kb", "put", "docs/webhooks.md", "--type", "doc")
        manifest = json.loads((root / ".sky/kb/manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(len(manifest["documents"]), 1)
        id, entry = next(iter(manifest["documents"].items()))
        revision = root / entry["path"]
        self.assertTrue(revision.parent.is_dir())
        self.assertTrue(revision.is_file())
        self.assertEqual(list(revision.parent.glob(".tmp-*")), [])
        self.assertIn("stored " + id, output)
        self.assertIn("id:" + id, command("kb", "search", "callbacks"))
        self.assertIn(body, command("kb", "show", id))

    def test_plain_markdown_without_type_is_refused_with_type_guidance(self):
        path = self.root / "plain.md"
        path.write_bytes(b"# Webhooks\n\nHTTP callbacks.\n")
        code, _, err = self.command("kb", "put", str(path))
        self.assertEqual(code, 1)
        self.assertIn("--type", err)
        self.assertEqual(self.store.manifest()["generation"], 0)

    def test_frontmatter_with_type_keeps_strict_validation(self):
        path = self.document(schema_version=2)
        code, _, err = self.command("kb", "put", str(path), "--type", "doc")
        self.assertEqual(code, 1)
        self.assertIn("unsupported document schema version", err)
        self.assertEqual(self.store.manifest()["generation"], 0)
        path.write_bytes(b"---\ntitle: [unterminated\n---\nBody\n")
        code, _, err = self.command("kb", "put", str(path), "--type", "doc")
        self.assertEqual(code, 1)
        self.assertIn("sky kb:", err)
        self.assertEqual(self.store.manifest()["generation"], 0)

    def test_plain_markdown_without_h1_uses_filename_and_retains_id_on_update(self):
        path = self.root / "conventions.md"
        path.write_bytes(b"## Details\n\nHTTP callbacks.\n")
        self.assertEqual(self.command("kb", "put", str(path), "--type", "doc")[0], 0)
        first = self.store.records()[0]
        self.assertEqual(first["metadata"]["title"], "conventions.md")
        path.write_bytes(b"# Updated conventions\n\nHTTP clients.\n")
        self.assertEqual(self.command("kb", "put", str(path), "--type", "doc")[0], 0)
        second = self.store.records()[0]
        self.assertEqual(second["metadata"]["id"], first["metadata"]["id"])
        self.assertEqual(second["metadata"]["title"], "Updated conventions")

    def test_plain_markdown_binary_content_is_refused(self):
        path = self.root / "binary.md"
        for content in (b"\xff\xfe", b"# Title\n\x00binary"):
            with self.subTest(content=content):
                path.write_bytes(content)
                code, _, err = self.command("kb", "put", str(path), "--type", "doc")
                self.assertEqual(code, 1)
                self.assertIn("binary", err)
                self.assertEqual(self.store.manifest()["generation"], 0)

    def test_plain_markdown_over_size_cap_is_refused(self):
        path = self.root / "large.md"
        path.write_bytes(b"x" * (MAX_DOCUMENT_CHARS + 1))
        code, _, err = self.command("kb", "put", str(path), "--type", "doc")
        self.assertEqual(code, 1)
        self.assertIn("size cap", err)
        self.assertEqual(self.store.manifest()["generation"], 0)

    def test_plain_markdown_still_passes_through_redaction_gate(self):
        path = self.root / "redacted.md"
        path.write_bytes(("# Token\n\nghp_" + "A" * 35).encode("utf-8"))
        code, _, err = self.command("kb", "put", str(path), "--type", "doc")
        self.assertEqual(code, 1)
        self.assertIn("redaction gate", err)
        self.assertEqual(self.store.manifest()["generation"], 0)

    def test_show_and_search_print_document_and_citation(self):
        self.run_stamp()
        self.assertEqual(self.command("kb", "put", str(self.document()))[0], 0)
        id = self.store.records()[0]["metadata"]["id"]
        code, out, err = self.command("kb", "show", id)
        self.assertEqual((code, err), (0, ""))
        self.assertIn("Use HTTP clients.", out)
        code, out, err = self.command("kb", "search", "HTTP", "-k", "1")
        self.assertEqual((code, err), (0, ""))
        self.assertIn("id:" + id, out)
        self.assertIn("1 hit(s)", out)

    def test_search_refuses_unbounded_k(self):
        code, _, err = self.command("kb", "search", "HTTP", "-k", "101")
        self.assertEqual(code, 1)
        self.assertIn("1 and 100", err)

    def test_adapter_is_deterministic_and_names_installed_interpreter_and_root(self):
        code, _, err = self.command("kb", "serve", "--write-adapter")
        self.assertEqual((code, err), (0, ""))
        path = self.root / ".sky/context.yaml"
        first = path.read_bytes()
        self.assertEqual(self.command("kb", "serve", "--write-adapter")[0], 0)
        self.assertEqual(path.read_bytes(), first)
        body = yamlish.parse(first.decode("utf-8"))
        self.assertEqual(body["servers"]["sky_kb"]["command"], sys.executable)
        self.assertEqual(body["servers"]["sky_kb"]["args"][-2:], ["--root", str(self.root)])
        self.assertEqual(body["sources"]["local"]["decisions.find"]["tool"], "decisions_find")

    def test_adapter_preserves_other_servers_and_sources(self):
        path = self.root / ".sky/context.yaml"
        path.write_text("servers:\n  external:\n    command: fake\nsources:\n  external:\n    server: external\n    code.search:\n      tool: code_search\n", encoding="utf-8")
        self.adapter()
        self.assertEqual(context_sources.load(root=self.root).sources["external"]["code.search"]["tool"], "code_search")

    def test_inventory_discovers_local_adapter_and_its_real_tool_names(self):
        self.adapter()
        servers = inventory.configured_servers(self.root, kb_map=self.root / "missing-map.json")
        self.assertIn("sky_kb", servers)
        self.assertEqual(servers["sky_kb"]["args"][-2:], ["--root", str(self.root)])
        observed = {"servers": {"sky_kb": {"tools": inventory.tool_metadata(kbserve.TOOLS)}}}
        names = inventory.provided_tools(observed)
        for tool in ("search", "neighbours", "decisions_find"):
            self.assertIn("mcp__sky_kb__" + tool, names)

    def test_adapter_refuses_reserved_name_collision_without_writing(self):
        path = self.root / ".sky/context.yaml"
        path.write_text("servers:\n  sky_kb:\n    command: other-server\n", encoding="utf-8")
        old = path.read_bytes()
        code, _, err = self.command("kb", "serve", "--write-adapter")
        self.assertEqual(code, 1)
        self.assertIn("owned by another", err)
        self.assertEqual(path.read_bytes(), old)

    def test_capability_rows_are_ok_missing_and_absent_with_first_missing_tool(self):
        context = self.adapter()
        def query(spec, timeout):
            return {"search": {}, "neighbours": {}, "decisions_find": {}}
        brain = Brain()
        probes.probe_context(brain, context, context_sources.capabilities(context, query=query))
        rows = {o.name: o for o in brain.observations}
        self.assertIs(rows["search"].state, State.OK)
        self.assertIs(rows["code"].state, State.ABSENT)
        self.assertIs(rows["tickets"].state, State.ABSENT)
        self.assertIs(rows["decisions"].state, State.MISSING)
        self.assertIn("decisions_record", rows["decisions"].detail)
        self.assertIs(rows["ingest"].state, State.MISSING)
        self.assertIn("ingest", rows["ingest"].detail)

    def test_capability_inventory_queries_each_server_once_with_timeout(self):
        context = self.adapter()
        calls = []
        def query(spec, timeout):
            calls.append(timeout)
            return self.inventory(spec)
        rows = context_sources.capabilities(context, query=query, timeout=2)
        self.assertEqual(calls, [2])
        self.assertEqual(sum(state == "ok" for _, state, _ in rows), 4)

    def test_unreachable_capability_server_reports_missing(self):
        context = self.adapter()
        def query(spec, timeout):
            raise subprocess.TimeoutExpired("fake-server", timeout)
        rows = context_sources.capabilities(context, query=query)
        search = next(r for r in rows if r[0] == "search")
        self.assertEqual(search[1], "MISSING")
        self.assertIn("unreachable", search[2])

    def test_doctor_with_local_adapter_needs_no_kb_map(self):
        self.adapter()
        policy = self.policy_fixture()
        with self.healthy_host(), patch("sky.cli._load_map", side_effect=AssertionError("remote map must not be read")):
            code, out, err = self.command("--policy", str(policy), "doctor")
        self.assertEqual((code, err), (0, ""))
        self.assertIn("KB local", out)
        self.assertRegex(out, r"search\s+ok")
        self.assertRegex(out, r"code\s+absent")
        self.assertRegex(out, r"tickets\s+absent")
        self.assertIn("no documents yet", out)

    def test_reviewer_dry_run_passes_offline_with_local_adapter(self):
        self.adapter()
        policy = self.policy_fixture()
        with patch.dict(os.environ, {"SKY_PLUGIN_ROOT": str(policy.parent)}), \
                patch("sky.policy.CONFIG_POLICY", str(self.root / "absent-policy.yaml")), \
                self.healthy_host(), patch("sky.cli._load_map", side_effect=AssertionError("no remote map")), \
                patch("sky.launcher.prove_git_blocked", return_value=(True, "fake git block proven")), \
                patch("sky.hand.run", side_effect=AssertionError("dry-run must not launch")):
            # Existing managed-policy admission is retained: render the registry,
            # then exercise the effective policy rather than an explicit bypass.
            Policy.load().render()
            code, out, err = self.command("build", "--dry-run", "--role", "reviewer")
        self.assertEqual((code, err), (0, ""))
        self.assertIn("--dry-run", out)
        self.assertIn("local MCP grants", out)
        configs = list((self.root / "state/runs").glob("*/mcp.json"))
        self.assertEqual(len(configs), 1)
        spec = json.loads(configs[0].read_text(encoding="utf-8"))["mcpServers"]["sky_kb"]
        self.assertEqual(spec["command"], sys.executable)
        self.assertNotIn("url", spec)

    def test_local_adapter_does_not_bypass_missing_effective_registry(self):
        self.adapter()
        policy = self.policy_fixture()
        with patch.dict(os.environ, {"SKY_PLUGIN_ROOT": str(policy.parent)}), \
                patch("sky.policy.CONFIG_POLICY", str(self.root / "absent-policy.yaml")), self.healthy_host():
            code, _, err = self.command("build", "--dry-run", "--role", "reviewer")
        self.assertEqual(code, 1)
        self.assertIn("registry is missing or stale", err)

    def test_actual_local_launch_refuses_when_role_does_not_grant_local_tools(self):
        self.adapter()
        policy = self.policy_fixture(without_local=True)
        with self.healthy_host(), patch("sky.launcher.prove_git_blocked", return_value=(True, "fake proven block")), \
                patch("sky.hand.run", side_effect=AssertionError("ungranted local tools must not launch")):
            code, _, err = self.command("--policy", str(policy), "build", "--role", "reviewer")
        self.assertEqual(code, 1)
        self.assertIn("mcp__sky_kb__search", err)
        self.assertIn("not granted to reviewer", err)

    def test_rendered_local_read_grants_allow_the_reviewer_hand_to_start(self):
        self.adapter()
        policy = self.policy_fixture()
        result = cli.hand.Result(ok=True, reason="finished", exit_code=0,
                                 log=self.root / "fake.log", seconds=0)
        with self.healthy_host(), patch("sky.launcher.prove_git_blocked", return_value=(True, "fake proven block")), \
                patch("sky.hand.run", return_value=result) as start:
            code, out, err = self.command("--policy", str(policy), "build", "--role", "reviewer")
        self.assertEqual((code, err), (0, ""))
        start.assert_called_once()
        self.assertIn("starting claude as reviewer", out)

    def test_shipped_policy_grants_local_reads_but_no_local_write_tools(self):
        policy = Policy.load(SHIPPED)
        for role in policy.roles_named():
            with self.subTest(role=role):
                tools = policy.tools_for(role)
                for tool in ("search", "neighbours", "decisions_find"):
                    self.assertIn(f"mcp__sky_kb__{tool}", tools)
                    self.assertEqual(policy.binding(f"mcp__sky_kb__{tool}"), "kb.read")
                self.assertNotIn("mcp__sky_kb__ingest", tools)
                self.assertNotIn("mcp__sky_kb__decisions_record", tools)

    def test_published_run_event_kinds_include_kb_put_and_match_core(self):
        path = Path(__file__).resolve().parents[2] / "schemas/run-event.schema.json"
        published = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(published["x-known-kinds"], list(schemas.EVENT_KINDS))
        self.assertIn("kb.put", schemas.EVENT_KINDS)

    def test_commands_refuse_outside_managed_project_with_config_name(self):
        (self.root / ".sky/project.yaml").unlink()
        for argv in (("serve",), ("put", "input.md"), ("show", "missing"), ("search", "query")):
            with self.subTest(command=argv[0]):
                code, _, err = self.command("kb", *argv)
                self.assertEqual(code, 1)
                self.assertIn(".sky/project.yaml", err)

    def test_explicit_root_allows_unmanaged_project(self):
        (self.root / ".sky/project.yaml").unlink()
        code, out, err = self.command("kb", "search", "query", "--root", str(self.root))
        self.assertEqual((code, err), (0, ""))
        self.assertIn("0 hit(s)", out)

    def test_subdirectory_resolves_project_root(self):
        (self.root / "sub").mkdir()
        os.chdir(self.root / "sub")
        self.assertEqual(context_sources.repository(), self.root)

    def test_invalid_present_project_config_refuses_without_fallback(self):
        (self.root / ".sky/project.yaml").write_text("managed: true\nunknown: value\n", encoding="utf-8")
        code, _, err = self.command("kb", "search", "query")
        self.assertEqual(code, 1)
        self.assertIn("unknown keys", err)

    def test_git_root_failure_does_not_fall_back_to_remote_kb_map(self):
        with self.healthy_host(), patch("sky.context_sources.project.git_root", return_value=None), \
                patch("sky.cli._load_map", side_effect=AssertionError("invalid present project must not fall back")):
            code, _, err = self.command("doctor")
        self.assertEqual(code, 1)
        self.assertIn(".sky/project.yaml", err)

    def test_missing_mapped_tool_blocks_local_reviewer_readiness(self):
        context = self.adapter()
        with self.healthy_host(), patch("sky.context_sources.inventory.query_server", return_value={}):
            brain = probes.run_all(context_sources.local_kb(context), policy=Policy.load(SHIPPED), cwd=self.root)
        self.assertFalse(brain.ready_for(Kind.REVIEW))
        self.assertIs(brain.state_of(Part.KNOWLEDGE), State.MISSING)

    def test_local_search_error_is_down_not_a_success(self):
        context = self.adapter()
        with self.healthy_host(), patch("sky.context_sources.stdio_call", side_effect=ValueError("bad local response")):
            brain = probes.run_all(context_sources.local_kb(context), policy=Policy.load(SHIPPED), cwd=self.root)
        self.assertIs(brain.state_of(Part.FOCUS), State.DOWN)
        self.assertFalse(brain.ready_for(Kind.REVIEW))


if __name__ == "__main__":
    unittest.main()
