"""Tests for the four role agent files.

An agent's `tools:` line **is** its authority — what is not listed is not
visible to it. That makes the line load-bearing, and it makes a typo silent:
the agent simply cannot do something, and nobody finds out until a task fails
halfway through.

So the line is generated from `policy.yaml` rather than kept in step by hand,
and the first test here is the drift check that proves it.

What these tests cannot do is check the prose. A test can say the reviewer file
mentions its verdict rule; it cannot say the instructions are good. Whether the
tool names are real is checked against the **live servers** by
`scripts/check-allowlists.py`, not here — a fixture of tool names would just be
a third copy of the thing that drifts.
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sky.policy import Policy  # noqa: E402

PLUGIN = Path(__file__).resolve().parents[2] / "plugin"
AGENTS = PLUGIN / "agents"
POLICY = Policy.load(PLUGIN / "policy.yaml")

#: Agents a skill delegates to. They are not roles and `sky build` cannot
#: launch them, so they are not held to the policy's role list.
HELPERS = {"context-retriever", "validator"}


def front_matter(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return {}
    block = text.split("---\n", 2)[1]
    out = {}
    for line in block.splitlines():
        if ": " in line:
            key, value = line.split(": ", 1)
            out[key.strip()] = value.strip()
    return out


class TheFilesMatchThePolicy(unittest.TestCase):
    """The drift check. Everything else here is secondary to this."""

    def test_every_role_has_an_agent_file(self):
        for role in POLICY.roles_named():
            with self.subTest(role=role):
                self.assertTrue((AGENTS / f"{role}.md").is_file(),
                                f"policy.yaml defines {role} with no agent file")

    def test_no_agent_file_claims_a_role_the_policy_does_not_have(self):
        """An orphan would be launchable by name with nothing governing it."""
        files = {p.stem for p in AGENTS.glob("*.md")} - HELPERS
        self.assertEqual(files, set(POLICY.roles_named()))

    def test_the_tools_line_is_exactly_what_the_policy_says(self):
        drifted = POLICY.sync_agents(AGENTS, write=False)
        self.assertEqual(drifted, [],
                         "run `sky policy sync-agents` — the agent files and "
                         "the policy disagree about what these roles may do")

    def test_no_file_still_carries_the_placeholder(self):
        for path in sorted(AGENTS.glob("*.md")):
            with self.subTest(agent=path.stem):
                self.assertNotIn("PLACEHOLDER", path.read_text())


class TheBoundaryIsVisibleInTheFile(unittest.TestCase):
    """A reader of the file should be able to see the rule without the policy."""

    def test_a_read_only_role_lists_no_shell_and_no_editing(self):
        for role in POLICY.roles_named():
            if POLICY.decide(role, "repo.edit").allowed:
                continue
            tools = front_matter(AGENTS / f"{role}.md")["tools"].split(", ")
            with self.subTest(role=role):
                self.assertNotIn("Edit", tools)
                self.assertNotIn("Write", tools)
                self.assertFalse([t for t in tools if t.startswith("Bash")],
                                 f"{role} can run commands")

    def test_the_developer_can_commit_and_cannot_push(self):
        tools = front_matter(AGENTS / "developer.md")["tools"]
        self.assertIn("Bash(git commit:*)", tools)
        self.assertNotIn("push", tools)

    def test_no_role_holds_a_bare_bash(self):
        """`Bash` without a pattern is every command, which is no allowlist."""
        for role in POLICY.roles_named():
            tools = front_matter(AGENTS / f"{role}.md")["tools"].split(", ")
            with self.subTest(role=role):
                self.assertNotIn("Bash", tools)


class TheFrontMatterIsUsable(unittest.TestCase):
    def test_the_name_matches_the_filename(self):
        """The launcher passes `--agent sky:<role>`; a mismatch selects nothing."""
        for path in sorted(AGENTS.glob("*.md")):
            with self.subTest(agent=path.stem):
                self.assertEqual(front_matter(path).get("name"), path.stem)

    def test_every_agent_describes_when_to_use_it(self):
        """The description is how a host decides to delegate to it at all."""
        for path in sorted(AGENTS.glob("*.md")):
            description = front_matter(path).get("description", "")
            with self.subTest(agent=path.stem):
                self.assertGreater(len(description), 80,
                                   "too short to route on")

    def test_the_description_says_what_the_agent_may_not_do(self):
        """A caller reading only the description should learn the boundary."""
        for path in sorted(AGENTS.glob("*.md")):
            description = front_matter(path).get("description", "").lower()
            with self.subTest(agent=path.stem):
                self.assertTrue(
                    any(word in description
                        for word in ("never", "cannot", "read-only", "no outward")),
                    f"{path.stem}'s description does not say what it will not do")


class TheJudgingAgentsStateTheirRule(unittest.TestCase):
    """A verdict that can be softened is not a gate."""

    JUDGES = ("reviewer", "architect", "security")

    def test_each_offers_exactly_two_verdicts(self):
        for role in self.JUDGES:
            text = (AGENTS / f"{role}.md").read_text()
            with self.subTest(role=role):
                self.assertIn("VERDICT: APPROVED", text)
                self.assertIn("VERDICT: BLOCKED", text)

    def test_each_says_the_verdict_is_mechanical(self):
        for role in self.JUDGES:
            text = (AGENTS / f"{role}.md").read_text().lower()
            with self.subTest(role=role):
                self.assertIn("if and only if", text,
                              "the blocker rule is not stated mechanically")

    def test_each_requires_evidence_rather_than_assertion(self):
        for role in self.JUDGES:
            text = (AGENTS / f"{role}.md").read_text()
            with self.subTest(role=role):
                self.assertIn("Evidence:", text)
                self.assertIn("OPEN", text)


class TheSplitIsFinished(unittest.TestCase):
    def test_the_combined_agent_is_gone(self):
        self.assertFalse((AGENTS / "architect-reviewer.md").exists())

    def test_nothing_still_refers_to_it(self):
        """A stale reference selects an agent that no longer exists."""
        root = Path(__file__).resolve().parents[2]
        stale = []
        for path in list(root.glob("plugin/**/*.md")) + \
                list(root.glob("plugin/**/*.yaml")) + \
                list(root.glob("scripts/*.py")):
            if "architect-reviewer" in path.read_text(encoding="utf-8"):
                stale.append(str(path.relative_to(root)))
        self.assertEqual(stale, [])


class TheSecurityAgentKnowsWhatToLookAt(unittest.TestCase):
    """It is the only agent whose subject is this system itself."""

    def setUp(self) -> None:
        self.text = (AGENTS / "security.md").read_text()

    def test_it_watches_the_files_that_decide_permission(self):
        for named in ("policy.yaml", "agents/*.md", "kb-map.json"):
            with self.subTest(file=named):
                self.assertIn(named, self.text)

    def test_it_watches_what_runs_with_credentials(self):
        for named in (".github/workflows/", "azure-pipelines.yml", ".gitlab-ci.yml"):
            with self.subTest(file=named):
                self.assertIn(named, self.text)

    def test_it_is_told_not_to_print_the_secret_it_reports(self):
        """Findings end up in a log, and a log is not where a credential goes."""
        self.assertIn("Never reproduce a secret", self.text)

    def test_it_is_warned_about_false_positives_too(self):
        """A scanner that flags documentation about tokens gets switched off."""
        self.assertIn("Flagging ordinary text", self.text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
