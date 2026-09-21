"""Tests for the selftest.

Two things matter here, and the second is the one usually skipped.

**It catches what it claims to.** Each check gets a repository built to fail it.

**It leaves ordinary content alone.** A check that fires on normal prose gets
switched off, and then it is protecting nothing. The word "usual" contains a
three-letter organisation name; `REQUIRED` looks like a tenant code; a design
document is *supposed* to discuss tokens and bearer headers. Every one of those
appears in a corpus below that must produce no findings.

This file names-retired-vocabulary-on-purpose: it proves the retirement rules
fire, which means containing the words they retire.
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sky import selftest  # noqa: E402

REPO = Path(__file__).resolve().parents[2]


def a_repo(**files) -> Path:
    """A minimal repository shaped like the real one."""
    root = Path(tempfile.mkdtemp())
    for name in ("core", "plugin", "schemas", "hosts", "docs"):
        (root / name).mkdir()
    (root / "plugin" / "agents").mkdir()
    for path, body in files.items():
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
    return root


class ItLeavesOrdinaryContentAlone(unittest.TestCase):
    """The half that is usually forgotten."""

    SAFE = {
        "plugin/skills/a/SKILL.md":
            "It usually reads the map. Because of that, the usual source is\n"
            "the configuration file. Discussion of a token belongs here.\n"
            "Set `$SKY_KB_PAT` before running; the URL is `${SKY_KB_URL}`.\n"
            "See <https://example.invalid/docs> and `<your-host>/mcp/`.\n",
        "plugin/skills/b/SKILL.md":
            "Every value is REQUIRED, ADDITIVE, VERBATIM and GLOBALLY unique.\n"
            "The header is `Authorization: Bearer ${SKY_KB_PAT}`.\n"
            "A response of APPROVED or BLOCKED is expected.\n",
        "plugin/agents/x.md": "---\nname: x\ntools: Read\n---\nprose\n",
    }

    def setUp(self) -> None:
        self.root = a_repo(**self.SAFE)

    def test_no_credential_is_reported_in_writing_about_credentials(self):
        result = selftest.check_no_credentials(self.root)
        self.assertTrue(result.passed, result.problems)

    def test_placeholders_and_shouted_words_are_not_endpoints_or_tenants(self):
        result = selftest.check_no_local_strings(self.root)
        self.assertTrue(result.passed, result.problems)

    def test_a_word_is_not_matched_inside_another_word(self):
        """`widget` is inside "widgets"; a substring scan flags four real lines."""
        result = selftest.check_no_local_vocabulary(self.root, words=["acme", "widget"])
        self.assertTrue(result.passed, result.problems)

    def test_the_real_repository_passes_every_check(self):
        """The strongest false-positive test available: this repository."""
        for result in selftest.run_all(REPO):
            with self.subTest(check=result.name):
                self.assertTrue(result.passed, result.problems)


class ItCatchesWhatItClaimsTo(unittest.TestCase):
    def test_a_missing_directory(self):
        root = a_repo()
        shutil.rmtree(root / "schemas")
        result = selftest.check_shape(root)
        self.assertFalse(result.passed)
        self.assertIn("no schemas/", result.problems)

    def test_core_importing_plugin(self):
        root = a_repo(**{"core/sky/x.py": "from plugin.skills import thing\n"})
        result = selftest.check_the_wall(root)
        self.assertFalse(result.passed)
        self.assertIn("core/sky/x.py:1", result.problems[0])

    def test_a_credential(self):
        root = a_repo(**{"plugin/skills/a/SKILL.md":
                         "token: kb_pat_AbCdEf0123456789XyZw\n"})
        result = selftest.check_no_credentials(root)
        self.assertFalse(result.passed)

    def test_a_real_url(self):
        root = a_repo(**{"plugin/skills/a/SKILL.md":
                         "Point it at https://kb.internal.acme.net/mcp/\n"})
        result = selftest.check_no_local_strings(root)
        self.assertFalse(result.passed)
        self.assertIn("URL", result.problems[0])

    def test_a_home_directory(self):
        root = a_repo(**{"plugin/ontology/v.py":
                         'P = "/Users/someone/projects/thing"\n'})
        result = selftest.check_no_local_strings(root)
        self.assertFalse(result.passed)
        self.assertIn("home directory", result.problems[0])

    def test_a_tenant_code(self):
        """Eight upper-case alphanumerics with at least one digit."""
        root = a_repo(**{"plugin/skills/a/SKILL.md": "tenant_code: SPD3ZM3S\n"})
        result = selftest.check_no_local_strings(root)
        self.assertFalse(result.passed)
        self.assertIn("tenant", result.problems[0])

    def test_local_vocabulary(self):
        root = a_repo(**{"plugin/skills/a/SKILL.md":
                         "Models the acme platform's delivery knowledge.\n"})
        result = selftest.check_no_local_vocabulary(root, words=["acme"])
        self.assertFalse(result.passed)

    def test_a_skill_naming_an_agent_that_does_not_exist(self):
        """The break that splitting one agent into two actually caused."""
        root = a_repo(**{
            "plugin/agents/reviewer.md": "---\nname: reviewer\n---\n",
            "plugin/skills/review/SKILL.md":
                "Run the `architect-reviewer` agent on the diff.\n"})
        result = selftest.check_agent_references(root)
        self.assertFalse(result.passed)
        self.assertIn("architect-reviewer", result.problems[0])

    def test_a_published_schema_that_has_drifted(self):
        root = a_repo()
        (root / "schemas" / "task.schema.json").write_text(json.dumps({"nope": 1}))
        result = selftest.check_schemas(root)
        self.assertFalse(result.passed)


class RetiredNamesAndSources(unittest.TestCase):
    def test_a_name_that_no_longer_exists_is_caught(self):
        root = a_repo(**{"plugin/skills/a/SKILL.md":
                         "Read the brain-map entry for this repository.\n"})
        result = selftest.check_no_retired_names(root)
        self.assertFalse(result.passed)
        self.assertIn("brain-map", result.problems[0])

    def test_reading_the_tenant_from_a_repo_file_is_caught(self):
        root = a_repo(**{"plugin/skills/a/SKILL.md":
                         "Read `tenant_code` from the repo's CLAUDE.md.\n"})
        result = selftest.check_no_retired_names(root)
        self.assertFalse(result.passed)
        self.assertIn("retired source", result.problems[0])

    def test_an_ordinary_mention_of_claude_md_is_left_alone(self):
        """`learn` correctly tells a developer to record a rule there.

        The first version of this check flagged that, which is how a check
        earns being switched off.
        """
        root = a_repo(**{"plugin/skills/learn/SKILL.md":
                         "Draft an edit to the repo's `CLAUDE.md` for the new "
                         "team rule.\n"})
        result = selftest.check_no_retired_names(root)
        self.assertTrue(result.passed, result.problems)


class ASkippedCheckIsNotAPassedOne(unittest.TestCase):
    """"Nothing was checked" and "nothing was wrong" are different claims."""

    def test_an_absent_word_list_reports_skipped(self):
        result = selftest.check_no_local_vocabulary(a_repo(), words=[])
        self.assertTrue(result.skipped)
        self.assertIn("SKIPPED", result.detail)
        self.assertIn(selftest.WORDS_FILE, result.detail)

    def test_the_word_list_is_read_from_a_file(self):
        tmp = Path(tempfile.mkdtemp()) / "words"
        tmp.write_text("# a comment\nacme\n\n  example  # trailing\n")
        self.assertEqual(selftest.load_words(tmp), ["acme", "example"])

    def test_an_absent_word_list_is_not_an_error(self):
        self.assertEqual(selftest.load_words(Path("/nonexistent/words")), [])


class WhatGetsPublished(unittest.TestCase):
    """`plugin/` is not quite the whole of it."""

    def test_the_marketplace_file_is_scanned_too(self):
        """It is fetched from the repository, so it reaches a teammate.

        Gate G11 showed the install cache holds only `plugin/`, which is easy
        to read as "only plugin/ is published". The marketplace file is read
        straight from the repository when someone adds it.
        """
        root = a_repo(**{".claude-plugin/marketplace.json":
                         '{"owner": {"name": "acme team"}}'})
        result = selftest.check_no_local_vocabulary(root, words=["acme"])
        self.assertFalse(result.passed)
        self.assertIn("marketplace.json", result.problems[0])


class OneServerTwoToolNames(unittest.TestCase):
    """The guard for the bug that cost two rounds, then happened again.

    A tool's id is `mcp__<server>__<tool>` and the server's name depends on the
    launch path, so an allowlist naming one spelling silently loses every tool
    on the other. Both real instances are reproduced below as repositories.
    """

    MANIFEST = {
        "plugin/.claude-plugin/plugin.json": '{"name": "sky", "version": "9.9.9"}',
        "plugin/.mcp.json": json.dumps({"mcpServers": {"kb": {}, "code": {}}}),
    }

    def a_plugin(self, **agents):
        return a_repo(**{**self.MANIFEST,
                         **{f"plugin/agents/{n}.md": b for n, b in agents.items()}})

    @staticmethod
    def agent(tools: str) -> str:
        return f"---\nname: a\ntools: {tools}\n---\nprose\n"

    def test_only_the_host_spelling_is_caught(self):
        """The context-retriever bug: real, and invisible until a hand ran."""
        root = self.a_plugin(**{"retriever": self.agent(
            "Read, mcp__plugin_sky_kb__kb_search, mcp__plugin_sky_kb__kb_graph_query")})
        result = selftest.check_both_tool_spellings(root)
        self.assertFalse(result.passed, result.detail)
        self.assertIn("retriever.md", result.problems[0])
        self.assertIn("mcp__kb__", result.problems[0])

    def test_only_the_core_spelling_is_caught_too(self):
        """The mirror image is just as broken, in the other kind of session."""
        root = self.a_plugin(**{"r": self.agent("Read, mcp__kb__kb_search")})
        result = selftest.check_both_tool_spellings(root)
        self.assertFalse(result.passed)
        self.assertIn("mcp__plugin_sky_kb__", result.problems[0])

    def test_a_partial_pair_is_caught(self):
        """Ten of one and nine of the other is the drift this really guards."""
        root = self.a_plugin(**{"r": self.agent(
            "mcp__kb__kb_search, mcp__kb__kb_graph_query, "
            "mcp__plugin_sky_kb__kb_search")})
        result = selftest.check_both_tool_spellings(root)
        self.assertFalse(result.passed)
        self.assertIn("kb_graph_query", result.problems[0])

    def test_both_spellings_pass(self):
        root = self.a_plugin(**{"r": self.agent(
            "Read, mcp__kb__kb_search, mcp__plugin_sky_kb__kb_search")})
        result = selftest.check_both_tool_spellings(root)
        self.assertTrue(result.passed, result.problems)

    def test_an_agent_with_no_mcp_tools_is_not_a_finding(self):
        """validator holds Read, Grep, Glob and Bash by design."""
        root = self.a_plugin(**{"validator": self.agent("Read, Grep, Glob, Bash")})
        self.assertTrue(selftest.check_both_tool_spellings(root).passed)

    def test_a_server_the_plugin_does_not_declare_needs_no_twin(self):
        """`catalogue` exists only when core creates it.

        Demanding `mcp__plugin_sky_catalogue__*` would demand a tool name that
        can never exist — the false positive that would get this switched off.
        """
        root = self.a_plugin(**{"r": self.agent(
            "mcp__kb__kb_search, mcp__plugin_sky_kb__kb_search, "
            "mcp__catalogue__kb_search")})
        result = selftest.check_both_tool_spellings(root)
        self.assertTrue(result.passed, result.problems)

    def test_no_plugin_mcp_config_skips_rather_than_passes(self):
        """"Nothing was checked" and "nothing was wrong" are different claims."""
        # A real plugin, with no MCP servers of its own — the meaningful case.
        root = a_repo(**{
            "plugin/.claude-plugin/plugin.json": '{"name": "sky", "version": "9.9.9"}',
            "plugin/agents/r.md": self.agent("Read")})
        result = selftest.check_both_tool_spellings(root)
        self.assertTrue(result.skipped)
        self.assertIn("no MCP servers", result.detail)
        # And a repository with no plugin manifest at all must not crash.
        self.assertTrue(selftest.check_both_tool_spellings(a_repo()).skipped)

    def test_the_real_repository_passes(self):
        result = selftest.check_both_tool_spellings(REPO)
        self.assertTrue(result.passed, result.problems)

    def test_the_plugin_declares_no_servers_of_its_own_any_more(self):
        """The decision of 2026-09-15, pinned so it is not undone by accident.

        `plugin/.mcp.json` was deleted. It could not authenticate — the host
        does not run `headersHelper` for a plugin's own server (measured) — so
        keeping it meant either a token in the host's settings file or a server
        that failed in every session. `sky setup init` registers a user-scoped
        one instead.

        This check therefore SKIPS, and that is correct rather than a gap: the
        two-spelling risk existed because a plugin server was addressed
        differently from a core one. With no plugin server there is one
        spelling, and the check says so instead of reporting a clean run it did
        not perform.
        """
        self.assertFalse((REPO / "plugin" / ".mcp.json").exists())
        result = selftest.check_both_tool_spellings(REPO)
        self.assertTrue(result.skipped)
        self.assertIn("no MCP servers", result.detail)

    def test_it_is_in_the_suite_that_actually_runs(self):
        """A check nobody calls guards nothing."""
        self.assertIn(selftest.check_both_tool_spellings, selftest.CHECKS)


if __name__ == "__main__":
    unittest.main(verbosity=2)
