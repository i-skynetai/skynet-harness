"""Managed MCP ledger and recorded-fixture context measurements."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sky import context_measurements, ledger


class MCPLedger(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        (self.root / ".sky").mkdir()
        (self.root / ".sky/project.yaml").write_text("managed: true\n", encoding="utf-8")
        self.resolver = patch("sky.ledger.repository", return_value=self.root)
        self.resolver.start()
        self.addCleanup(self.resolver.stop)

    def payload(self, **changes):
        return {"session_id": "session", "tool_name": "mcp__code__find_symbols",
                "tool_input": {"query": "Thing", "token": "private-secret"},
                "tool_response": {"content": [{"type": "text", "text": "a😀"}]}, **changes}

    def record(self, **changes):
        return ledger.record(self.payload(**changes), env={})

    def test_managed_session_does_not_require_launched_marker(self):
        self.assertTrue(self.record().is_file())

    def test_input_identity_contains_no_plaintext(self):
        text = self.record().read_text(encoding="utf-8")
        self.assertNotIn("private-secret", text)
        self.assertNotIn("Thing", text)
        self.assertEqual(len(json.loads(text)["input_identity"]), 64)

    def test_response_counts_unicode_characters_without_content(self):
        row = ledger.read(self.record())[0]
        self.assertEqual(row["response_chars"], 2)
        self.assertEqual(row["server"], "code")
        self.assertNotIn("tool_response", row)

    def test_sequence_increments_across_calls(self):
        path = self.record()
        self.record()
        self.assertEqual([r["sequence"] for r in ledger.read(path)], [1, 2])

    def test_failure_is_recorded(self):
        row = ledger.read(self.record(tool_response={"isError": True, "content": []}))[0]
        self.assertTrue(row["failed"])

    def test_unmanaged_project_is_not_recorded(self):
        from sky.context_sources import NotManaged
        with patch("sky.ledger.repository", side_effect=NotManaged("absent")):
            self.assertIsNone(self.record())

    def test_missing_session_refuses(self):
        with self.assertRaisesRegex(ValueError, "session_id"):
            self.record(session_id=None)

    def test_external_run_directory_refuses(self):
        with tempfile.TemporaryDirectory() as other:
            with self.assertRaisesRegex(ValueError, "inside repository"):
                ledger.record(self.payload(), env={"SKY_RUN_DIR": other})

    def test_non_mcp_tool_is_left_to_existing_ledger(self):
        self.assertIsNone(self.record(tool_name="Bash"))

    def test_protocol_identity_comes_from_adapter(self):
        from sky.context_sources import Context
        context = Context(self.root, {"sources": {"code": {"server": "code",
                          "code.find": {"tool": "find_symbols"}}}})
        path = ledger.record(self.payload(), env={}, context=context)
        self.assertEqual(ledger.read(path)[0]["operation"], "code.find")

    def test_invalid_present_project_config_refuses(self):
        from sky.policy import PolicyError
        (self.root / ".sky/project.yaml").write_text("managed: true\nunknown: true\n", encoding="utf-8")
        with self.assertRaisesRegex(PolicyError, "unknown"):
            self.record()

    def test_malformed_existing_ledger_is_not_silently_skipped(self):
        path = self.record()
        path.write_text("broken\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "invalid JSON"):
            self.record()

    def fixture(self, operations):
        path = self.root / "fixture.jsonl"
        rows = [{"sequence": i, "tool": "mcp__code__fixture", "server": "code",
                 "input_identity": str(i), "response_chars": i * 3, "failed": False,
                 "operation": operation, "counting_method": ledger.COUNTING_METHOD}
                for i, operation in enumerate(operations, 1)]
        path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
        return path

    def test_manifest_totals_measured_items(self):
        result = context_measurements.build(self.fixture(["code.find", "code.source"]))
        self.assertEqual(result["measured_characters"], 9)
        self.assertEqual(result["items"][0]["source"], "code")
        self.assertEqual(result["counting_method"], ledger.COUNTING_METHOD)
        self.assertEqual(result["findings"], [])

    def test_verification_before_index_is_a_finding(self):
        result = context_measurements.build(self.fixture(["code.source", "code.find"]))
        self.assertIn("verification before", result["findings"][0])

    def test_failed_index_is_visible(self):
        path = self.fixture(["code.find", "code.source"])
        rows = ledger.read(path)
        rows[0]["failed"] = True
        path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
        self.assertEqual(len(context_measurements.build(path)["findings"]), 1)

    def test_malformed_measurements_refuse(self):
        path = self.fixture(["code.find"])
        row = ledger.read(path)[0]
        row["response_chars"] = -1
        path.write_text(json.dumps(row) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "malformed"):
            context_measurements.build(path)

    def test_duplicate_sequence_refuses(self):
        path = self.fixture(["code.find"])
        line = path.read_text(encoding="utf-8")
        path.write_text(line + line, encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "out-of-order"):
            context_measurements.build(path)
