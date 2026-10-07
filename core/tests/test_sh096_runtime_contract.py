import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from sky import codexhost, recorder


class RuntimeContract(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.run = recorder.Run.start(role="developer", task="implement", kb="local",
                                      agent_id="sky:developer", root=self.root)
        self.env = {"SKY_LAUNCHED": "1", "SKY_RUN_DIR": str(self.run.directory),
                    "SKY_RUN_ID": self.run.run_id, "SKY_AGENT_ID": self.run.agent_id,
                    "SKY_ROLE": self.run.role, "SKY_TASK": self.run.task, "SKY_KB_NAME": self.run.kb}

    def test_substitution_and_missing_record_refused(self):
        self.assertEqual(codexhost.run_environment(self.run, self.env), self.env)
        for key in self.env:
            changed = dict(self.env, **{key: "forged"})
            with self.subTest(key=key), self.assertRaises(codexhost.Refused):
                codexhost.run_environment(self.run, changed)
        (self.run.directory / "events.jsonl").write_text('{}\n', encoding="utf-8")
        with self.assertRaises(codexhost.Refused):
            codexhost.run_environment(self.run, self.env)

    def test_only_terminal_calls_go_to_existing_ledger(self):
        item = {"type": "mcpToolCall", "status": "completed", "server": "sky_kb",
                "tool": "search", "arguments": {"query": "design"}, "result": {"content": []}}
        with patch("sky.codexhost.ledger.record") as record:
            codexhost.record_mcp(item, session_id="thread", root=self.root, run_env=self.env)
            payload = record.call_args.args[0]
            self.assertEqual(payload["tool_name"], "mcp__sky_kb__search")
            self.assertEqual(payload["hook_event_name"], "PostToolUse")
            self.assertEqual(record.call_args.kwargs["env"], self.env)
            record.reset_mock()
            for change in ({"status": "inProgress"}, {"server": "forged__alias"}):
                with self.assertRaises(codexhost.Refused):
                    codexhost.record_mcp(dict(item, **change), session_id="thread",
                                         root=self.root, run_env=self.env)
            record.assert_not_called()
            codexhost.record_mcp(dict(item, status="failed", error="timeout"),
                                 session_id="thread", root=self.root, run_env=self.env)
            self.assertEqual(record.call_args.args[0]["hook_event_name"], "PostToolUseFailure")

    def test_dispatch_reuses_run_and_preserves_observed_failure(self):
        log = self.root / "host.jsonl"
        with patch("sky.context_sources.load", return_value=None), patch("sky.codexcontroller.run", return_value={"summary": "prepared", "role": "developer"}) as start:
            result = codexhost.execute(["codex", "ignored legacy flags"], env=self.env,
                                       cwd=self.root, log_path=log)
            self.assertTrue(result.ok)
            self.assertEqual(start.call_args.kwargs["runtime_run"].run_id, self.run.run_id)
            self.assertEqual(start.call_args.kwargs["runtime_env"], self.env)
        with patch("sky.codexcontroller.run", side_effect=ValueError("host connection ended")):
            result = codexhost.execute(["codex"], env=self.env, cwd=self.root, log_path=log)
            self.assertFalse(result.ok)
            self.assertEqual(result.reason, "failed")
        with patch("sky.codexcontroller.run") as start:
            codexhost.execute(["codex"], env=dict(self.env, SKY_ROLE="forged"),
                              cwd=self.root, log_path=log)
            start.assert_not_called()
