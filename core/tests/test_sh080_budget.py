"""Budget boundaries and runtime confirmation; no token measurement claim."""
import copy
import unittest
from unittest.mock import Mock

from sky import budget


class Budget(unittest.TestCase):
    def manifest(self, characters):
        return {"measured_characters": characters, "retrievals": [{"characters": characters}], "findings": []}

    def test_exact_cap_delivers_pack(self):
        result = budget.apply(self.manifest(40), {"max_tokens": 10}, task_id="task", pack="evidence")
        self.assertTrue(result["delivered"])
        self.assertEqual(result["pack"], "evidence")

    def test_one_token_or_one_character_over_cap_delivers_nothing(self):
        for characters in (41, 44):
            result = budget.apply(self.manifest(characters), {"max_tokens": 10}, task_id="task", pack="evidence")
            self.assertFalse(result["delivered"])
            self.assertIsNone(result["pack"])
            self.assertIn("nothing delivered", result["findings"][0])
            self.assertEqual(result["manifest"]["measured_characters"], characters)

    def test_missing_cap_uses_shipped_default_and_says_so(self):
        result = budget.apply(self.manifest(40), task_id="task")
        self.assertEqual(result["max_tokens"], budget.DEFAULT_MAX_TOKENS)
        self.assertIn("shipped default", result["findings"][0])

    def test_tokens_are_labelled_estimate_from_measured_characters(self):
        result = budget.apply(self.manifest(41), task_id="task")
        self.assertEqual(result["estimated_tokens"], 10.25)
        self.assertIn("estimate", result["token_method"])

    def test_human_override_is_recorded_and_applies_to_one_task(self):
        run = Mock(run_id="run")
        manifest = self.manifest(80)
        approval = budget.approve(manifest, task_id="task", max_tokens=20, run=run, confirm=lambda _: True, env={})
        result = budget.apply(manifest, {"max_tokens": 10}, task_id="task", pack="evidence", approval=approval)
        self.assertTrue(result["delivered"])
        self.assertEqual(run.event.call_args.args[0], budget.EVENT)
        with self.assertRaises(budget.BudgetError):
            budget.apply(manifest, {"max_tokens": 10}, task_id="other", approval=approval)

    def test_agent_cannot_approve(self):
        with self.assertRaisesRegex(budget.BudgetError, "person"):
            budget.approve(self.manifest(80), task_id="task", max_tokens=20, run=Mock(), confirm=lambda _: True, env={"SKY_LAUNCHED": "1"})

    def test_refused_confirmation_does_not_record_approval(self):
        run = Mock()
        with self.assertRaises(budget.BudgetError):
            budget.approve(self.manifest(80), task_id="task", max_tokens=20, run=run, confirm=lambda _: False, env={})
        run.event.assert_not_called()

    def test_changed_manifest_or_serialized_approval_refused(self):
        manifest = self.manifest(80)
        approval = budget.approve(manifest, task_id="task", max_tokens=20, run=Mock(run_id="run"), confirm=lambda _: True, env={})
        changed = self.manifest(84)
        for provided in (approval, {"max_tokens": 100}):
            with self.assertRaises(budget.BudgetError):
                budget.apply(changed, {"max_tokens": 10}, task_id="task", approval=provided)

    def test_invalid_cap_or_inconsistent_measured_total_refused(self):
        for cap in (0, -1, True, "10"):
            with self.assertRaises(budget.BudgetError):
                budget.apply(self.manifest(40), {"max_tokens": cap}, task_id="task")
        manifest = self.manifest(40)
        manifest["measured_characters"] = 41
        with self.assertRaises(budget.BudgetError):
            budget.apply(manifest, task_id="task")

    def test_over_budget_does_not_mutate_input_manifest(self):
        manifest = self.manifest(80)
        before = copy.deepcopy(manifest)
        budget.apply(manifest, {"max_tokens": 10}, task_id="task")
        self.assertEqual(manifest, before)
