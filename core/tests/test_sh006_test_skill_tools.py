"""SH-006: the `test` skill calls only tools the policy names.

It once told the agent to run remote regression and browser suites through tool
families no role holds. It now runs local tests only and names any
shared-environment suite for the person to run.
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sky.policy import Policy  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
POLICY = Policy.load(REPO / "plugin" / "policy.yaml")
SKILL = REPO / "plugin" / "skills" / "test" / "SKILL.md"


class TheTestSkillUsesOnlyNamedTools(unittest.TestCase):

    def test_every_knowledge_tool_it_names_is_in_a_role_tool_list(self):
        listed = {t for role in POLICY.roles for t in POLICY.tools_for(role)}
        named = set(re.findall(r"\bkb_[a-z_]+", SKILL.read_text()))
        for name in sorted(named):
            with self.subTest(tool=name):
                self.assertTrue(any(t.endswith(f"__{name}") for t in listed),
                                f"{name} is not in any role's tool list")

    def test_it_runs_no_shared_environment_suite(self):
        body = SKILL.read_text()
        self.assertNotIn("kb_tools_", body)
        self.assertIn("never run them", body)


if __name__ == "__main__":
    unittest.main(verbosity=2)
