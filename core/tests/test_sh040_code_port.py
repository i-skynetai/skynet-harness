"""Code protocol round trips against a fake stdio server; no network."""
import json
import sys
import unittest
from pathlib import Path

from sky.codeport import CodePort, TOOLS, skygraph_adapter
from sky.context_sources import Context, ContextError


class CodePortTests(unittest.TestCase):
    def port(self, missing=None):
        spec = {"command": sys.executable, "args": [str(Path(__file__).resolve()), "--fake-server"],
                "env": {"PYTHONPATH": str(Path(__file__).resolve().parents[1]), "PYTHONUTF8": "1"}}
        if missing:
            spec["args"].append(missing)
        return CodePort(Context(Path.cwd(), {"servers": {"code": spec},
                        "sources": {"code": skygraph_adapter("fixture")}}))

    def test_find_round_trip_translates_name_to_query(self):
        result = self.port().invoke("code.find", name="Thing")
        self.assertEqual(result["arguments"], {"query": "Thing", "repo": "fixture", "branch": "main"})
        self.assertEqual(result["tool"], "find_symbols")

    def test_outline_round_trip_supplies_repo_and_filepath(self):
        result = self.port().invoke("code.outline", file="module.py")
        self.assertEqual(result["arguments"]["filepath"], "module.py")
        self.assertEqual(result["arguments"]["repo"], "fixture")
        self.assertEqual(result["tool"], "outline_file")

    def test_source_round_trip_preserves_stale_metadata(self):
        result = self.port().invoke("code.source", qualified_name="module.py::Thing")
        self.assertEqual(result["tool"], "read_source")
        self.assertTrue(result["stale"])
        self.assertEqual(result["source"], "class Thing: pass")

    def test_related_round_trip_preserves_relations(self):
        result = self.port().invoke("code.related", qualified_name="module.py::Thing")
        self.assertEqual(result["tool"], "related_symbols")
        self.assertEqual(result["calls"], ["other"])

    def test_absent_capability_is_reported(self):
        self.assertEqual(CodePort(None).status()[0], "absent")
        with self.assertRaisesRegex(ContextError, "absent"):
            CodePort(None).invoke("code.find", name="Thing")

    def test_missing_mapped_tool_is_named(self):
        state, detail = self.port("read_source").status()
        self.assertEqual(state, "MISSING")
        self.assertIn("read_source", detail)

    def test_complete_capability_is_ok(self):
        self.assertEqual(self.port().status()[0], "ok")

    def test_refresh_is_not_a_read_operation(self):
        with self.assertRaisesRegex(ContextError, "unsupported"):
            self.port().invoke("index.refresh", paths="module.py")

    def test_missing_argument_refuses_before_call(self):
        with self.assertRaisesRegex(ContextError, "missing"):
            self.port().invoke("code.outline")


def fake_server():
    missing = sys.argv[2] if len(sys.argv) > 2 else None
    for line in sys.stdin:
        request = json.loads(line)
        if "id" not in request:
            continue
        method = request["method"]
        if method == "initialize":
            result = {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}},
                      "serverInfo": {"name": "fixture", "version": "1"}}
        elif method == "tools/list":
            result = {"tools": [{"name": name, "inputSchema": {"type": "object"}}
                                for name in TOOLS.values() if name != missing]}
        else:
            params = request["params"]
            value = {"tool": params["name"], "arguments": params["arguments"],
                     "stale": True, "source": "class Thing: pass", "calls": ["other"]}
            result = {"content": [{"type": "text", "text": json.dumps(value)}]}
        print(json.dumps({"jsonrpc": "2.0", "id": request["id"], "result": result}), flush=True)


if __name__ == "__main__":
    if "--fake-server" in sys.argv:
        fake_server()
    else:
        unittest.main()
