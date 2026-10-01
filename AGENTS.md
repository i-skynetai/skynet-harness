# Agent rules — skynet-harness

Applies to all files in this repository, including work by Codex. This is the portable
counterpart of the shared project CLAUDE.md. Read README.md, CONTRIBUTING.md and
ROADMAP.md before changes. These are both portfolio projects and open-source projects:
a newcomer must be able to understand and try the shipped product in ten minutes.

## Work and ownership

- Ship only working, tested features. Unbuilt features belong in ROADMAP.md, not stubs.
- ROADMAP.md is the only backlog: every feature, known bug and fix has an ID, priority,
  size, status and owner. This project's prefix is SH.
- Before the first release, the maintainer owns the base-product rows; publish the
  roadmap with the first version tag. After release, take one feature at a time.
- Before coding, claim the row with owner and date and mark In progress. Move it to
  In review when ready for review, and Done with the version only after merge.
- Use the Claim a feature issue template. Large features start from
  docs/features/TEMPLATE.md. Do not overwrite someone else's uncommitted work.
- Read actual source before asserting behaviour. Distinguish verified results from
  checks still needed. Never invent a measurement, successful run or integration.

## Release gate

A fresh clone must install and demonstrate the product in minutes without a private
service, account or key. Tests run with one documented command and the same checks in
CI. No unresolved P0 correctness bug may ship. Every README claim must work end to end
and have test evidence. Include the full Apache 2.0 licence, CONTRIBUTING.md, ROADMAP.md,
CHANGELOG.md, feature template, claim template, architecture docs and a matching version
tag. Check public history as well as the working tree for private material.

Local test success does not prove hosted CI or a fresh install. Record skipped tests,
optional-provider checks and live checks separately. Review work never implies permission
to publish. Do not push to public repositories from the restricted work laptop.

## Documentation

Follow this README order: title/tagline and tests/Python/licence badges; plain description;
PNG within 25 lines; problem; explained terms; sixty-second demo and real output image;
numbered usage steps; run diagram; features; limits; status; links and licence.
Keep prose at most 900 words, counts current, versions exact and dates absolute.
Avoid unexplained jargon and “simply”, “just”, or “easy”.

Keep SVG sources beside rendered PNGs in docs/images; embed PNGs and inspect them
visually. Diagram source belongs only under a Diagram sources appendix. Architecture
gets at most three pictures. A terminal screenshot must show actual command output.
CONTRIBUTING.md must explain checks, claiming work and these documentation rules.

In the portfolio workspace run `python3 ../check-docs.py .` before README/docs commits
and before a tag. Fix every FAIL; fix or explain WARNs. Read the adjacent
DOCUMENTATION-STANDARD.md for the full standard. In a standalone clone those parent
files may be absent: apply the rules above manually and report that the shared checker
was unavailable. Do not pretend it ran.

No employer/client/internal product names, private URLs, personal filesystem paths,
credentials or copied employer source in public artifacts or history. Keep private
plans outside this repository.

## Project boundaries

Keep the core standard-library-only and independent of the plugin. Outward actions cannot become plainly allowed. Offer a role only where the host can enforce it. The string guard is not a sandbox. Keep the vendored plugin runtime consistent with the core using the documented vendor script. Record the reason for every refusal.

## Checks

Use the interpreter and development dependencies described in CONTRIBUTING.md.

```sh
python3 -m unittest discover -s core/tests -t core
```

Do not weaken checks or delete tests to make a release appear ready. A review records
failures and their evidence; it does not silently implement a different product.
