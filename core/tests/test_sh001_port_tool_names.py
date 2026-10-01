"""SH-001: the probes call the tools the knowledge port names.

The probes once called `kb.similarity_search` while the port document, the
policy and the skills all said `kb_similarity_search`. Against a server built to
the document, `doctor` reported focus DOWN and `ready for: nothing`. These tests
stand up exactly that server — one that knows only the documented names — and
pin the names to the policy and the port document so they cannot drift again.
"""
from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sky import probes  # noqa: E402
from sky.kbmap import KB  # noqa: E402
from sky.policy import Policy  # noqa: E402
from sky.readiness import Brain, Part, State  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
POLICY = Policy.load(REPO / "plugin" / "policy.yaml")
PORT_DOC = REPO / "docs" / "knowledge-port.md"

A_KB = KB(name="stub", purpose="", url="https://stub.invalid/mcp/",
          tenant="ABCD2345", ontology="kb_sdlc", privacy="work",
          write=True, pat_env="SKY_TEST_PAT")

#: Port operations that write. The agent never calls these as plain tools; the
#: policy names them as an outward action instead.
WRITE_ACTIONS = {"documents_ingest": "kb.ingest"}


def documented_operations() -> set[str]:
    """The operations in the port document's table, read from the document."""
    names = set()
    for line in PORT_DOC.read_text().splitlines():
        if line.startswith("| `"):
            names.update(re.findall(r"`([a-z_]+)`", line.split("|")[1]))
    return names


class PortServer:
    """A knowledge base built to the port document and nothing more.

    It refuses any tool name the document does not give, the way a real MCP
    server answers an unknown tool.
    """

    def __init__(self):
        self.known = {probes.kb_tool(op) for op in documented_operations()}
        self.called = []

    def _answer(self, name, args):
        self.called.append(name)
        if name not in self.known:
            raise RuntimeError(f"unknown tool {name!r}")
        reply = {
            probes.kb_tool("similarity_search"): {"hits": [
                {"text": "…", "metadata": {"doc_id": "d1", "tenant_code": "ABCD2345"}}]},
            probes.kb_tool("ontologies_get"): {"entity_types": ["Module", "Service"]},
            probes.kb_tool("documents_ingest"): {"job_id": "j1"},
            probes.kb_tool("jobs_status"): {"status": "COMPLETED"},
            probes.kb_tool("jobs_output"): {"entities": 3},
        }.get(name, {})
        return json.dumps(reply)

    def _rpc(self, url, token, method, params):
        if method == "tools/list":
            return {"tools": [{"name": n} for n in sorted(self.known)]}
        text = self._answer(params["name"], params.get("arguments", {}))
        return {"content": [{"type": "text", "text": text}]}

    def _call_tool(self, url, token, name, args):
        return self._answer(name, args)

    def __enter__(self):
        import os
        self.saved = (probes._rpc, probes._call_tool, os.environ.get("SKY_TEST_PAT"))
        probes._rpc, probes._call_tool = self._rpc, self._call_tool
        os.environ["SKY_TEST_PAT"] = "a-token"
        return self

    def __exit__(self, *exc):
        import os
        probes._rpc, probes._call_tool, pat = self.saved
        if pat is None:
            os.environ.pop("SKY_TEST_PAT", None)
        else:
            os.environ["SKY_TEST_PAT"] = pat
        return False


def state(brain: Brain, part: Part):
    row = next(o for o in brain.observations if o.part is part)
    return row.state, row.detail


class AServerBuiltToThePortDocument(unittest.TestCase):

    def test_focus_is_ok(self):
        with PortServer() as server:
            brain = Brain()
            probes.probe_knowledge(brain, A_KB)
            probes.probe_focus(brain, A_KB)
        got, detail = state(brain, Part.FOCUS)
        self.assertIs(got, State.OK, detail)
        self.assertEqual(server.called, [probes.kb_tool("similarity_search")])

    def test_the_deep_ingest_probe_calls_only_documented_names(self):
        saved_sleep = probes.time.sleep
        probes.time.sleep = lambda s: None
        try:
            with PortServer() as server:
                brain = Brain()
                probes.probe_remembering(brain, A_KB, deep=True)
        finally:
            probes.time.sleep = saved_sleep
        got, detail = state(brain, Part.REMEMBERING)
        self.assertIs(got, State.OK, detail)
        self.assertEqual(set(server.called), {probes.kb_tool(op) for op in (
            "ontologies_get", "documents_ingest", "jobs_status", "jobs_output")})


class TheNamesLiveInOnePlace(unittest.TestCase):

    def test_every_probe_operation_is_in_the_port_document(self):
        missing = set(probes.PROBE_OPERATIONS) - documented_operations()
        self.assertFalse(missing, f"not in {PORT_DOC.name}: {sorted(missing)}")

    def test_every_probe_tool_is_one_the_policy_names(self):
        listed = {tool for role in POLICY.roles for tool in POLICY.tools_for(role)}
        for op in probes.PROBE_OPERATIONS:
            if op in WRITE_ACTIONS:
                action = POLICY.actions.get(WRITE_ACTIONS[op])
                self.assertIsNotNone(action, f"{op}: policy has no {WRITE_ACTIONS[op]}")
                self.assertTrue(action.outward, f"{op} must be outward")
                continue
            suffix = f"__{probes.kb_tool(op)}"
            self.assertTrue(any(t.endswith(suffix) for t in listed),
                            f"no role's tool list names {probes.kb_tool(op)}")

    def test_no_probe_spells_a_tool_name_itself(self):
        source = (REPO / "core" / "sky" / "probes.py").read_text()
        spelled = re.findall(r'"kb[._][a-z_.]+"', source)
        self.assertEqual(spelled, [], "use kb_tool(<operation>) instead")


if __name__ == "__main__":
    unittest.main(verbosity=2)
