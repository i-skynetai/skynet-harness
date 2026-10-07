# Contributing

Contribute a reproducible bug report, a feature proposal, a documentation correction,
tests or code. You do not need a connected model or knowledge service to run the
standard-library tests. Start with the [README](README.md) and [docs index](docs/README.md).

## Report a bug or propose a feature

Search [existing issues](https://github.com/i-skynetai/skynet-harness/issues) and
[ROADMAP.md](ROADMAP.md) first. Issues are the discussion and reproduction record;
the roadmap is the only backlog, with SH IDs, priorities, acceptance criteria and owners.
An accepted new bug or feature gets a roadmap row from a maintainer.

- [Report a bug](https://github.com/i-skynetai/skynet-harness/issues/new?template=bug_report.md):
  include version/commit, OS, Python/host versions, minimal reproduction, expected and
  actual results. A public fixture is more useful than a screenshot of private data.
- [Propose a feature](https://github.com/i-skynetai/skynet-harness/issues/new?template=feature_request.md):
  explain the problem, proposed behavior and a testable acceptance case.
- [Claim existing work](https://github.com/i-skynetai/skynet-harness/issues/new?template=feature_claim.md):
  name the SH ID and your approach. Comment on an existing issue instead of duplicating it.

Do not put credentials, private URLs, employer material or unredacted run records in
issues, patches or screenshots. For security concerns, use private vulnerability
reporting if offered; otherwise ask the maintainer for a private route without details.

## Pick and claim work

1. Choose an unowned `Ready` row; *good first issue* marks a suggested starting point.
   `Proposed` and `Needs decision` rows need maintainer agreement before implementation.
2. Open the claim issue or comment and wait for the maintainer to confirm ownership.
   Check that another contributor is not already implementing it.
3. In your first PR, set the row to `In progress` with your handle and an absolute date.
4. For L-sized work or permission changes, agree the design first. Use
   [the design template](docs/features/TEMPLATE.md) for a large feature.
5. Open the implementation PR and mark the row `In review`. A maintainer records the
   merge/release status; contributors must not label unfinished work Done.

Take one feature at a time. A claim with no visible progress for 21 days returns to
Ready; leave an update if you need longer. Small spelling/link corrections can use
SH-092/093 or the docs-maintenance row; agree broader scope on an issue.

## Set up a development checkout

Git and Python 3.11 or newer are required. No pip install, pytest or runtime dependency
is needed. Fork the repository on GitHub, then clone your fork:

```sh
git clone https://github.com/<your-handle>/skynet-harness.git
cd skynet-harness
git switch -c fix/SH-XXX-short-description
python sky policy lint
```

Use `python3` if that is your interpreter command. Run commands from the harness root.
On Windows PowerShell, run `$env:PYTHONUTF8='1'` first and put Git for Windows' Bash
and sh on PATH. Missing-shell skips/failures are environment findings to report, not
proof that the affected behavior passed.

## Required checks

```sh
python -m unittest discover -s core/tests -t core
python sky selftest
python sky policy lint
```

Counts and platform skips vary by revision; record the actual result. CI
runs the unit suite and selftest on Linux with Python 3.11, 3.12 and 3.13. Record the
actual results for your commit, including skipped and optional/live checks. A local
pass does not establish hosted CI or an authenticated host integration.

After changing `core/sky/`, refresh the plugin's runtime before the final checks:

```sh
python scripts/vendor-runtime.py
```

After changing shipped policy/skill bindings, regenerate and check the shipped agents
and registry from an unmanaged harness checkout:

```sh
python sky policy render
python sky policy lint
```

Generated runtime, agent and registry copies belong in the same PR as their source.
Do not regenerate from an unrelated managed project's narrowed policy.

For README or docs changes, in the portfolio workspace run:

```sh
python ../check-docs.py .
```

That parent checker is not distributed in a standalone clone. If unavailable, report
that fact and apply the manual documentation checks below. Do not claim it ran.
`selftest` checks private names using committed salted hashes; the maintainer's plain
word list remains private. Do not add that list to a contribution.

## Open a pull request

Push your branch to your fork and open a PR against `main`. Use the PR template:
state the concrete problem, final behavior, SH ID, commands/results and remaining limits.
Include the relevant failure case and a regression test for behavior changes.
Documentation-only corrections need documentation verification, not invented tests.

Keep unrelated changes out. Use draft PRs for unfinished work. Update the same PR
when review finds problems and rerun affected checks. Maintainers check acceptance,
permissions, privacy and CI before merging. Permission changes need explicit design
agreement; a green test suite does not automatically approve them.

AI-assisted patches follow the same process. Verify their claims and disclose the
assistance in the PR. In this project's maintainer environment Claude does not push;
Codex performs verified project pushes. That local rule does not require external
contributors to use Codex to push their own forks.

## What a change must preserve

- Standard-library-only core, independent of the plugin.
- Default deny; no outward action becomes plainly allowed.
- Roles offered only where the host can enforce their stated limits.
- Named refusals and visible redaction failures; no quiet secret scrubbing.
- Tested behavior and honest distinctions between measured, skipped and planned work.

Be respectful in reports and reviews. Explain disagreement with evidence and keep the
discussion about the change. Match existing style and keep the reasoning in docstrings.

## Documentation checks

Write for someone new who has ten minutes. Explain terms at first use. Keep the README
within 900 prose words: purpose/benefit, early PNG, runnable demo, installation, limits,
status/history and links. State pending features with roadmap IDs; distinguish source
main from a tagged release and never invent gains, test counts or live output.

Keep detailed guides, reference and explanations in separate linked pages. Check local
links, headings, command working directories and Windows instructions. A clean-clone
example must work without a private service; model runs state their authentication needs.

Keep Mermaid/SVG sources beside rendered PNGs in `docs/images/`, embed PNGs and inspect
them. Diagram source links belong in a Diagram sources appendix. Render Mermaid with
`python scripts/render-mermaid.py` when source changes (its optional Node/mermaid-cli
requirements are explained in the script); no renderer is needed to use the harness.
Terminal images must show real command output. Architecture has at most three pictures.

Contribution templates follow [GitHub's issue/PR template guidance](https://docs.github.com/en/communities/using-templates-to-encourage-useful-issues-and-pull-requests/about-issue-and-pull-request-templates).
