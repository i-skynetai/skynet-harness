"""The approval controller must refuse before a host receives permission."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import subprocess
import sys

SOURCE = Path(__file__).resolve().parents[2] / "hosts/codex/governed_probe.py"
spec = importlib.util.spec_from_file_location("codex_governed", SOURCE)
gate_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate_module)


class CodexApprovalBoundary(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.effective = SimpleNamespace(
            root=self.root, body={"version": 1}, config={"managed": True},
            tools_for=lambda role: ("Read", "Grep", "Glob", "Edit", "Write"),
            decide=lambda role, action: SimpleNamespace(allowed=True))
        self.gate = gate_module.Gate(self.effective, "developer", self.root / "events.jsonl")
        self.gate.thread, self.gate.turn = "thread", "turn"

    def patch(self, path="hello.py", **params):
        self.gate.observe({"method": "item/started", "params": {
            "threadId": "thread", "turnId": "turn", "item": {
                "type": "fileChange", "id": "patch", "changes": [
                    {"path": str(self.root / path), "kind": {"type": "add"}, "diff": "hello"}]}}})
        return {"id": 1, "method": "item/fileChange/requestApproval", "params": {
            "threadId": "thread", "turnId": "turn", "itemId": "patch", **params}}

    def decision(self, request):
        return self.gate.approve(request, self.effective)["decision"]

    def test_developer_gets_one_patch_not_a_session_grant(self):
        self.assertEqual(self.decision(self.patch()), "accept")
        self.assertFalse((self.root / "hello.py").exists())
        event = json.loads((self.root / "events.jsonl").read_text())
        self.assertEqual(event["decision"], "accept")

    def test_reviewer_cannot_edit_even_when_tool_list_has_write(self):
        self.gate.role = "reviewer"
        self.assertEqual(self.decision(self.patch()), "decline")

    def test_policy_action_denial_is_not_overridden_by_role_name(self):
        request = self.patch()
        self.effective.decide = lambda role, action: SimpleNamespace(allowed=False)
        self.assertEqual(self.decision(request), "decline")

    def test_removed_write_tool_is_not_regranted(self):
        request = self.patch()
        self.effective.tools_for = lambda role: ("Read", "Grep", "Glob", "Edit")
        self.assertEqual(self.decision(request), "decline")

    def test_governance_and_external_paths_are_denied(self):
        for path in ("../outside.py", ".git/config", ".sky/policy.yaml",
                     ".codex/config.toml", ".claude/settings.json", "AGENTS.md"):
            with self.subTest(path=path):
                self.gate.used.clear()
                self.assertEqual(self.decision(self.patch(path)), "decline")

    def test_broad_grant_is_denied(self):
        self.assertEqual(self.decision(self.patch(grantRoot=str(self.root))), "decline")

    def test_missing_patch_is_an_error(self):
        request = self.patch()
        self.gate.items.clear()
        with self.assertRaises(gate_module.Refused):
            self.decision(request)

    def test_wrong_identity_and_replay_are_errors(self):
        request = self.patch(turnId="other")
        with self.assertRaises(gate_module.Refused):
            self.decision(request)
        request = self.patch()
        self.decision(request)
        with self.assertRaises(gate_module.Refused):
            self.decision(request)

    def test_changed_policy_cannot_authorize_an_inflight_patch(self):
        request = self.patch()
        self.effective.body = {"version": 2}
        with self.assertRaises(gate_module.Refused):
            self.decision(request)

    def test_command_and_network_escalation_are_denied(self):
        request = self.patch()
        request["method"] = "item/commandExecution/requestApproval"
        self.gate.items["patch"] = {"type": "commandExecution", "command": None}
        self.assertEqual(self.decision(request), "decline")

    def test_command_vocabulary_rejects_operators_unknown_programs_and_expansion(self):
        shell = self.root / "pwsh.exe"
        shell.touch()
        workspace = self.root / "project"
        workspace.mkdir()
        for script in ("python -B socket_probe.py", "npm test; git push", "npm test | curl",
                       "npm test && git push", "cat $HOME/auth.json", "Get-Content ../secret"):
            with self.subTest(script=script):
                command = '"' + str(shell) + '" -Command ' + repr(script)
                self.assertIsNone(gate_module.command_binding(workspace, command))
        command = '"' + str(shell) + '" -Command ' + repr("npm test")
        self.assertEqual(gate_module.command_binding(workspace, command),
                         ("Bash(npm test:*)", "test.run"))

    def test_unknown_permission_request_is_an_error(self):
        request = self.patch()
        request["method"] = "item/permissions/requestApproval"
        with self.assertRaises(gate_module.Refused):
            self.decision(request)

    def test_link_escape_is_denied(self):
        target = self.root / "original"
        target.write_text("keep")
        alias = self.root / "alias"
        try:
            os.link(target, alias)
        except OSError:
            self.skipTest("host cannot create hard-link fixture")
        self.assertEqual(self.decision(self.patch("alias")), "decline")

    def test_logging_failure_prevents_approval(self):
        self.gate.log = self.root
        with self.assertRaises(OSError):
            self.decision(self.patch())

    def test_unrepresentable_read_role_is_refused(self):
        self.effective.tools_for = lambda role: ("Grep", "Glob")
        with self.assertRaises(gate_module.Refused):
            gate_module.Gate(self.effective, "reviewer", self.root / "events")

    def test_briefing_budget_refuses_in_preflight_before_host_start(self):
        self.effective.config["context"] = {"max_chars": 100}
        self.effective.tools_for = lambda role: ("Read", "Grep", "Glob", "mcp__sky_kb__search")
        manifest = self.root / ".sky/kb/manifest.json"
        manifest.parent.mkdir(parents=True)
        manifest.write_text("{}")
        home = self.root / "login"
        home.mkdir()
        (home / "auth.json").write_text("{}")
        from sky import codexcontroller
        with patch.dict(os.environ, {"CODEX_HOME": str(home)}), \
             patch.object(codexcontroller.project, "resolve", return_value=self.effective), \
             patch.object(codexcontroller, "installed_package", return_value=self.root), \
             patch.object(codexcontroller, "procedures", return_value="procedure" * 100), \
             patch.object(codexcontroller.Server, "search", return_value=[]), \
             patch.object(codexcontroller.subprocess, "run", return_value=SimpleNamespace(
                 returncode=0, stdout="codex-cli 0.160.0")), \
             patch.object(codexcontroller.subprocess, "Popen") as host:
            with self.assertRaisesRegex(codexcontroller.Refused, "context over budget"):
                codexcontroller.preflight(self.root, "reviewer", task="review")
            host.assert_not_called()

    def test_protocol_errors_disconnects_and_timeouts_kill_the_peer(self):
        self.effective.config.update(sessions_dir=".sky/sessions", context={"max_chars": 40000})
        self.effective.tools_for = lambda role: ("Read", "Grep", "Glob", "mcp__sky_kb__search")
        manifest = self.root / ".sky/kb/manifest.json"
        manifest.parent.mkdir(parents=True)
        manifest.write_text("{}")
        home = self.root / "login"
        home.mkdir()
        (home / "auth.json").write_text("{}")
        real_popen = subprocess.Popen
        fixture = Path(__file__).parent / "fixtures/codex_approval_host.py"
        for mode in ("disconnect", "timeout", "unknown", "malformed", "network", "silent"):
            with self.subTest(mode=mode):
                peers = []
                def start(command, **kwargs):
                    peer = real_popen([sys.executable, str(fixture), "timeout" if mode == "silent" else mode], **kwargs)
                    peers.append(peer)
                    return peer
                with patch.dict(os.environ, {"CODEX_HOME": str(home)}), \
                     patch.object(gate_module.project, "resolve", return_value=self.effective), \
                     patch.object(gate_module.Server, "search", return_value=[]), \
                     patch.object(gate_module.hand, "_windows_job", return_value=None), \
                     patch.object(gate_module.subprocess, "run", return_value=SimpleNamespace(
                         returncode=0, stdout="codex-cli 0.160.0")), \
                     patch.object(gate_module.subprocess, "Popen", side_effect=start):
                    with self.assertRaises(gate_module.Refused) as refused:
                        gate_module.run(self.root, "reviewer", "review", timeout=.3,
                                        silence_cap=.06 if mode == "silent" else 420)
                    if mode == "silent":
                        self.assertIn("silence cap", str(refused.exception))
                self.assertTrue(peers)
                self.assertIsNotNone(peers[0].poll())
                self.assertFalse(list(self.root.glob(".sky-codex-*")))
