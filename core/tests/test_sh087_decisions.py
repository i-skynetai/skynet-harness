"""Offline decision lifecycle, CLI, MCP and policy contract tests."""
import json
import io
from contextlib import redirect_stdout, redirect_stderr
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sky import cli, kbserve, schemas
from sky.decisions import (DecisionStore, EVENT_KINDS, find, list_decisions,
                           propose, show, transition)
from sky.kbstore import Store, StoreError, document_text
from sky.recorder import Run


class Decisions(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.env = patch.dict(os.environ, {}, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.store = DecisionStore(self.root)
        self.run = Run.start(role="runtime", task="decide", kb="local", agent_id="runtime",
                             root=self.root / ".sky/runs")

    def proposal(self, name="cache", scope=None, *, title=None, question=None, options=None):
        source = name + ".md"
        metadata = {"title": title or name + " cache choice", "question": question or "Which cache?",
                    "options": options or ["memory", "disk"], "chosen_option": "memory",
                    "rationale": "Bounded process lifetime", "evidence_revision": "rev1",
                    "scope": scope or ["."]}
        (self.root / source).write_bytes(document_text(metadata, "# Cache\nEvidence\n").encode())
        return propose(self.store, source, run=self.run)["id"]

    def accept(self, record_id):
        return transition(self.store, record_id, "accept", run=self.run, confirm=lambda _: True)

    def test_propose_stores_proposed_without_approval(self):
        record = show(self.store, self.proposal())["metadata"]
        self.assertEqual(record["status"], "proposed")
        self.assertNotIn("approval", record)
        self.assertEqual(record["sky_run"], self.run.run_id)

    def test_accept_writes_runtime_evidence_and_new_revision_keeping_id(self):
        record_id = self.proposal()
        old = show(self.store, record_id)
        entry = self.accept(record_id)
        meta = show(self.store, record_id)["metadata"]
        self.assertEqual(entry["id"], record_id)
        self.assertNotEqual(entry["digest"], old["entry"]["digest"])
        self.assertTrue((self.root / old["entry"]["path"]).exists())
        self.assertEqual(meta["approval"]["decision_digest"], old["entry"]["digest"])
        self.assertEqual(meta["approval"]["session"], self.run.run_id)
        self.assertEqual(meta["approval"]["method"], "sky kb decide accept")
        self.assertEqual(meta["version"], 2)

    def test_agent_stamped_approval_refused_at_put(self):
        record = show(self.store, self.proposal())
        record["metadata"]["approval"] = {"actor": "agent"}
        for store in (self.store, Store(self.root)):
            with self.assertRaisesRegex(StoreError, "runtime-owned"):
                store.put(record["metadata"], record["body"], stamp=self.run.stamp())

    def test_accept_under_sky_launched_refused_even_empty(self):
        record_id = self.proposal()
        with patch.dict(os.environ, {"SKY_LAUNCHED": ""}):
            with self.assertRaisesRegex(StoreError, "people only"):
                self.accept(record_id)
        self.assertEqual(show(self.store, record_id)["metadata"]["status"], "proposed")

    def test_non_runtime_transition_refused(self):
        record_id = self.proposal()
        self.run.agent_id = "developer"
        with self.assertRaisesRegex(StoreError, "runtime run"):
            self.accept(record_id)

    def test_declined_confirmation_writes_no_revision(self):
        record_id = self.proposal()
        before = self.store.manifest()
        with self.assertRaisesRegex(StoreError, "declined"):
            transition(self.store, record_id, "accept", run=self.run, confirm=lambda _: False)
        self.assertEqual(self.store.manifest(), before)

    def test_changed_revision_since_confirmation_refused(self):
        record_id = self.proposal()
        def change(_):
            record = show(self.store, record_id)
            self.store.put(record["metadata"], record["body"] + "Changed\n", stamp=self.run.stamp())
            return True
        with self.assertRaisesRegex(StoreError, "changed since confirmation"):
            transition(self.store, record_id, "accept", run=self.run, confirm=change)
        self.assertEqual(show(self.store, record_id)["metadata"]["status"], "proposed")

    def test_supersede_links_both_ways_and_old_is_not_current(self):
        old, new = self.proposal("old"), self.proposal("new")
        self.accept(old)
        self.accept(new)
        transition(self.store, old, "supersede", by=new, run=self.run, confirm=lambda _: True)
        self.assertEqual(show(self.store, old)["metadata"]["superseded_by"], [new])
        self.assertEqual(show(self.store, new)["metadata"]["supersedes"], [old])
        hit = next(hit for hit in find(self.store, "cache", evidence_revision="rev1") if hit["id"] == old)
        self.assertFalse(hit["current"])
        self.assertFalse(hit["closes"])

    def test_supersede_requires_accepted_replacement(self):
        old, new = self.proposal("old"), self.proposal("new")
        self.accept(old)
        with self.assertRaisesRegex(StoreError, "different accepted"):
            transition(self.store, old, "supersede", by=new, run=self.run, confirm=lambda _: True)

    def test_supersession_failure_keeps_manifest_and_both_links(self):
        old, new = self.proposal("old"), self.proposal("new")
        self.accept(old)
        self.accept(new)
        before = self.store.manifest()
        atomic = self.store._atomic
        calls = []
        def fail(path, text):
            calls.append(path)
            if len(calls) == 2:
                raise OSError("simulated failed revision")
            atomic(path, text)
        with patch.object(self.store, "_atomic", side_effect=fail):
            with self.assertRaises(OSError):
                transition(self.store, old, "supersede", by=new, run=self.run, confirm=lambda _: True)
        self.assertEqual(self.store.manifest(), before)

    def test_find_ranks_question_title_options_and_aliases(self):
        # The second record matches the query only through its options, so a
        # tie would mean the title and question were never scored.
        first = self.proposal("cache")
        second = self.proposal("unrelated", title="Storage choice", question="Where do results live?",
                               options=["memory", "disk cache"])
        hits = find(self.store, "cache")
        self.assertEqual(hits[0]["id"], first)
        self.assertGreater(hits[0]["score"], hits[1]["score"])
        self.assertEqual({hit["id"] for hit in hits}, {first, second})

    def test_closes_only_accepted_current_in_scope_with_verified_revision(self):
        record_id = self.proposal()
        self.assertFalse(find(self.store, "cache", evidence_revision="rev1")[0]["closes"])
        self.accept(record_id)
        self.assertTrue(find(self.store, "cache", evidence_revision="rev1")[0]["closes"])
        self.assertFalse(find(self.store, "cache")[0]["closes"])
        self.assertFalse(find(self.store, "cache", evidence_revision="rev2")[0]["closes"])

    def test_out_of_scope_accepted_decision_does_not_close(self):
        record_id = self.proposal(scope=["core"])
        self.accept(record_id)
        hit = find(self.store, "cache", scope="docs", evidence_revision="rev1")[0]
        self.assertFalse(hit["in_scope"])
        self.assertFalse(hit["closes"])

    def test_rejected_never_closes(self):
        record_id = self.proposal()
        transition(self.store, record_id, "reject", run=self.run, confirm=lambda _: True)
        self.assertEqual(show(self.store, record_id)["metadata"]["status"], "rejected")
        self.assertFalse(find(self.store, "cache", evidence_revision="rev1")[0]["closes"])

    def test_list_and_show_output_shapes(self):
        record_id = self.proposal(scope=["core"])
        self.assertEqual(set(show(self.store, record_id)), {"metadata", "body", "entry"})
        self.assertEqual(len(list_decisions(self.store, status="proposed", scope="core/a.py")), 1)
        self.assertEqual(list_decisions(self.store, status="accepted"), [])

    def test_event_kinds_emitted_and_approval_matches_event(self):
        old, new = self.proposal("old"), self.proposal("new")
        rejected = self.proposal("rejected")
        self.accept(old)
        self.accept(new)
        transition(self.store, rejected, "reject", run=self.run, confirm=lambda _: True)
        transition(self.store, old, "supersede", by=new, run=self.run, confirm=lambda _: True)
        events = [json.loads(line) for line in (self.run.directory / "events.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertTrue(set(EVENT_KINDS.values()) <= {event["kind"] for event in events})
        approval = show(self.store, old)["metadata"]["approval"]
        self.assertEqual(events[-1]["event_id"], approval["event_id"])

    def test_missing_options_or_choice_refused(self):
        (self.root / "plain.md").write_bytes(b"# Question\nNo choice yet\n")
        with self.assertRaises(StoreError):
            propose(self.store, "plain.md", run=self.run)

    def test_plain_markdown_sections_propose_without_inventing_choice(self):
        (self.root / "plain.md").write_bytes(b"# Cache\n## Question\nWhich cache?\n## Options\n- memory\n- disk\n## Chosen option\nmemory\n## Rationale\nSmall lifetime\n")
        record_id = propose(self.store, "plain.md", run=self.run)["id"]
        self.assertEqual(show(self.store, record_id)["metadata"]["chosen_option"], "memory")

    def test_path_escape_refused(self):
        with self.assertRaises(StoreError):
            propose(self.store, "../outside.md", run=self.run)

    def test_accepted_decision_cannot_be_reset_to_proposed(self):
        record_id = self.proposal()
        self.accept(record_id)
        with self.assertRaisesRegex(StoreError, "approved decision"):
            self.proposal()

    def test_invalid_scope_and_limit_refused(self):
        self.proposal()
        with self.assertRaises(StoreError):
            find(self.store, "cache", scope="../outside")
        with self.assertRaises(StoreError):
            find(self.store, "cache", k=0)

    def test_model_approval_in_proposal_file_refused(self):
        (self.root / "forged.md").write_bytes(document_text({"approval": {"actor": "agent"}}, "# Forged\n").encode())
        with self.assertRaisesRegex(StoreError, "runtime-owned"):
            propose(self.store, "forged.md", run=self.run)

    def command(self, *args, stdin=""):
        out, err = io.StringIO(), io.StringIO()
        with patch.dict(os.environ, {"SKY_STATE_DIR": str(self.root / ".state")}), \
                patch("sys.stdin", io.StringIO(stdin)), redirect_stdout(out), redirect_stderr(err):
            code = cli.main(["kb", "decide", *args, "--root", str(self.root)])
        return code, out.getvalue(), err.getvalue()

    def test_cli_propose_from_stdin_and_accept_yes(self):
        text = "# Cache\n## Question\nWhich cache?\n## Options\n- memory\n- disk\n## Chosen option\nmemory\n## Rationale\nSmall lifetime\n"
        code, output, error = self.command("propose", "--from", "-", stdin=text)
        self.assertEqual(code, 0, error)
        record_id = list_decisions(self.store)[0]["metadata"]["id"]
        self.assertIn(record_id, output)
        code, _, error = self.command("accept", record_id, "--yes")
        self.assertEqual(code, 0, error)
        self.assertEqual(show(self.store, record_id)["metadata"]["approval"]["method"], "sky kb decide accept")

    def test_cli_accept_under_sky_launched_refused(self):
        record_id = self.proposal()
        with patch.dict(os.environ, {"SKY_LAUNCHED": "1"}):
            code, _, error = self.command("accept", record_id, "--yes")
        self.assertEqual(code, 1)
        self.assertIn("people only", error)

    def test_cli_list_and_show(self):
        record_id = self.proposal()
        code, output, error = self.command("list", "--status", "proposed", "--scope", ".")
        self.assertEqual(code, 0, error)
        self.assertEqual(json.loads(output)[0]["metadata"]["id"], record_id)
        code, output, error = self.command("show", record_id)
        self.assertEqual(code, 0, error)
        self.assertEqual(json.loads(output)["metadata"]["id"], record_id)

    def test_cli_put_refuses_forged_approval(self):
        record = show(self.store, self.proposal())
        record["metadata"]["approval"] = {"actor": "agent"}
        path = self.root / "forged.md"
        path.write_bytes(document_text(record["metadata"], record["body"]).encode())
        with patch.dict(os.environ, {"SKY_STATE_DIR": str(self.root / ".state")}), \
                redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()) as error:
            code = cli.main(["kb", "put", str(path), "--root", str(self.root)])
        self.assertEqual(code, 1)
        self.assertIn("runtime-owned", error.getvalue())

    def test_event_kinds_are_published(self):
        repo = Path(__file__).resolve().parents[2]
        published = json.loads((repo / "schemas/run-event.schema.json").read_text(encoding="utf-8"))
        self.assertTrue(set(EVENT_KINDS.values()) <= set(schemas.EVENT_KINDS))
        self.assertEqual(published["x-known-kinds"], list(schemas.EVENT_KINDS))

    def test_mcp_find_returns_closes_without_required_project_argument(self):
        record_id = self.proposal()
        self.accept(record_id)
        hits = kbserve.Server(self.store).call("decisions_find", {
            "question": "cache", "scope": ".", "evidence_revision": "rev1"})
        self.assertTrue(hits[0]["closes"])
        self.assertTrue(hits[0]["applicable"])

    def test_decide_skill_contract_and_read_only_grants(self):
        from sky.policy import Policy
        repo = Path(__file__).resolve().parents[2]
        skill = (repo / "plugin/skills/decide/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("Use when the user asks", skill)
        for term in ("SKILLS.md", "CONFIG.md", "Check your work", "verify", "evidence"):
            self.assertIn(term, skill)
        self.assertNotIn("mcp__sky_kb__", skill)
        policy = Policy.load(repo / "plugin/policy.yaml")
        self.assertNotIn("Write", policy.skills["decide"]["tools"])
        for role in ("architect", "developer"):
            self.assertIn("decide", policy.skills_for(role))
