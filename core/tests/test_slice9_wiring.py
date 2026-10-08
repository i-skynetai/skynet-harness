"""CLI/runtime wiring for the tested slice-9 pure modules; no live transports."""
import copy
import io
import json
import os
import tempfile
import unittest
from contextlib import ExitStack, redirect_stdout, redirect_stderr
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from sky import budget, cli, context_sources, ingest, ingestcommands, launcher, project, recorder, schemas, workflows
from sky.kbserve import Server
from sky.kbstore import Store, StoreError, document_text
from sky.policy import Policy, PolicyError

REPO = Path(__file__).resolve().parents[2]


class Wiring(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        previous = Path.cwd()
        os.chdir(self.root)
        self.addCleanup(os.chdir, previous)
        self.environment = patch.dict(os.environ, {"SKY_STATE_DIR": str(self.root / "state")}, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        (self.root / ".sky").mkdir()
        self.configure()
        self.store = Store(self.root)
        self.run = recorder.Run.start(role="runtime", task="cache", kb="local", agent_id="runtime")
        self.policy = Policy.load(REPO / "plugin/policy.yaml")
        self.context = context_sources.Context(self.root, {"servers": {"sky_kb": {"command": "fake"}},
            "sources": {"local": {"server": "sky_kb", "search.keyword": {"tool": "search"}}}})
        item = patch("sky.project.git_root", return_value=self.root)
        item.start()
        self.addCleanup(item.stop)

    def configure(self, tokens=None):
        text = "managed: true\n"
        if tokens is not None:
            text += f"context:\n  max_tokens: {tokens}\n"
        (self.root / ".sky/project.yaml").write_bytes(text.encode())

    def command(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def events(self):
        return [json.loads(line) for path in (self.root / "state/runs").glob("*/events.jsonl")
                for line in path.read_text(encoding="utf-8").splitlines()]

    def healthy(self):
        stack = ExitStack()
        stack.enter_context(patch("sky.cli._load_policy", return_value=self.policy))
        stack.enter_context(patch("sky.cli._resolve_kb", return_value=(SimpleNamespace(catalogue=lambda: None),
                            SimpleNamespace(name="local", code_url=""), None)))
        stack.enter_context(patch("sky.cli.check_definition", return_value=self.root / "agent.md"))
        stack.enter_context(patch("sky.probes.run_all", return_value=Mock(blockers=lambda kind: [])))
        stack.enter_context(patch("sky.launcher.build_env", return_value=Mock(variables={})))
        stack.enter_context(patch("sky.launcher.prove_git_blocked", return_value=(True, "fixture")))
        stack.enter_context(patch("sky.launcher.write_mcp_config", return_value=self.root / "mcp.json"))
        stack.enter_context(patch("sky.launcher.hand_command", return_value=["fake-hand"]))
        stack.enter_context(patch("sky.launcher.start_hand", side_effect=AssertionError("dry-run must not execute")))
        return stack

    def handover(self):
        source = self.root / "handover.md"
        source.write_bytes(document_text({"type": "handover", "title": "Cache handover", **self.run.stamp()},
                                        "Public cache evidence.\n").encode())
        engine = {"name": "remote-kb", "tenant": "public-demo"}
        path = ingest.seal(self.root, "handover.md", engine=engine, stamp=self.run.stamp(), run=self.run)
        return source, path.relative_to(self.root).as_posix(), engine

    def test_workflow_cli_gate_stops_before_developer_and_records_verdict(self):
        called = []
        def build(args):
            called.append(args.role)
            args._summary = {"result_text": "Finding with evidence\nVERDICT: BLOCKED"}
            return 0
        with patch("sky.cli._load_policy", return_value=self.policy), patch("sky.context_sources.load", return_value=self.context), \
             patch("sky.context_sources.call", return_value=[]), patch("sky.cli.cmd_build", side_effect=build):
            code, out, err = self.command("workflow", "run", "feature", "--task", "cache")
        self.assertEqual(code, 1)
        self.assertEqual(called, ["architect"])
        self.assertIn("stopped at architect", out)
        self.assertTrue(any(row["kind"] == "workflow.step" and row.get("verdict") == "BLOCKED" for row in self.events()))

    def test_workflow_cli_approved_gates_ship_only_prints_and_skips_absent(self):
        called = []
        def build(args):
            called.append(args.role)
            args._summary = {"result_text": "Citations inspected\nVERDICT: APPROVED"}
            return 0
        with patch("sky.cli._load_policy", return_value=self.policy), patch("sky.context_sources.load", return_value=self.context), \
             patch("sky.context_sources.call", return_value=[]), patch("sky.cli.cmd_build", side_effect=build), \
             patch("sky.cli.cmd_ship", side_effect=AssertionError("ship cannot execute")):
            code, out, err = self.command("workflow", "run", "feature", "--task", "cache")
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(called, ["architect", "developer", "reviewer", "security"])
        self.assertIn("tickets absent", out)
        self.assertIn("prs absent", out)
        self.assertIn("sky ship", out)
        rows = [r for r in self.events() if r["kind"] == "workflow.step"]
        self.assertEqual(len(rows), len(workflows.FEATURE))
        self.assertEqual(rows[-1]["status"], "printed")

    def test_workflow_dry_run_developer_requires_admission(self):
        with self.healthy(), patch("sky.context_sources.load", return_value=self.context), \
             patch("sky.context_sources.call", return_value=[]):
            code, out, err = self.command("workflow", "run", "feature", "--task", "cache", "--dry-run")
        self.assertEqual(code, 1)
        self.assertIn("no admitted plan", err)
        self.assertIn("stopped at developer", out)

    def test_workflow_unknown_name_refused_before_step(self):
        with patch("sky.cli._load_policy", return_value=self.policy), patch("sky.cli.cmd_build") as build:
            code, out, _ = self.command("workflow", "run", "absent", "--task", "cache")
        self.assertEqual(code, 1)
        self.assertIn("unknown workflow", out)
        build.assert_not_called()

    def test_route_goal_selects_rule_and_uses_build(self):
        with patch("sky.cli._load_policy", return_value=self.policy), patch("sky.cli.cmd_build", return_value=0) as build:
            code, out, err = self.command("route", "review cache", "--dry-run")
        self.assertEqual((code, err), (0, ""))
        self.assertIn("rule review", out)
        self.assertEqual(build.call_args.args[0].role, "reviewer")
        self.assertEqual(build.call_args.args[0].task, "review cache")

    def test_route_workflow_selection_uses_workflow_runner(self):
        with patch("sky.cli._load_policy", return_value=self.policy), patch("sky.workflowcommands.execute", return_value=0) as run:
            code, out, _ = self.command("route", "implement cache", "--dry-run")
        self.assertEqual(code, 0)
        self.assertIn("rule feature", out)
        self.assertEqual(run.call_args.args[0].workflow_name, "feature")

    def test_route_ambiguous_or_missing_asks_and_runs_nothing(self):
        for goal in ("review feature", "unmatched request"):
            with self.subTest(goal=goal), patch("sky.cli._load_policy", return_value=self.policy), patch("sky.cli.cmd_build") as build:
                code, out, _ = self.command("route", goal)
            self.assertEqual(code, 2)
            self.assertIn("choice", out)
            build.assert_not_called()

    def test_route_explicit_role_preserves_existing_governed_build(self):
        with self.healthy():
            code, out, err = self.command("route", "--role", "reviewer", "--task", "cache", "--dry-run")
        self.assertEqual((code, err), (0, ""))
        self.assertIn("--dry-run", out)

    def test_policy_lint_refuses_sessions_with_future_resolver_message(self):
        body = copy.deepcopy(self.policy.body)
        body["workflows"] = {"session": [{"id": "remote", "session": "unresolved", "optional": True}]}
        with self.assertRaisesRegex(PolicyError, "remote.*named sessions arrive with SH-070/071"):
            Policy.from_dict(body)

    def test_policy_lint_refuses_unknown_hand_outward_step_and_routing_target(self):
        for change in ({"workflows": {"bad": [{"id": "bad-hand", "hand": "unmeasured"}]}},
                       {"workflows": {"bad": [{"id": "publish", "operation": "push"}]}},
                       {"routing": {"bad": {"contains": ["x"], "agent": "absent"}}}):
            body = copy.deepcopy(self.policy.body)
            body.update(change)
            with self.assertRaises(PolicyError):
                Policy.from_dict(body)

    def test_project_positive_max_tokens_preserved_and_schema_matches(self):
        self.assertEqual(project.validate_config({"managed": True, "context": {"max_tokens": 27}}, self.root)["context"]["max_tokens"], 27)
        for cap in (0, -1, True, "100"):
            with self.assertRaises(PolicyError):
                project.validate_config({"managed": True, "context": {"max_tokens": cap}}, self.root)
        self.assertEqual(project.schema(), json.loads((REPO / "schemas/project.schema.json").read_text(encoding="utf-8")))

    def test_local_mcp_pack_refused_before_delivery_when_over_cap(self):
        self.store.put({"title": "Cache", "type": "doc", "project": self.root.name, "source": "docs/cache.md"}, "cache " * 30, stamp=self.run.stamp())
        self.configure(1)
        server = Server(self.store)
        reply = server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                               "params": {"name": "search", "arguments": {"query": "cache"}}})
        self.assertTrue(reply["result"]["isError"])
        self.assertIn("nothing delivered", reply["result"]["content"][0]["text"])
        self.assertEqual(server.delivered_characters, 0)

    def test_local_mcp_cumulative_budget_blocks_second_pack(self):
        self.configure(1)
        server = Server(self.store)
        self.assertEqual(server.bounded("aa"), "aa")  # JSON text itself is 2 chars, not quoted.
        with self.assertRaises(StoreError):
            server.bounded("bbb")
        self.assertEqual(server.delivered_characters, 2)

    def test_context_sources_cap_runtime_pack_and_explain_remote_limit(self):
        self.configure(1)
        with self.assertRaisesRegex(context_sources.ContextError, "remote MCP responses are measured, not capped"):
            context_sources.deliver(self.context, "12345", task_id="cache")
        self.assertEqual(context_sources.deliver(self.context, "1234", task_id="cache")["pack"], "1234")

    def test_budget_cli_approval_retries_exact_task_pack_only(self):
        self.configure(1)
        self.assertFalse(budget.deliver(self.root, "12345678", task_id="cache")["delivered"])
        with patch("builtins.input", return_value="y"):
            code, out, err = self.command("budget", "approve", "--task", "cache", "--tokens", "2")
        self.assertEqual((code, err), (0, ""))
        self.assertIn("estimated tokens", out)
        self.assertTrue(budget.deliver(self.root, "12345678", task_id="cache")["delivered"])
        self.assertFalse(budget.deliver(self.root, "abcdefgh", task_id="cache")["delivered"])
        self.assertFalse(budget.deliver(self.root, "12345678", task_id="another")["delivered"])
        self.assertTrue(any(row["kind"] == "context.budget_approved" for row in self.events()))

    def test_budget_cli_human_only_and_confirmation_refusal(self):
        self.configure(1)
        budget.deliver(self.root, "12345678", task_id="cache")
        with patch.dict(os.environ, {"SKY_LAUNCHED": "1"}), patch("builtins.input") as prompt:
            code, _, err = self.command("budget", "approve", "--task", "cache", "--tokens", "2")
        self.assertEqual(code, 1)
        self.assertIn("person", err)
        prompt.assert_not_called()
        with patch("builtins.input", return_value="n"):
            self.assertEqual(self.command("budget", "approve", "--task", "cache", "--tokens", "2")[0], 1)
        self.assertFalse(budget.task_path(self.store, "cache", "approval").exists())

    def test_launcher_context_budget_refusal_precedes_admission_consumption(self):
        from sky import admission
        with self.healthy(), patch("sky.launcher.check_admission", return_value={"plan_id": "plan-a", "token": "private"}) as check, \
             patch("sky.launcher.context_pack", side_effect=context_sources.ContextError("context over budget")):
            code, out, err = self.command("build", "--role", "developer", "--task", "cache", "--dry-run")
        self.assertEqual(code, 1)
        self.assertIn("context over budget", err)
        self.assertEqual(check.call_count, 1)
        self.assertFalse(check.call_args.kwargs["consume"])
        self.assertTrue(any(row["kind"] == admission.EVENTS["refuse"] for row in self.events()))

    def test_launcher_context_pack_contains_local_evidence_and_remote_limit(self):
        self.store.put({"title": "Cache", "type": "doc", "project": self.root.name, "source": "docs/cache.md"}, "Known cache evidence.", stamp=self.run.stamp())
        pack = launcher.context_pack(self.context, "cache", role="reviewer", hand="claude", policy=self.policy)
        self.assertIn("Known cache evidence", pack)
        self.configure(1)
        with self.assertRaises(ValueError):
            launcher.context_pack(self.context, "cache", role="reviewer", hand="claude", policy=self.policy)

    def test_ingest_cli_confirmed_fake_transport_and_ship_listing(self):
        source, file, engine = self.handover()
        original = source.read_bytes()
        with patch("sky.ingestcommands.transport", return_value=Mock(return_value={"ok": True})) as factory, \
             patch("builtins.input", return_value="y"):
            code, out, err = self.command("ingest", file)
        self.assertEqual((code, err), (0, ""))
        self.assertIn("payload digest", out)
        self.assertEqual(source.read_bytes(), original)
        self.assertEqual(factory.return_value.call_args.args[0], engine)
        self.assertTrue(json.loads((self.root / file).read_text(encoding="utf-8"))["executed"])
        self.assertEqual(self.command("ship")[1].strip(), "nothing pending.")

    def test_ingest_cli_confirmation_refusal_and_agent_refusal_keep_local(self):
        source, file, _ = self.handover()
        for agent in (False, True):
            with self.subTest(agent=agent), patch.dict(os.environ, {"SKY_LAUNCHED": "1"} if agent else {}), \
                 patch("builtins.input", return_value="n"), patch("sky.ingestcommands.transport", return_value=Mock()) as factory:
                code, _, err = self.command("ingest", file)
            self.assertEqual(code, 1)
            self.assertIn("person" if agent else "confirmation refused", err)
            factory.return_value.assert_not_called()
            self.assertTrue(source.exists())
        self.assertTrue(any(row["kind"] == "kb.ingest_refused" for row in self.events()))

    def test_ship_lists_ingest_command_and_never_calls_transport(self):
        _, file, _ = self.handover()
        with patch("sky.ingestcommands.transport", side_effect=AssertionError("ship prints only")):
            code, out, err = self.command("ship")
        self.assertEqual((code, err), (0, ""))
        self.assertIn("run: sky ingest " + file, out)

    def test_put_handover_seals_stamped_revision_for_configured_engine(self):
        (self.root / "handover.md").write_bytes(b"# Cache handover\n\nPublic cache evidence.\n")
        engine = {"name": "remote-kb", "tenant": "public-demo"}
        with patch("sky.ingestcommands.remote", return_value=(engine, None)):
            code, out, err = self.command("kb", "put", "handover.md", "--type", "handover")
        self.assertEqual((code, err), (0, ""))
        paths = ingestcommands.pending(self.root)
        self.assertEqual(len(paths), 1)
        intent = json.loads(paths[0].read_text(encoding="utf-8"))
        self.assertEqual(intent["stamp"]["sky_agent"], "runtime")
        self.assertTrue((self.root / intent["source"]).exists())
        self.assertIn("sky ingest", out)

    def test_put_handover_without_remote_makes_no_intent(self):
        (self.root / "handover.md").write_bytes(b"# Cache handover\n\nPublic cache evidence.\n")
        with patch("sky.ingestcommands.remote", return_value=(None, None)):
            code, _, err = self.command("kb", "put", "handover.md", "--type", "handover")
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(ingestcommands.pending(self.root), [])
        self.assertTrue(self.store.records())

    def test_ingest_published_schema_and_events_match_runtime(self):
        published = json.loads((REPO / "schemas/ingest-intent.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(published, schemas.json_schema(ingest.INGEST_INTENT))
        self.assertEqual(json.loads((REPO / "schemas/run-event.schema.json").read_text(encoding="utf-8")),
                         schemas.json_schema(schemas.RUN_EVENT))
        for kind in ("workflow.step", "context.budget_approved", "kb.ingest_approved", "kb.ingest_refused", "kb.ingest_executed"):
            self.assertIn(kind, schemas.EVENT_KINDS)

    def test_shipped_workflow_does_not_change_role_tool_sets(self):
        for role in self.policy.roles_named():
            header = (REPO / "plugin/agents" / (role + ".md")).read_text(encoding="utf-8").split("---")[1]
            line = next(line for line in header.splitlines() if line.startswith("tools:"))
            self.assertEqual(line.removeprefix("tools:").strip(), ", ".join(self.policy.tools_for(role)))

    def test_native_codex_dispatch_keeps_original_environment_and_adapter(self):
        environment = {"SKY_RUN_ID": self.run.run_id, "SKY_RUN_DIR": str(self.run.directory)}
        with patch("sky.codexhost.execute", return_value="result") as adapter, \
             patch("sky.hand.run", side_effect=AssertionError("native run cannot use legacy hand")):
            result = launcher.start_hand("codex", ["codex", "--sky-governed"], env=environment,
                                         cwd=self.root, log_path=self.run.directory / "hand.log")
        self.assertEqual(result, "result")
        self.assertIs(adapter.call_args.kwargs["env"], environment)
        self.assertEqual(adapter.call_args.kwargs["cwd"], self.root)

    def test_codex_exact_briefing_approval_and_seeded_context_count(self):
        from sky import codexcontroller
        self.configure(10)
        effective = SimpleNamespace(root=self.root, config={"context": {"max_tokens": 10}})
        with patch("sky.codexcontroller.procedures", return_value="x" * 200):
            with self.assertRaisesRegex(codexcontroller.Refused, "over budget"):
                codexcontroller.prepare_context(effective, "developer", "cache", package=self.root)
            pending = json.loads(budget.task_path(self.store, "cache", "pending").read_text())
            self.assertEqual(pending["task_id"], "cache")
            budget.approve_pending(self.root, task_id="cache", max_tokens=1000,
                                   run=self.run, confirm=lambda _: True, env={})
            hits, prompt = codexcontroller.prepare_context(effective, "developer", "cache", package=self.root)
        self.assertIn("x" * 200, prompt)
        self.assertEqual(hits, [])
        server = Server(self.store, task_id="cache", characters_before=len(prompt))
        self.assertEqual(server.task_id, "cache")
        self.assertEqual(server.delivered_characters, len(prompt))
        with self.assertRaisesRegex(StoreError, "over budget"):
            server.bounded("new unapproved context")
        pending = json.loads(budget.task_path(self.store, "cache", "pending").read_text())
        self.assertEqual(pending["manifest"]["measured_characters"], len(prompt) + len("new unapproved context"))

    def test_ingest_adapter_translates_argument_names(self):
        engine = {"name": "remote-kb", "tenant": "public-demo"}
        source = {"server": "remote", "ingest.document": {
            "tool": "ingest", "arguments": {"metadata": "meta", "body": "text"}}}
        context = context_sources.Context(self.root, {"sources": {"remote-kb": source},
                                                   "servers": {"remote": {"command": "fake"}}})
        with patch("sky.ingestcommands.remote", return_value=(engine, ("adapter", context, "remote-kb"))), \
             patch("sky.context_sources.stdio_call", return_value={"ok": True}) as call:
            ingestcommands.transport(self.root)(engine, {"metadata": {"title": "Public"}, "body": "body"})
        self.assertEqual(call.call_args.args[2], {"meta": {"title": "Public"}, "text": "body"})

    def test_runtime_ingest_transport_rechecks_engine_and_requires_acknowledgement(self):
        engine = {"name": "remote-kb", "tenant": "public-demo"}
        source = {"server": "remote", "ingest.document": {"tool": "ingest"}}
        context = context_sources.Context(self.root, {"sources": {"remote-kb": source},
                                                   "servers": {"remote": {"command": "fake"}}})
        handle = ("adapter", context, "remote-kb")
        send = ingestcommands.transport(self.root)
        with patch("sky.ingestcommands.remote", return_value=(engine, handle)), \
             patch("sky.context_sources.stdio_call", return_value={"ok": True}) as call:
            self.assertEqual(send(engine, {"metadata": {}, "body": "public"}), {"ok": True})
            call.assert_called_once()
            with self.assertRaisesRegex(StoreError, "differs"):
                send({**engine, "tenant": "other"}, {"metadata": {}, "body": "public"})
        source, file, _ = self.handover()
        with patch("sky.ingestcommands.remote", return_value=(engine, handle)), \
             patch("sky.context_sources.stdio_call", return_value={}):
            with self.assertRaisesRegex(StoreError, "transport refused"):
                ingest.ingest(self.root, file, confirm=lambda _: True, transport=send, run=self.run, env={})
        self.assertTrue(source.exists())

    def test_ingest_cli_malformed_intent_and_transport_error_report_instead_of_crash(self):
        _, file, _ = self.handover()
        with patch("builtins.input", return_value="y"), \
             patch("sky.ingestcommands.transport", return_value=Mock(side_effect=RuntimeError("server disconnected"))):
            code, _, err = self.command("ingest", file)
        self.assertEqual(code, 1)
        self.assertIn("server disconnected", err)
        (self.root / file).write_bytes(b"{}")
        code, _, err = self.command("ingest", file)
        self.assertEqual(code, 1)
        self.assertIn("sky ingest", err)
