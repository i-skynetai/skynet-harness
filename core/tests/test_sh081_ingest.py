"""Sealed remote intents with a fake transport; source handovers always survive."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from sky import ingest, schemas
from sky.kbstore import StoreError, document_text


class Ingest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.stamp = {"sky_agent": "architect", "sky_run": "run-a", "sky_role": "architect", "sky_task": "task", "sky_kb": "local"}
        self.metadata = {"type": "handover", "title": "Cache handover", **self.stamp}
        self.source = self.root / "handover.md"
        self.source.write_bytes(document_text(self.metadata, "Cited public handover.\n").encode())
        self.engine = {"name": "remote-kb", "tenant": "public-demo"}
        self.run = Mock()

    def seal(self, **kwargs):
        values = {"engine": self.engine, "stamp": self.stamp}
        values.update(kwargs)
        return ingest.seal(self.root, "handover.md", **values)

    def relative(self, path):
        return path.relative_to(self.root).as_posix()

    def execute(self, path, **kwargs):
        values = dict(confirm=lambda _: True, transport=lambda *_: {"ok": True}, run=self.run, env={})
        values.update(kwargs)
        return ingest.ingest(self.root, self.relative(path), **values)

    def test_no_kb_makes_no_intent_and_keeps_handover(self):
        self.assertIsNone(self.seal(engine=None))
        self.assertTrue(self.source.exists())
        self.assertFalse((self.root / ".sky/outbox").exists())

    def test_seal_validates_stamp_and_payload_and_digest(self):
        path = self.seal()
        intent = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(intent["kind"], "kb.ingest")
        self.assertEqual(intent["payload_digest"], ingest.digest(intent["payload"]))
        self.assertEqual(intent["stamp"], self.stamp)
        self.assertIn(".sky/outbox", path.as_posix())

    def test_bad_stamp_or_payload_refused_at_sealing(self):
        for stamp in ({}, {**self.stamp, "sky_agent": "wrong"}):
            with self.assertRaises(StoreError):
                self.seal(stamp=stamp)
        self.metadata["type"] = "doc"
        self.source.write_bytes(document_text(self.metadata, "Body").encode())
        with self.assertRaises(StoreError):
            self.seal()

    def test_model_approval_in_handover_is_refused(self):
        self.metadata["approved_by"] = "model"
        self.source.write_bytes(document_text(self.metadata, "Body").encode())
        with self.assertRaisesRegex(StoreError, "approval"):
            self.seal()

    def test_secret_content_is_refused_without_copy_to_outbox(self):
        self.source.write_bytes(document_text(self.metadata, "api_key = 'a9F3v8K2m4R7t6Q1z5W0n8B3c2D9s7H4'\n").encode())
        with self.assertRaisesRegex(StoreError, "redaction"):
            self.seal()
        self.assertFalse((self.root / ".sky/outbox").exists())

    def test_render_prints_ingest_command_stamp_and_source(self):
        path = self.seal()
        rendered = ingest.render(self.root, self.relative(path))
        self.assertTrue(rendered["command"].startswith("sky ingest "))
        self.assertEqual(rendered["stamp"], self.stamp)
        self.assertEqual(rendered["source"], "handover.md")
        self.assertEqual(rendered["engine"], self.engine)

    def test_confirmation_refusal_never_calls_remote_or_deletes_local(self):
        path = self.seal()
        transport = Mock()
        before = self.source.read_bytes()
        with self.assertRaisesRegex(StoreError, "confirmation refused"):
            self.execute(path, confirm=lambda _: False, transport=transport)
        transport.assert_not_called()
        self.assertEqual(self.source.read_bytes(), before)
        self.assertNotIn("executed", json.loads(path.read_text()))

    def test_governed_agent_cannot_ingest(self):
        path = self.seal()
        transport = Mock()
        with self.assertRaisesRegex(StoreError, "person"):
            self.execute(path, env={"SKY_LAUNCHED": "1"}, transport=transport)
        transport.assert_not_called()

    def test_confirmed_fake_transport_records_success_and_keeps_handover(self):
        path = self.seal()
        requests = []
        transport = Mock(return_value={"ok": True, "record_id": "remote-record"})
        result = self.execute(path, confirm=lambda request: requests.append(request) or True, transport=transport)
        self.assertEqual(result["record_id"], "remote-record")
        self.assertEqual(requests[0]["payload_digest"], json.loads(path.read_text())["payload_digest"])
        transport.assert_called_once()
        self.assertTrue(json.loads(path.read_text())["executed"])
        self.assertTrue(self.source.exists())

    def test_payload_tamper_and_changed_source_refused(self):
        path = self.seal()
        intent = json.loads(path.read_text())
        intent["payload"]["body"] = "Tampered"
        path.write_bytes(json.dumps(intent).encode())
        with self.assertRaisesRegex(StoreError, "digest"):
            self.execute(path)
        path = self.seal()
        self.source.write_bytes(document_text(self.metadata, "Changed handover").encode())
        with self.assertRaisesRegex(StoreError, "changed since"):
            self.execute(path)

    def test_change_during_confirmation_and_replay_refused(self):
        path = self.seal()
        transport = Mock()
        def change(_):
            self.source.write_bytes(document_text(self.metadata, "New content").encode())
            return True
        with self.assertRaises(StoreError):
            self.execute(path, confirm=change, transport=transport)
        transport.assert_not_called()
        path = self.seal()
        self.execute(path)
        with self.assertRaisesRegex(StoreError, "pending"):
            self.execute(path)

    def test_transport_failure_records_refusal_and_preserves_source(self):
        path = self.seal()
        with self.assertRaisesRegex(StoreError, "transport"):
            self.execute(path, transport=lambda *_: {"ok": False})
        self.assertTrue(self.source.exists())
        self.assertTrue(any(call.args[0] == ingest.REFUSAL_EVENT for call in self.run.event.call_args_list))

    def test_source_containment_and_symlink_refused(self):
        with self.assertRaises(StoreError):
            ingest.seal(self.root, "../handover.md", engine=self.engine, stamp=self.stamp)
        link = self.root / "link.md"
        try:
            link.symlink_to(self.source)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable on this host")
        with self.assertRaises(StoreError):
            ingest.seal(self.root, "link.md", engine=self.engine, stamp=self.stamp)

    def test_ingest_schema_reuses_runtime_approval_ownership(self):
        self.assertEqual(ingest.INGEST_INTENT.by_name["approved_by"].owner, schemas.RUNTIME)
        self.assertEqual(ingest.INGEST_INTENT.by_name["stamp"].owner, schemas.RUNTIME)
