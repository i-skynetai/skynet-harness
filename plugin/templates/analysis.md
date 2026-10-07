---
{
  "type": "analysis",
  "schema_version": 1,
  "title": "Replace with the goal title",
  "goal": "Replace with the requested goal",
  "scope": ["."],
  "evidence_revision": "replace-with-verified-checkout-revision",
  "intent": {"in_scope": ["Replace with bounded scope"], "out_of_scope": []},
  "findings": [{"statement": "Replace with a verified fact", "citations": ["replace-with-file:1"]}],
  "open_questions": [{"question": "Replace with an unresolved question", "candidates": [], "reason": "Explain the inspected candidates and why none closes it"}],
  "risks": [],
  "retrieval": {"operations": []},
  "citations": [],
  "relates_to": []
}
---
# Analysis

Replace every placeholder. Return structured frontmatter and explanatory Markdown
for `sky kb analyze put --from - --goal <goal>`. Do not supply stamps or retrieval.run.
The runtime records ledger operations/characters; unavailable counts remain null.

## Intent and discovery
Explain in/out of scope. Every finding names resolving file:line or id:<record>
citations. Unsupported claims remain OPEN.

## Decisions and OPEN questions
Each question lists candidates {id, status, closes}, an evidence-backed reason,
and optional closed_by. Include closed_by only for an accepted, current, in-scope
candidate with a verified evidence revision and no conflicting applicable answer.

## Risks and retrieval
Describe incomplete coverage and risks. Runtime measurements do not prove prompt
delivery. An observation is not a decision and a saved analysis is not admission.
