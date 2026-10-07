"""SH-083 local transactions and MCP fixtures; no live service or CLI wiring."""
import copy
import io
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from sky import kbserve, kbstore
from sky.kbstore import Approval, Store, StoreBusy, StoreError

STAMP = {"sky_agent": "runtime", "sky_run": "fixture-run", "sky_role": "architect",
         "sky_task": "fixture-task", "sky_kb": "local"}
APPROVAL = Approval("fixture-person", "fixture-session", "confirmation-1", "2026-10-06T12:00:00Z")


class LocalStore(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        (self.root / "code.py").write_text("# evidence\nprint('fixture')\n", encoding="utf-8")
        self.store = Store(self.root, chunk_chars=16)

    def metadata(self, **updates):
        return {"type": "doc", "title": "Fixture document", "project": "fixture",
                "source": "docs/fixture.md", **updates}

    def put(self, body="HTTP client conventions", **updates):
        return self.store.put(self.metadata(**updates), body, stamp=STAMP)

    def decision(self, **updates):
        return self.metadata(id="decision-http", type="decision", version=1, scope=["."],
            question="How do services communicate?", aliases=["Which HTTP client?"],
            answer="HTTP", rationale="Existing convention", status="accepted", supersedes=[],
            source_analysis="analysis-1", evidence_revision="checkout-1", citations=["code.py:1"], **updates)

    def knowledge(self, **updates):
        return self.metadata(id="knowledge-http", type="knowledge", scope=["."], module="fixture",
            category="pattern", confidence=0.8, checkout_digest="a" * 64,
            index_digest="b" * 64, stale=False, citations=["code.py:1"], **updates)

    def save_decision(self, metadata=None):
        return self.store.put(metadata or self.decision(), "HTTP is the convention.",
                              stamp=STAMP, approval=APPROVAL)

    def test_markdown_frontmatter_round_trip_and_manifest_revision(self):
        entry = self.put()
        loaded = self.store.get(entry["id"])
        self.assertEqual(loaded["body"], "HTTP client conventions")
        self.assertEqual(loaded["metadata"]["sky_run"], "fixture-run")
        self.assertTrue((self.root / entry["path"]).read_text(encoding="utf-8").startswith("---\n{"))
        self.assertEqual(self.store.manifest()["generation"], 1)

    def test_stable_document_and_chunk_ids_survive_body_update(self):
        first = self.put("abcdefgh" * 5)
        second = self.put("ijklmnop" * 5)
        self.assertEqual(first["id"], second["id"])
        self.assertEqual([c["id"] for c in first["chunks"]], [c["id"] for c in second["chunks"]])
        self.assertNotEqual(first["digest"], second["digest"])
        self.assertTrue((self.root / first["path"]).exists())

    def test_same_write_is_idempotent_without_timestamp_or_manifest_change(self):
        first = self.put()
        before = (self.root / ".sky/kb/manifest.json").read_bytes()
        self.assertEqual(self.put(), first)
        self.assertEqual((self.root / ".sky/kb/manifest.json").read_bytes(), before)

    def test_explicit_id_survives_source_rename(self):
        first = self.put(id="stable-doc")
        second = self.put(id="stable-doc", source="docs/renamed.md")
        self.assertEqual(first["id"], second["id"])

    def test_missing_or_mismatched_runtime_stamp_refuses(self):
        for stamp in ({}, {**STAMP, "sky_run": ""}):
            with self.assertRaisesRegex(StoreError, "stamp required"):
                self.store.put(self.metadata(), "text", stamp=stamp)
        with self.assertRaisesRegex(StoreError, "stamp mismatch"):
            self.put(sky_agent="model-forged")
        self.assertFalse((self.root / ".sky/kb/manifest.json").exists())

    def test_runtime_owned_approval_fields_cannot_arrive_from_model(self):
        for key in ("approval", "decided_by", "recorded_at", "run_identity"):
            with self.assertRaisesRegex(StoreError, "runtime-owned"):
                self.store.put({**self.decision(), key: "forged"}, "text", stamp=STAMP, approval=APPROVAL)

    def test_decision_requires_approval_and_runtime_seals_evidence(self):
        with self.assertRaisesRegex(StoreError, "runtime approval"):
            self.store.put(self.decision(), "text", stamp=STAMP)
        entry = self.save_decision()
        meta = self.store.get(entry["id"])["metadata"]
        self.assertEqual(meta["approval"], APPROVAL.evidence())
        self.assertEqual(meta["decided_by"], APPROVAL.actor)
        self.assertEqual(meta["run_identity"], STAMP["sky_run"])

    def test_decision_schema_rejects_empty_answer_and_unknown_fields(self):
        for changes in ({"answer": ""}, {"extra": "unknown"}, {"version": True}):
            with self.assertRaises(StoreError):
                self.save_decision({**self.decision(), **changes})

    def test_knowledge_is_cited_observation_with_checked_digests(self):
        entry = self.store.put(self.knowledge(), "A reusable pattern", stamp=STAMP)
        meta = self.store.get(entry["id"])["metadata"]
        self.assertNotIn("approval", meta)
        self.assertEqual(kbserve.Server(self.store).decisions_find("pattern", "fixture", "."), [])
        for changes in ({"citations": []}, {"checkout_digest": "bad"}, {"confidence": 2}):
            with self.assertRaises(StoreError):
                self.store.put({**self.knowledge(), **changes}, "text", stamp=STAMP)

    def test_citations_require_existing_contained_file_and_valid_line(self):
        for citation in ("missing.py:1", "code.py:0", "code.py:100", "../escape.py:1", "not-a-citation"):
            with self.assertRaises(StoreError):
                self.put(citations=[citation])
        self.put(citations=["code.py:2"])

    def test_record_citation_resolves_and_missing_reference_refuses(self):
        first = self.put(id="first")
        self.put(id="second", citations=["id:" + first["id"]])
        with self.assertRaisesRegex(StoreError, "record not found"):
            self.put(id="third", citations=["id:missing"])

    def test_traversal_absolute_windows_paths_and_unsafe_ids_refuse(self):
        for source in ("../outside.md", "/outside.md", "C:/outside.md", "docs\\file.md"):
            with self.assertRaises(StoreError):
                self.put(source=source)
        for id in ("../escape", "a/b", ""):
            with self.assertRaisesRegex(StoreError, "invalid document id"):
                self.put(id=id)

    def test_symlinked_store_and_input_file_refuse(self):
        outside = self.root / "outside"
        outside.mkdir()
        link = self.root / ".sky"
        try:
            link.symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest("this Windows user cannot create symlink fixtures")
        with self.assertRaisesRegex(StoreError, "symlink refused"):
            self.put()
        link.unlink()
        (self.root / "input.md").symlink_to(self.root / "code.py")
        with self.assertRaisesRegex(StoreError, "symlink refused"):
            self.store.put_file("input.md", stamp=STAMP)

    def test_interrupted_manifest_commit_keeps_previous_document_and_manifest(self):
        first = self.put("previous")
        before_manifest = (self.root / ".sky/kb/manifest.json").read_bytes()
        before_doc = (self.root / first["path"]).read_bytes()
        atomic = self.store._atomic
        def fail_manifest(path, text):
            if path.name == "manifest.json":
                raise OSError("injected pre-commit interruption")
            atomic(path, text)
        with patch.object(self.store, "_atomic", side_effect=fail_manifest):
            with self.assertRaises(OSError):
                self.put("changed")
        self.assertEqual((self.root / ".sky/kb/manifest.json").read_bytes(), before_manifest)
        self.assertEqual((self.root / first["path"]).read_bytes(), before_doc)
        self.assertEqual(self.store.get(first["id"])["body"], "previous")

    def test_two_writers_serialize_and_preserve_both_manifest_entries(self):
        errors = []
        ready = threading.Event()
        def writer():
            ready.set()
            try:
                Store(self.root).put(self.metadata(id="second"), "second", stamp=STAMP)
            except Exception as exc:
                errors.append(exc)
        with self.store.locked():
            thread = threading.Thread(target=writer)
            thread.start()
            self.assertTrue(ready.wait(2))
            self.assertFalse((self.root / ".sky/kb/manifest.json").exists())
        thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])
        self.put("first", id="first")
        self.assertEqual(set(self.store.manifest()["documents"]), {"first", "second"})

    def test_lock_contention_times_out_instead_of_breaking_live_lock(self):
        with self.store.locked():
            with self.assertRaises(StoreBusy):
                with Store(self.root, lock_timeout=0).locked():
                    self.fail("contending writer entered")

    def test_unknown_schema_versions_and_malformed_relations_refuse(self):
        for metadata in (self.metadata(schema_version=2), self.metadata(relates_to="wrong")):
            with self.assertRaises(StoreError):
                self.store.put(metadata, "text", stamp=STAMP)
        self.put()
        path = self.root / ".sky/kb/manifest.json"
        body = json.loads(path.read_text(encoding="utf-8"))
        body["schema_version"] = 2
        path.write_text(json.dumps(body), encoding="utf-8")
        with self.assertRaisesRegex(StoreError, "schema version"):
            self.store.manifest()

    def test_digest_tampering_and_manifest_path_tampering_refuse(self):
        entry = self.put()
        (self.root / entry["path"]).write_text("tampered", encoding="utf-8")
        with self.assertRaisesRegex(StoreError, "digest mismatch"):
            self.store.get(entry["id"])
        manifest = self.store.manifest()
        manifest["documents"][entry["id"]]["path"] = "../escape.md"
        (self.root / ".sky/kb/manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaisesRegex(StoreError, "path mismatch"):
            self.store.manifest()

    def test_redaction_gate_refuses_secret_shaped_content(self):
        with self.assertRaisesRegex(StoreError, "redaction gate"):
            self.put("ghp_" + "A" * 35)

    def test_yaml_frontmatter_file_is_validated_and_missing_frontmatter_refuses(self):
        path = self.root / "input.md"
        path.write_text("---\ntype: doc\ntitle: Fixture\nproject: fixture\n---\nBody\n", encoding="utf-8", newline="\n")
        self.assertEqual(self.store.get(self.store.put_file("input.md", stamp=STAMP)["id"])["body"], "Body\n")
        path.write_text("# No frontmatter", encoding="utf-8")
        with self.assertRaisesRegex(StoreError, "no frontmatter"):
            self.store.put_file("input.md", stamp=STAMP)

    def test_published_decision_and_knowledge_schemas_match_runtime(self):
        schemas = Path(__file__).resolve().parents[2] / "schemas"
        for name, expected in (("decision", kbstore.DECISION_SCHEMA), ("knowledge", kbstore.KNOWLEDGE_SCHEMA)):
            self.assertEqual(json.loads((schemas / f"{name}.schema.json").read_text(encoding="utf-8")), expected)

    def test_crlf_body_round_trip_checks_exact_revision_bytes(self):
        entry = self.put("first\r\nsecond\r\n")
        self.assertEqual(self.store.get(entry["id"])["body"], "first\r\nsecond\r\n")

    def test_duplicate_frontmatter_keys_and_non_mapping_manifest_refuse(self):
        with self.assertRaisesRegex(StoreError, "duplicate frontmatter"):
            kbstore.parse_document('---\n{"type":"doc","type":"decision"}\n---\ntext')
        path = self.root / ".sky/kb/manifest.json"
        path.parent.mkdir(parents=True)
        path.write_text("[]", encoding="utf-8")
        with self.assertRaisesRegex(StoreError, "manifest must be a mapping"):
            self.store.manifest()

    def test_empty_search_returns_zero_hits(self):
        self.assertEqual(kbserve.Server(self.store).search("http"), [])

    def test_search_is_ranked_bounded_deterministic_and_cited(self):
        self.put("http retry " * 8, id="a", title="HTTP retry")
        self.put("http clients", id="b", title="Clients")
        server = kbserve.Server(self.store)
        hits = server.search("http retry", k=2)
        self.assertEqual(len(hits), 2)
        self.assertEqual(hits[0]["id"], "a")
        self.assertEqual(hits, server.search("http retry", k=2))
        self.assertTrue(all(len(h["excerpt"]) <= 16 and h["citation"].startswith("id:") for h in hits))
        self.assertEqual(server.search("http", types=["decision"]), [])

    def test_graph_depth_type_filter_cycles_and_dangling_edges(self):
        self.put(id="a", relates_to=["b", "missing"])
        self.put(id="b", type="adr", relates_to=["c"])
        self.put(id="c", relates_to=["a"])
        result = kbserve.Server(self.store).neighbours("a", depth=3, type="adr")
        self.assertEqual([hit["id"] for hit in result["hits"]], ["b"])
        self.assertIn("a: unresolved relates_to missing", result["findings"])

    def test_decision_aliases_applicability_current_revision_and_project_isolation(self):
        self.save_decision()
        server = kbserve.Server(self.store)
        hits = server.decisions_find("HTTP client", "fixture", "module", evidence_revision="checkout-1")
        self.assertTrue(hits[0]["applicable"])
        self.assertFalse(server.decisions_find("HTTP client", "fixture", "module")[0]["applicable"])
        self.assertFalse(server.decisions_find("HTTP client", "fixture", "module", evidence_revision="old")[0]["applicable"])
        self.assertEqual(server.decisions_find("HTTP client", "other", "."), [])
        self.assertEqual(server.decisions_find("transport protocol", "fixture", "."), [])

    def test_conflicting_decisions_tie_without_recency_winning_and_supersession_marks_old(self):
        self.save_decision()
        other = {**self.decision(), "id": "decision-other", "answer": "RPC"}
        self.save_decision(other)
        server = kbserve.Server(self.store)
        hits = server.decisions_find("HTTP client", "fixture", ".", evidence_revision="checkout-1")
        self.assertEqual(len(hits), 2)
        self.assertEqual(hits[0]["score"], hits[1]["score"])
        self.assertTrue(all(hit["applicable"] for hit in hits))
        other["supersedes"] = ["decision-http"]
        self.save_decision(other)
        hits = server.decisions_find("HTTP client", "fixture", ".", evidence_revision="checkout-1")
        self.assertFalse(next(h for h in hits if h["id"] == "decision-http")["applicable"])

    def test_stdio_initialize_list_call_notifications_and_malformed_frames(self):
        requests = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-03-26"}},
                    {"jsonrpc": "2.0", "method": "notifications/initialized"},
                    {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
                    {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "search", "arguments": {"query": "empty"}}}]
        output = io.StringIO()
        kbserve.serve(self.store, io.StringIO("\n".join(json.dumps(r) for r in requests) + "\ninvalid\n"), output)
        frames = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual(len(frames), 4)
        self.assertEqual(frames[0]["result"]["protocolVersion"], "2025-03-26")
        self.assertEqual(len(frames[1]["result"]["tools"]), 5)
        self.assertFalse(frames[2]["result"]["isError"])
        self.assertEqual(frames[3]["error"]["code"], -32700)

    def test_mcp_unknown_method_tool_and_bad_arguments_report_errors(self):
        server = kbserve.Server(self.store)
        self.assertEqual(server.handle({"jsonrpc": "2.0", "id": 1, "method": "unknown"})["error"]["code"], -32601)
        for name, args in (("unknown", {}), ("search", {"query": "x", "k": 0}), ("search", {"query": "x", "extra": 1})):
            result = server.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": name, "arguments": args}})
            self.assertTrue(result["result"]["isError"])

    def test_mcp_writes_need_runtime_stamp_and_decisions_cannot_forge_confirmation(self):
        arguments = {"metadata": self.metadata(), "body": "local write"}
        with self.assertRaisesRegex(StoreError, "runtime stamp"):
            kbserve.Server(self.store).call("ingest", arguments)
        server = kbserve.Server(self.store, stamp=STAMP)
        self.assertIn("id", server.call("ingest", arguments))
        with self.assertRaisesRegex(StoreError, "confirmation"):
            server.call("decisions_record", {"metadata": self.decision(), "body": "text"})
        with self.assertRaisesRegex(StoreError, "decisions_record"):
            server.call("ingest", {"metadata": self.decision(), "body": "text"})
        server = kbserve.Server(self.store, stamp=STAMP, confirm=lambda meta: APPROVAL)
        self.assertEqual(server.call("decisions_record", {"metadata": self.decision(), "body": "text"})["id"], "decision-http")
