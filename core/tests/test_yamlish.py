"""Tests for the small YAML reader.

The important test is the last class: the same text through this reader and
through PyYAML must give the same answer. A hand-written YAML reader that
*fails* is a nuisance; one that quietly disagrees with every other YAML tool
about a security policy is the actual danger.

That cross-check found three real divergences when it was first run — `no`
read as False by PyYAML and as "no" here, `1.0` read as a float there and a
string here, and a plain scalar with a colon that PyYAML rejects outright. All
three are now refused rather than resolved one way, which is why the two
readers agree on every case below.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sky import yamlish  # noqa: E402
from sky.yamlish import YamlishError, parse  # noqa: E402

SHIPPED_POLICY = Path(__file__).resolve().parents[2] / "plugin" / "policy.yaml"

#: Every one of these must parse identically here and in PyYAML.
AGREES = [
    ("a mapping", "a: 1\nb: two\n"),
    ("nesting", "a:\n  b:\n    c: deep\n"),
    ("a sequence under a key", "tools:\n  - Read\n  - Grep\n"),
    ("a sequence at the key's own column", "tools:\n- Read\n- Grep\n"),
    ("a sequence of mappings",
     "rules:\n  - name: one\n    why: because\n  - name: two\n    why: also\n"),
    ("a flow sequence", 'tools: [Read, Grep, "Bash(git add:*)"]\n'),
    ("a colon inside a quoted value", 'tool: "Bash(git add:*)"\n'),
    ("booleans", "a: true\nb: false\n"),
    ("the three ways to say nothing", "a: null\nb: ~\nc:\n"),
    ("whole numbers", "a: 7\nb: -3\n"),
    ("both quote styles", "a: 'it''s'\nb: \"line\\nbreak\"\n"),
    ("comments", "a: 1  # trailing\n# whole line\nb: 2\n"),
    ("a hash inside a string", 'a: "not # a comment"\n'),
    ("an empty flow sequence", "a: []\n"),
    ("a sequence at the root", "- one\n- two\n"),
    ("the shape the policy actually uses",
     "roles:\n  developer:\n    tools: [Read]\n    may:\n      - repo.read\n"
     "      - test.run\n"),
    ("mappings nested in a sequence in a mapping",
     "guard:\n  deny:\n    - pattern: git push\n      because: nope\n"
     "    - pattern: git tag\n      because: also nope\n"),
    ("a leading document marker", "---\na: 1\n"),
    ("a hyphen in a key", "ticket-prefix: PROJ\n"),
    ("a dot in a key", "a.b: 1\n"),
    ("brackets that are not a flow sequence", "a: x[1]\n"),
    ("an empty sequence item", "a:\n  -\n  - two\n"),
]


class ItReadsWhatItClaimsTo(unittest.TestCase):
    def test_the_policy_that_ships_parses(self):
        body = parse(SHIPPED_POLICY.read_text())
        self.assertIn("roles", body)
        self.assertIn("actions", body)
        self.assertEqual(body["version"], 1)

    def test_every_supported_shape_parses(self):
        for name, text in AGREES:
            with self.subTest(case=name):
                parse(text)          # must not raise

    def test_a_quoted_value_keeps_its_colon(self):
        self.assertEqual(parse('t: "Bash(git add:*)"\n'), {"t": "Bash(git add:*)"})

    def test_indentation_decides_nesting(self):
        self.assertEqual(parse("a:\n  b: 1\nc: 2\n"), {"a": {"b": 1}, "c": 2})


class ItRefusesWhatItCannotDoCorrectly(unittest.TestCase):
    """The design rule. A construct it would get wrong stops the load."""

    def test_the_features_it_does_not_implement(self):
        cases = {
            "anchors": "a: &x 1\nb: *x\n",
            "flow mappings": "a: {b: 1}\n",
            "block scalars": "a: |\n  text\n",
            "folded scalars": "a: >\n  text\n",
            "tags": "a: !!str 1\n",
            "merge keys": "a: <<\n",
            "tabs": "a:\n\tb: 1\n",
            "two documents": "a: 1\n---\nb: 2\n",
            "a multi-line flow sequence": "a: [one,\n     two]\n",
            "an unclosed quote": 'a: "open\n',
        }
        for name, text in cases.items():
            with self.subTest(case=name):
                with self.assertRaises(YamlishError):
                    parse(text)

    def test_a_duplicated_key_is_an_error_not_a_silent_overwrite(self):
        """PyYAML keeps the last one. In a policy that means a rule was written
        and is being ignored."""
        with self.assertRaises(YamlishError) as caught:
            parse("a: 1\na: 2\n")
        self.assertIn("set twice", str(caught.exception))

    def test_the_words_yaml_versions_disagree_about(self):
        """The Norway problem, refused rather than resolved."""
        for word in ("no", "yes", "on", "off", "No", "YES", "y", "n"):
            with self.subTest(word=word):
                with self.assertRaises(YamlishError) as caught:
                    parse(f"a: {word}\n")
                self.assertIn("different things to different", str(caught.exception))

    def test_those_words_are_fine_in_quotes(self):
        self.assertEqual(parse('a: "no"\n'), {"a": "no"})

    def test_anything_numeric_that_is_not_a_whole_number(self):
        for value in ("1.5", "1.0", "2026-09-14", "0x10", "1e3", "+7", ".5"):
            with self.subTest(value=value):
                with self.assertRaises(YamlishError):
                    parse(f"a: {value}\n")

    def test_an_unquoted_colon_in_a_value(self):
        """PyYAML rejects this outright; accepting it would let a file load
        here and fail there."""
        with self.assertRaises(YamlishError) as caught:
            parse("note: see this: thing\n")
        self.assertIn("quotes", str(caught.exception))

    def test_the_error_names_the_line(self):
        with self.assertRaises(YamlishError) as caught:
            parse("a: 1\nb: 2\nc: {d: 1}\n")
        self.assertEqual(caught.exception.line_number, 3)

    def test_a_refusal_says_what_to_do_instead(self):
        with self.assertRaises(YamlishError) as caught:
            parse("a: [one,\n     two]\n")
        self.assertIn("block sequence", str(caught.exception))


class ItAgreesWithPyYaml(unittest.TestCase):
    """The test that makes this reader safe to use on a policy file.

    Skipped where PyYAML is absent — core must stay dependency-free — so the
    honest reading of a local green run is "the cases pass; the comparison ran
    wherever the library was installed".
    """

    def setUp(self) -> None:
        try:
            import yaml                                  # noqa: F401
        except ImportError:                              # pragma: no cover
            self.skipTest("PyYAML is not installed here")

    def test_every_case_parses_the_same_both_ways(self):
        import yaml
        for name, text in AGREES:
            with self.subTest(case=name):
                self.assertEqual(parse(text), yaml.safe_load(text))

    def test_the_shipped_policy_parses_the_same_both_ways(self):
        """The one that matters: the real file, both readers, same answer."""
        import yaml
        text = SHIPPED_POLICY.read_text()
        self.assertEqual(parse(text), yaml.safe_load(text))

    def test_nothing_this_reader_accepts_is_rejected_by_pyyaml(self):
        """A file that loads here and fails there would be worse than useless."""
        import yaml
        for name, text in AGREES:
            with self.subTest(case=name):
                yaml.safe_load(text)                      # must not raise


if __name__ == "__main__":
    unittest.main(verbosity=2)
