"""The four rules a skill obeys here, from `plugin/SKILLS.md`.

Each rule is a real failure this project had before the rule existed: code
re-derived every run, descriptions the host had to guess between, corrections
that died with the session, and skills that handed over a first draft.

The checks matter more than the prose, so every one below is driven against a
relapse as well as the good case — three retirement rules once passed for
months while matching nothing at all.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sky import hosts, selftest, setup  # noqa: E402
from sky.policy import Policy  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
PLUGIN = REPO / "plugin"
POLICY = Policy.load(PLUGIN / "policy.yaml")
A_PROFILE = setup.Profile.from_dict({
    "name": "t", "mcp_url": "https://stub.invalid/mcp/", "tenant_code": "ABCD2345",
    "ontology": "o", "instance": "example-kb"})


def a_plugin(**skills) -> Path:
    root = Path(tempfile.mkdtemp())
    for d in ("core", "plugin", "schemas", "hosts", "docs"):
        (root / d).mkdir()
    for name, body in skills.items():
        d = root / "plugin" / "skills" / name
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text(body, encoding="utf-8")
    return root


CLEAR = ('---\nname: c\ndescription: Builds a carousel. Use when the user asks '
         'for "a carousel".\n---\nBefore returning, verify against the rendered image.\n')


class Rule1_SavedCodeNotRederived(unittest.TestCase):
    def test_the_contract_ships(self):
        self.assertTrue((PLUGIN / "SKILLS.md").is_file())

    def test_the_renderer_exists_and_runs(self):
        script = PLUGIN / "scripts" / "render-diagram.py"
        self.assertTrue(os.access(script, os.X_OK))
        root = Path(tempfile.mkdtemp())
        (root / "d.svg").write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" width="80" height="40">'
            '<text x="4" y="24">hi</text></svg>')
        out = subprocess.run([str(script), str(root / "d.svg"),
                              "--out-dir", str(root / "images")],
                             capture_output=True, text=True, timeout=120)
        # 0 = svg and png, 3 = svg only because no converter is installed.
        self.assertIn(out.returncode, (0, 3), out.stderr)
        self.assertTrue((root / "images" / "d.svg").is_file())

    def test_it_says_so_rather_than_claiming_a_png_it_lacks(self):
        body = (PLUGIN / "scripts" / "render-diagram.py").read_text()
        self.assertIn("not produced", body)
        self.assertIn("no SVG-to-PNG converter found", body)

    def test_the_skills_that_draw_call_it_instead_of_writing_one(self):
        """The property, not a sentence: the skill names the script and spells
        out no converter of its own. Asserting one phrase is how a test passes
        while the thing it names has moved."""
        converters = ("qlmanage", "mmdc", "rsvg-convert", "inkscape")
        for skill in ("design", "adr"):
            body = (PLUGIN / "skills" / skill / "SKILL.md").read_text()
            with self.subTest(skill=skill):
                self.assertIn("render-diagram.py", body)
                for tool in converters:
                    self.assertNotIn(tool, body,
                                     f"{skill} spells out {tool} instead of "
                                     f"letting the script own it")

    def test_a_package_carries_the_scripts_and_not_just_the_procedure(self):
        os.environ["SKY_PLUGIN_ROOT"] = str(PLUGIN)
        try:
            files = hosts.build("codex", POLICY, profile=A_PROFILE).files
        finally:
            os.environ.pop("SKY_PLUGIN_ROOT", None)
        self.assertIn("scripts/render-diagram.py", files)
        self.assertIn("skills/SKILLS.md", files)


class Rule2_ASkillNobodyCanFind(unittest.TestCase):
    def test_two_vague_descriptions_are_caught(self):
        """The video's own example: "helps with content" against "creates
        marketing assets"."""
        root = a_plugin(
            a='---\nname: a\ndescription: Helps with content.\n---\nx\n',
            b='---\nname: b\ndescription: Creates marketing assets.\n---\nx\n')
        self.assertFalse(selftest.check_skills_can_be_found(root).passed)

    def test_two_skills_claiming_one_trigger_are_caught(self):
        clash = ('---\nname: d\ndescription: Other. Use when the user asks for '
                 '"a carousel".\n---\nverify\n')
        result = selftest.check_skills_can_be_found(a_plugin(c=CLEAR, d=clash))
        self.assertFalse(result.passed)
        self.assertIn("both claim the trigger", result.problems[0])

    def test_a_clear_one_passes(self):
        self.assertTrue(selftest.check_skills_can_be_found(a_plugin(c=CLEAR)).passed)

    def test_a_description_that_says_when_without_the_words_use_when(self):
        """`ingest` says "Use only when the user explicitly asks"; an earlier
        version of this rule tested one fixed wording and flagged it."""
        body = ('---\nname: e\ndescription: Pushes a document. Use only when the '
                'user explicitly asks — "ingest this file".\n---\nverify\n')
        self.assertTrue(selftest.check_skills_can_be_found(a_plugin(e=body)).passed)

    def test_the_real_plugin_has_no_collisions(self):
        result = selftest.check_skills_can_be_found(REPO)
        self.assertTrue(result.passed, result.problems)


class Rule3_ACorrectionThatLastsLongerThanTheSession(unittest.TestCase):
    def test_learn_classifies_where_a_fix_belongs(self):
        body = (PLUGIN / "skills" / "learn" / "SKILL.md").read_text()
        self.assertIn("smallest durable place", body)
        for where in ("SKILL.md", "reference/", "scripts/"):
            with self.subTest(where=where):
                self.assertIn(where, body)

    def test_it_says_to_re_run_and_check_the_fix_held(self):
        body = (PLUGIN / "skills" / "learn" / "SKILL.md").read_text()
        self.assertIn("re-run the same task", body.lower())

    def test_a_skill_change_is_still_code_and_stops_for_a_person(self):
        body = (PLUGIN / "skills" / "learn" / "SKILL.md").read_text()
        self.assertIn("is **code**", body)

    def test_sync_reads_the_scripts_a_skill_brings_with_it(self):
        body = (PLUGIN / "skills" / "sync" / "SKILL.md").read_text()
        self.assertIn("not only `SKILL.md`", body)
        self.assertIn("runs without anyone", body)


class Rule4_YourFirstLookIsNotTheAgentsFirstLook(unittest.TestCase):
    def test_a_skill_that_returns_its_first_draft_is_caught(self):
        body = ('---\nname: e\ndescription: Writes a thing. Use when the user '
                'asks to "write a thing".\n---\nWrite it and hand it over.\n')
        result = selftest.check_skills_verify_before_returning(a_plugin(e=body))
        self.assertFalse(result.passed)
        self.assertIn("returns its first attempt", result.problems[0])

    def test_every_producing_skill_in_the_real_plugin_checks_its_work(self):
        result = selftest.check_skills_verify_before_returning(REPO)
        self.assertTrue(result.passed, result.problems)

    def test_the_evidence_is_specific_to_the_skill_not_boilerplate(self):
        """Rule 4 is about evidence outside the draft, which differs per job —
        a shared paragraph would be the label-instead-of-enforcement failure
        again."""
        wanted = {
            "ingest": "jobs.status",          # the count is in the output
            "build": "the hand's prose",      # read the record, not the summary
            "review": "file and a line",
            "test": "baseline",
            "setup": "sky setup doctor",
            "ship": "composed a command line",
        }
        for skill, phrase in wanted.items():
            with self.subTest(skill=skill):
                body = (PLUGIN / "skills" / skill / "SKILL.md").read_text()
                self.assertIn(phrase, body)

    def test_reading_your_own_output_is_named_as_not_verification(self):
        body = (PLUGIN / "SKILLS.md").read_text()
        self.assertIn("is not verification", body)


class TheChecksAreInTheSuiteThatRuns(unittest.TestCase):
    def test_both_are_wired(self):
        for check in (selftest.check_skills_can_be_found,
                      selftest.check_skills_verify_before_returning):
            with self.subTest(check=check.__name__):
                self.assertIn(check, selftest.CHECKS)


if __name__ == "__main__":
    unittest.main(verbosity=2)
