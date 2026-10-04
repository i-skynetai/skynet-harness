"""Tests for the policy, and for the file that actually ships.

Two halves. The first exercises the evaluator against small made-up policies,
so a rule can be broken on purpose and the failure seen. The second runs
against `plugin/policy.yaml` itself — the real file — because a policy that is
only ever tested against a fixture is a policy nobody has checked.

The rules worth breaking, and each is broken here on purpose:

    default deny            an action not listed is denied
    unknown is denied       a typo is not an allowance
    outward is never plain  a push cannot be granted by editing the file
    never beats everything  even a role that lists it
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sky.policy import ALLOW, DENY, NEEDS_HUMAN, Policy, PolicyError  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
SHIPPED = REPO / "plugin" / "policy.yaml"

MINIMAL = """
version: 1
actions:
  repo.read:
    outward: false
    description: "read files"
  repo.edit:
    outward: false
    description: "change files"
  push:
    outward: true
    broker: push_branch
    description: "publish a branch"
  pr.merge:
    outward: true
    description: "merge"
    never: "the last human checkpoint"
roles:
  developer:
    purpose: "build"
    tools: [Read, Edit]
    may:
      - repo.read
      - repo.edit
    needs_human:
      - push
  reviewer:
    purpose: "read"
    tools: [Read]
    may:
      - repo.read
guard:
  deny_commands:
    - pattern: "git push"
      action: push
      reason: "goes through ship"
"""


def a_policy(body: str = MINIMAL, tmp: Path | None = None) -> Policy:
    tmp = tmp or Path(tempfile.mkdtemp())
    path = tmp / "policy.yaml"
    path.write_text(body)
    return Policy.load(path)


class TheDefaultIsDeny(unittest.TestCase):
    def test_an_action_the_role_does_not_list_is_denied(self):
        d = a_policy().decide("reviewer", "repo.edit")
        self.assertEqual(d.outcome, DENY)
        self.assertFalse(d.allowed)
        self.assertIn("does not have", d.why)

    def test_an_action_the_policy_never_heard_of_is_denied(self):
        """A typo in a skill must not become an allowance."""
        d = a_policy().decide("developer", "repo.edti")
        self.assertEqual(d.outcome, DENY)
        self.assertIn("not an action this policy defines", d.why)

    def test_an_unknown_role_is_denied_and_told_what_exists(self):
        d = a_policy().decide("superuser", "repo.read")
        self.assertEqual(d.outcome, DENY)
        self.assertIn("developer", d.why)
        self.assertIn("reviewer", d.why)

    def test_what_is_listed_is_allowed(self):
        self.assertEqual(a_policy().decide("developer", "repo.edit").outcome, ALLOW)


class OutwardIsNeverAPlainAllow(unittest.TestCase):
    """The rule that stops `push` being granted by editing the file."""

    def test_an_outward_action_in_needs_human_is_not_permission(self):
        d = a_policy().decide("developer", "push")
        self.assertEqual(d.outcome, NEEDS_HUMAN)
        self.assertFalse(d.allowed, "needs-human was treated as permission")
        self.assertEqual(d.broker, "push_branch")

    def test_a_policy_that_grants_an_outward_action_directly_will_not_load(self):
        body = MINIMAL.replace("""    may:
      - repo.read
      - repo.edit
    needs_human:
      - push""", """    may:
      - repo.read
      - repo.edit
      - push""")
        with self.assertRaises(PolicyError) as caught:
            a_policy(body)
        self.assertIn("changes what other people can see", str(caught.exception))
        self.assertIn("needs_human", str(caught.exception))

    def test_and_if_such_a_policy_somehow_existed_the_action_still_would_not_pass(self):
        """Belt and braces: the evaluator does not trust the file either."""
        p = a_policy()
        p.roles["developer"]["may"] = ["repo.read", "repo.edit", "push"]
        p.roles["developer"]["needs_human"] = []
        d = p.decide("developer", "push")
        self.assertFalse(d.allowed)
        self.assertEqual(d.outcome, NEEDS_HUMAN)


class NeverBeatsEverything(unittest.TestCase):
    def test_an_action_marked_never_is_denied_to_every_role(self):
        for role in ("developer", "reviewer"):
            with self.subTest(role=role):
                d = a_policy().decide(role, "pr.merge")
                self.assertEqual(d.outcome, DENY)
                self.assertIn("human checkpoint", d.why)

    def test_a_policy_that_grants_a_never_action_will_not_load(self):
        body = MINIMAL.replace("""    needs_human:
      - push""", """    needs_human:
      - push
      - pr.merge""")
        with self.assertRaises(PolicyError) as caught:
            a_policy(body)
        self.assertIn("marked never", str(caught.exception))

    def test_and_the_evaluator_refuses_it_even_then(self):
        p = a_policy()
        p.roles["developer"]["needs_human"] = ["push", "pr.merge"]
        self.assertEqual(p.decide("developer", "pr.merge").outcome, DENY)


class TheLintCatchesDrift(unittest.TestCase):
    """A policy file is edited months later by someone who did not write it."""

    def test_a_read_only_role_holding_an_editing_tool_is_caught(self):
        body = MINIMAL.replace('''    tools: [Read]
    may:
      - repo.read''', '''    tools: [Read, Edit]
    may:
      - repo.read''')
        with self.assertRaises(PolicyError) as caught:
            a_policy(body)
        self.assertIn("writer wearing its name", str(caught.exception))

    def test_a_role_that_can_edit_with_no_tool_to_do_it_is_caught(self):
        body = MINIMAL.replace("    tools: [Read, Edit]\n", "    tools: [Read]\n", 1)
        with self.assertRaises(PolicyError) as caught:
            a_policy(body)
        self.assertIn("no tool to do it with", str(caught.exception))

    def test_an_action_that_does_not_exist_is_caught(self):
        body = MINIMAL.replace("      - repo.edit\n", "      - repo.edti\n", 1)
        with self.assertRaises(PolicyError) as caught:
            a_policy(body)
        self.assertIn("not a defined action", str(caught.exception))

    def test_a_guard_rule_with_no_reason_is_caught(self):
        body = MINIMAL.replace('      reason: "goes through ship"\n', "")
        with self.assertRaises(PolicyError) as caught:
            a_policy(body)
        self.assertIn("no reason", str(caught.exception))

    def test_a_role_with_no_tools_is_caught(self):
        body = MINIMAL.replace("    tools: [Read]\n", "", 1)
        with self.assertRaises(PolicyError) as caught:
            a_policy(body)
        self.assertIn("nothing to enforce", str(caught.exception))

    def test_an_action_in_both_lists_is_caught(self):
        body = MINIMAL.replace("""    needs_human:
      - push""", """    needs_human:
      - push
      - repo.read""")
        with self.assertRaises(PolicyError) as caught:
            a_policy(body)
        self.assertIn("both", str(caught.exception))

    def test_a_version_this_code_does_not_understand_is_caught(self):
        with self.assertRaises(PolicyError) as caught:
            a_policy(MINIMAL.replace("version: 1", "version: 9", 1))
        self.assertIn("version 9", str(caught.exception))

    def test_a_version_that_is_not_a_number_is_caught(self):
        with self.assertRaises(PolicyError) as caught:
            a_policy(MINIMAL.replace("version: 1", 'version: "one"', 1))
        self.assertIn("whole number", str(caught.exception))

    def test_a_broken_policy_does_not_load_partly(self):
        """Loading it "mostly" is how a file with one broken rule stays in use."""
        body = MINIMAL.replace("      - repo.edit\n", "      - repo.edti\n", 1)
        with self.assertRaises(PolicyError):
            a_policy(body)


class TheGuardsCommandRules(unittest.TestCase):
    def test_a_push_is_denied_with_a_reason(self):
        d = a_policy().denied_command("git push origin main")
        self.assertIsNotNone(d)
        self.assertEqual(d.action, "push")
        self.assertIn("ship", d.why)

    def test_extra_whitespace_does_not_evade_it(self):
        self.assertIsNotNone(a_policy().denied_command("git    push   origin  x"))

    def test_an_ordinary_command_is_left_alone(self):
        """Installing this must not make someone's own agent less capable."""
        for command in ("ls -la", "pytest tests/", "git status", "git log --oneline"):
            with self.subTest(command=command):
                self.assertIsNone(a_policy().denied_command(command))

    def test_the_most_specific_rule_wins_not_the_first_listed(self):
        """A denial recorded as the wrong thing is what an audit later reads.

        With first-match, `git push --force` was recorded as an ordinary push
        and `gh pr merge` as opening a pull request. Both were still denied —
        nothing got through — but the action in the record was wrong.
        """
        p = Policy.load(SHIPPED)
        self.assertEqual(p.denied_command("git push --force origin main").action,
                         "push")
        self.assertEqual(p.denied_command("gh pr merge 42").action, "pr.merge")
        self.assertEqual(p.denied_command("gh pr create").action, "pr.open")

    def test_the_policy_says_the_guard_fails_closed_in_a_run(self):
        self.assertTrue(Policy.load(SHIPPED).guard_fails_closed_in_run)


class TheFileThatActuallyShips(unittest.TestCase):
    """Tested directly, because a fixture cannot drift the way a real file can."""

    def setUp(self) -> None:
        self.policy = Policy.load(SHIPPED)

    def test_it_loads_and_lints_clean(self):
        self.assertEqual(self.policy.lint(), [])

    def test_it_has_the_four_roles(self):
        self.assertEqual(self.policy.roles_named(),
                         ("architect", "developer", "reviewer", "security"))

    def test_only_the_developer_can_edit(self):
        for role in ("reviewer", "architect", "security"):
            with self.subTest(role=role):
                self.assertFalse(self.policy.decide(role, "repo.edit").allowed)
        self.assertTrue(self.policy.decide("developer", "repo.edit").allowed)

    def test_no_role_may_push_open_a_pr_or_merge(self):
        for role in self.policy.roles_named():
            for action in ("push", "pr.open", "pr.merge", "pr.vote",
                           "pipeline.run", "deploy", "ticket.assign"):
                with self.subTest(role=role, action=action):
                    self.assertFalse(self.policy.decide(role, action).allowed)

    def test_no_role_may_change_its_own_permission_or_promote_a_skill(self):
        for role in self.policy.roles_named():
            for action in ("permission.change", "skill.promote"):
                with self.subTest(role=role, action=action):
                    d = self.policy.decide(role, action)
                    self.assertEqual(d.outcome, DENY)

    def test_read_only_roles_have_no_shell_and_no_editing(self):
        for role in ("reviewer", "architect", "security"):
            tools = self.policy.tools_for(role)
            with self.subTest(role=role):
                self.assertFalse(any(t.startswith("Bash") for t in tools))
                self.assertNotIn("Edit", tools)
                self.assertNotIn("Write", tools)

    def test_the_developer_can_commit_locally_and_not_push(self):
        tools = self.policy.tools_for("developer")
        self.assertTrue(any("git commit" in t for t in tools))
        self.assertFalse(any("push" in t for t in tools))

    def test_the_ticket_prefix_is_configuration_and_ships_empty(self):
        """It is read from here rather than hard-coded in the skills.

        The shipped default is deliberately empty: a real project's prefix is
        one team's vocabulary, and shipping it puts that team's vocabulary on
        everybody else's machine. An earlier version of this test asserted the
        default was non-empty, which made the leak look correct.
        """
        self.assertIn("prefix", self.policy.tickets)
        self.assertEqual(self.policy.ticket_prefix(), "")

    def test_ingest_goes_to_the_only_isolated_layer(self):
        """The other layers are shared across tenants on the same host."""
        self.assertEqual(self.policy.ingest.get("layer"), "project")
        self.assertTrue(self.policy.ingest.get("require_stamp"))
        self.assertTrue(self.policy.ingest.get("require_redaction_gate"))

    def test_every_never_carries_its_reason(self):
        """A rule with no stated reason gets argued with and then removed."""
        for action in self.policy.actions.values():
            if action.never:
                with self.subTest(action=action.name):
                    self.assertGreater(len(action.never), 20)


class AgentCardsAreCheckedAgainstIt(unittest.TestCase):
    """`allowed_actions` used to be strings nothing validated.

    A typo produced a card that granted nothing, silently. There is a real
    vocabulary now, so a card is checked against it.
    """

    def setUp(self) -> None:
        self.policy = Policy.load(SHIPPED)

    def a_card(self, **overrides) -> dict:
        card = {"agent_id": "agt-1", "display_name": "arup-developer-1",
                "owner_jira_user_id": "arup", "role": "developer",
                "hand": "claude",
                "allowed_actions": ["repo.read", "repo.edit", "test.run"]}
        card.update(overrides)
        return card

    def test_a_card_that_matches_its_role_is_fine(self):
        self.assertEqual(self.policy.check_agent_card(self.a_card()), [])

    def test_a_typo_in_an_action_is_caught(self):
        problems = self.policy.check_agent_card(
            self.a_card(allowed_actions=["repo.read", "repo.edti"]))
        self.assertTrue(any("repo.edti" in p for p in problems))

    def test_a_card_may_be_narrower_than_its_role(self):
        """An owner handing one agent less than the role allows is the point."""
        self.assertEqual(
            self.policy.check_agent_card(self.a_card(allowed_actions=["repo.read"])),
            [])

    def test_a_card_may_not_be_wider_than_its_role(self):
        """Otherwise the card quietly becomes the policy."""
        problems = self.policy.check_agent_card(
            self.a_card(role="reviewer", allowed_actions=["repo.read", "repo.edit"]))
        self.assertTrue(any("repo.edit" in p for p in problems), problems)

    def test_a_card_cannot_grant_something_marked_never(self):
        problems = self.policy.check_agent_card(
            self.a_card(allowed_actions=["repo.read", "pr.merge"]))
        self.assertTrue(any("pr.merge" in p for p in problems))

    def test_a_card_that_both_allows_and_denies_is_caught(self):
        problems = self.policy.check_agent_card(
            self.a_card(denied_actions=["repo.edit"]))
        self.assertTrue(any("both allowed and denied" in p for p in problems))

    def test_an_unknown_role_stops_there(self):
        problems = self.policy.check_agent_card(self.a_card(role="wizard"))
        self.assertEqual(len(problems), 1)
        self.assertIn("wizard", problems[0])


class FindingIt(unittest.TestCase):
    def test_versions_are_ordered_numerically_not_alphabetically(self):
        """Several plugin versions sit side by side — four of one on this
        machine — and string order puts 0.10.0 below 0.9.0."""
        from sky.policy import _version_key
        ordered = sorted(["0.9.0", "0.10.0", "0.2.1", "1.0.0"], key=_version_key)
        self.assertEqual(ordered, ["0.2.1", "0.9.0", "0.10.0", "1.0.0"])

    def test_an_odd_version_name_does_not_crash_the_ordering(self):
        from sky.policy import _version_key
        sorted(["1.0.0", "main", "2.0-rc1"], key=_version_key)   # must not raise

    def test_the_environment_variable_wins(self):
        tmp = Path(tempfile.mkdtemp())
        (tmp / "policy.yaml").write_text(MINIMAL)
        before = os.environ.get("SKY_POLICY")
        os.environ["SKY_POLICY"] = str(tmp / "policy.yaml")
        try:
            self.assertEqual(Policy.find(), tmp / "policy.yaml")
        finally:
            os.environ.pop("SKY_POLICY", None)
            if before is not None:
                os.environ["SKY_POLICY"] = before

    def test_a_missing_policy_says_what_it_means(self):
        with self.assertRaises(PolicyError) as caught:
            Policy.load(Path(tempfile.mkdtemp()) / "absent.yaml")
        message = str(caught.exception)
        self.assertIn("cannot read", message)

    def test_nothing_found_explains_the_consequence(self):
        before = os.environ.get("SKY_POLICY")
        os.environ["SKY_POLICY"] = str(Path(tempfile.mkdtemp()) / "absent.yaml")
        try:
            with self.assertRaises(PolicyError) as caught:
                Policy.load()
            self.assertIn("may not build", str(caught.exception))
        finally:
            os.environ.pop("SKY_POLICY", None)
            if before is not None:
                os.environ["SKY_POLICY"] = before


class AFreshCloneCanReadThePolicyItShipsWith(unittest.TestCase):
    """The last resort, and why it is last.

    Before this, someone who cloned the repository and ran the first command in the
    README was told no policy.yaml was found — while the file sat in `plugin/` two
    directories away. That reads as "this tool is broken", not "this tool is
    unconfigured", and it is the first thing a stranger sees.
    """

    def test_the_repository_copy_is_found_when_nothing_is_installed(self):
        from sky.policy import _repo_policy
        found = _repo_policy()
        self.assertIsNotNone(found, "the checkout's own plugin/policy.yaml was not found")
        self.assertTrue(found.is_file())
        self.assertEqual(found.name, "policy.yaml")
        Policy.load(found)                      # and it must actually parse

    def test_it_is_found_from_the_vendored_copy_too(self):
        """This module is vendored into plugin/runtime/sky, at a different depth.

        Counting parent directories would be right in one copy and wrong in the other,
        which is the kind of break that only shows up in the copy nobody tested.
        """
        vendored = REPO / "plugin" / "runtime" / "sky" / "policy.py"
        if not vendored.is_file():
            self.skipTest("no vendored runtime in this checkout")
        import subprocess
        out = subprocess.run(
            [sys.executable, "-c",
             "import sys; sys.path.insert(0, %r); "
             "from sky.policy import _repo_policy; print(_repo_policy())"
             % str(REPO / "plugin" / "runtime")],
            capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertTrue(Path(out.stdout.strip()).as_posix().endswith("plugin/policy.yaml"),
                        f"vendored copy resolved to {out.stdout.strip()!r}")

    def test_an_installed_policy_still_wins_over_the_checkout(self):
        """A checkout on disk must never quietly override what governs the machine."""
        from sky import policy as policy_module
        installed = Path(tempfile.mkdtemp()) / "policy.yaml"
        installed.write_text(MINIMAL)
        real = policy_module._installed_policy
        policy_module._installed_policy = lambda: installed
        before = os.environ.pop("SKY_POLICY", None)
        try:
            self.assertEqual(Policy.find(), installed)
        finally:
            policy_module._installed_policy = real
            if before is not None:
                os.environ["SKY_POLICY"] = before


if __name__ == "__main__":
    unittest.main(verbosity=2)
