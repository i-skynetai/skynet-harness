"""Slice 3 CLI, hooks, adapter and published manifest contract; no network."""
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from sky import cli, context_sources, contextcommands, ledger, schemas
from tests.test_sh040_code_port import fake_server

ROOT = Path(__file__).resolve().parents[2]


class ContextWiring(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        (self.root / ".sky").mkdir()
        (self.root / ".sky/project.yaml").write_text("managed: true\n", encoding="utf-8")
        self.spec = {"command": sys.executable,
                     "args": [str(Path(__file__).resolve()), "--fake-server"],
                     "env": {"PYTHONPATH": str(ROOT / "core"), "PYTHONUTF8": "1"}}
        self.mcp = self.root / "mcp.json"
        self.mcp.write_text(json.dumps({"mcpServers": {"graph": self.spec}}), encoding="utf-8")
        self.resolver = patch("sky.context_sources.repository", return_value=self.root)
        self.resolver.start()
        self.addCleanup(self.resolver.stop)
        self.state = patch.dict(os.environ, {"SKY_STATE_DIR": str(self.root / "state")})
        self.state.start()
        self.addCleanup(self.state.stop)

    def invoke(self, *arguments):
        out = io.StringIO()
        with redirect_stdout(out):
            code = cli.main(list(arguments))
        return code, out.getvalue()

    def adapter(self):
        return contextcommands.write_code_adapter(self.root, self.mcp, "graph")

    def fixture(self):
        path = self.root / ".sky/sessions/run-fixture/tools.jsonl"
        path.parent.mkdir(parents=True)
        row = {"sequence": 1, "tool": "mcp__code__read_source", "server": "code",
               "input_identity": "a" * 64, "response_chars": 5, "failed": False,
               "operation": "code.source", "counting_method": ledger.COUNTING_METHOD}
        path.write_text(json.dumps(row) + "\n", encoding="utf-8")
        return path

    def test_hooks_have_bash_and_mcp_entries(self):
        hooks = json.loads((ROOT / "plugin/hooks/hooks.json").read_text(encoding="utf-8"))["hooks"]
        entries = {entry["matcher"]: entry for entry in hooks["PostToolUse"]}
        self.assertIn("Bash", entries)
        self.assertIn("mcp__.*", entries)
        self.assertTrue(entries["Bash"]["hooks"][0]["command"].endswith("/sky-ledger"))
        self.assertTrue(entries["mcp__.*"]["hooks"][0]["command"].endswith("/sky-ledger-mcp"))
        self.assertEqual(hooks["PreToolUse"][0]["matcher"], "Bash")
        self.assertEqual(hooks["PostToolUseFailure"][0]["matcher"], "mcp__.*")

    def test_failed_mcp_hook_records_error_count(self):
        payload = {"session_id": "fixture-session", "tool_name": "mcp__code__find_symbols",
                   "tool_input": {"query": "x"}, "hook_event_name": "PostToolUseFailure", "error": "unreachable"}
        with patch("sky.cli.sys.stdin", io.StringIO(json.dumps(payload))), patch("sky.ledger.repository", return_value=self.root), patch.dict(os.environ, {}, clear=True):
            self.assertEqual(cli.main(["ledger", "--mcp"]), 0)
        paths = list((self.root / ".sky/sessions").glob("*/tools.jsonl"))
        self.assertEqual(len(paths), 1)
        row = ledger.read(paths[0])[0]
        self.assertTrue(row["failed"])
        self.assertEqual(row["response_chars"], len("unreachable"))

    def test_shell_hook_scripts_parse(self):
        shell = shutil.which("sh") or shutil.which("bash")
        if not shell:
            self.skipTest("POSIX shell unavailable; shell syntax check not executed")
        for name in ("sky-guard", "sky-ledger", "sky-ledger-mcp"):
            result = subprocess.run([shell, "-n", str(ROOT / "plugin/bin" / name)],
                                    capture_output=True, encoding="utf-8", errors="replace")
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_mcp_hook_does_not_call_bash_ledger(self):
        with patch("sky.cli.sys.stdin", io.StringIO(json.dumps({"tool_name": "Read"}))), patch("sky.cli.guard.record") as old:
            self.assertEqual(cli.main(["ledger", "--mcp"]), 0)
            old.assert_not_called()

    def test_existing_bash_ledger_dispatch_is_unchanged(self):
        payload = {"tool_name": "Bash", "tool_input": {"command": "git status"}}
        with patch("sky.cli.sys.stdin", io.StringIO(json.dumps(payload))), patch("sky.cli.guard.record") as old:
            self.assertEqual(cli.main(["ledger"]), 0)
            old.assert_called_once_with(payload)

    def test_adapter_writer_is_deterministic_and_copies_server(self):
        path = self.adapter()
        first = path.read_bytes()
        self.adapter()
        self.assertEqual(path.read_bytes(), first)
        context = context_sources.load(root=self.root)
        self.assertEqual(context.servers["code"], self.spec)
        self.assertEqual(context.sources["code"]["code.outline"]["defaults"]["repo"], self.root.name)

    def test_unknown_server_refuses_before_writing(self):
        with self.assertRaisesRegex(ValueError, "unknown MCP server"):
            contextcommands.write_code_adapter(self.root, self.mcp, "missing")
        self.assertFalse((self.root / ".sky/context.yaml").exists())

    def test_adapter_command_writes_code_mapping(self):
        code, out = self.invoke("context", "adapter", "code", "--from-mcp-json", str(self.mcp),
                                "--server", "graph", "--repo", "example", "--branch", "topic")
        self.assertEqual(code, 0)
        self.assertIn("code adapter written", out)
        mapping = context_sources.load(root=self.root).sources["code"]["code.find"]
        self.assertEqual(mapping["defaults"], {"repo": "example", "branch": "topic"})

    def test_doctor_capability_code_ok_against_stdio_server(self):
        self.adapter()
        rows = context_sources.capabilities(context_sources.load(root=self.root))
        row = next(row for row in rows if row[0] == "code")
        self.assertEqual(row[1], "ok")

    def test_doctor_capability_missing_tool_is_named(self):
        self.spec["args"].append("read_source")
        self.mcp.write_text(json.dumps({"mcpServers": {"graph": self.spec}}), encoding="utf-8")
        self.adapter()
        row = next(row for row in context_sources.capabilities(context_sources.load(root=self.root)) if row[0] == "code")
        self.assertEqual(row[1], "MISSING")
        self.assertIn("read_source", row[2])

    def test_manifest_command_json_validates_and_reports_order(self):
        self.adapter()
        self.fixture()
        code, out = self.invoke("context", "manifest", "run-fixture", "--json")
        self.assertEqual(code, 0)
        result = json.loads(out)
        self.assertEqual(schemas.validate(schemas.CONTEXT_MANIFEST, result), [])
        self.assertEqual(result["measured_characters"], 5)
        self.assertEqual(result["items"], [])
        self.assertIn("verification before", result["findings"][0])

    def test_absent_source_is_a_manifest_finding(self):
        self.fixture()
        result = contextcommands.manifest(self.root, "run-fixture")
        self.assertTrue(any("absent source code" in finding for finding in result["findings"]))

    def test_manifest_command_prints_counting_method(self):
        self.fixture()
        code, out = self.invoke("context", "manifest", "run-fixture")
        self.assertEqual(code, 0)
        self.assertIn("5 characters", out)
        self.assertIn(ledger.COUNTING_METHOD, out)

    def test_manifest_refuses_path_run_id(self):
        with self.assertRaisesRegex(ValueError, "not a path"):
            contextcommands.manifest(self.root, "../other")

    def test_manifest_refuses_absent_ledger(self):
        with self.assertRaisesRegex(ValueError, "absent"):
            contextcommands.manifest(self.root, "missing")

    def test_published_manifest_schema_matches_core(self):
        published = json.loads((ROOT / "schemas/context-manifest.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(published, schemas.json_schema(schemas.CONTEXT_MANIFEST))

    def test_measurements_cannot_be_claimed_by_model(self):
        problems = schemas.validate(schemas.CONTEXT_MANIFEST, {"retrievals": [], "measured_characters": 0}, source=schemas.MODEL)
        self.assertTrue(any("only the runtime" in problem for problem in problems))

    def test_negative_character_count_is_refused(self):
        self.fixture()
        result = contextcommands.manifest(self.root, "run-fixture")
        result["retrievals"][0]["characters"] = -1
        self.assertTrue(schemas.validate(schemas.CONTEXT_MANIFEST, result))

    def test_content_block_array_counts_text_without_json_envelope(self):
        self.assertEqual(ledger.measured_response([{"type": "text", "text": "a😀"}]), 2)

    def test_standard_launched_run_ledger_is_found(self):
        run = self.root / "state/runs/run-standard"
        run.mkdir(parents=True)
        (run / "events.jsonl").write_text('{"kind":"run.start"}\n', encoding="utf-8")
        payload = {"session_id": "session", "tool_name": "mcp__code__find_symbols", "tool_response": "ok"}
        with patch("sky.ledger.repository", return_value=self.root):
            path = ledger.record(payload, env={"SKY_RUN_ID": "run-standard", "SKY_RUN_DIR": str(run)})
        self.assertEqual(path, run / "tools.jsonl")
        self.assertEqual(contextcommands.manifest(self.root, "run-standard")["measured_characters"], 2)


if __name__ == "__main__":
    if "--fake-server" in sys.argv:
        fake_server()
    else:
        unittest.main()
