---
name: Report a bug
about: A reproducible failure, incorrect result or misleading documentation
title: "Bug: "
---

<!-- Search existing issues and ROADMAP.md first. Never paste credentials, private
URLs, employer material, raw private documents or unredacted run records. -->

**Existing issue or SH ID** — link it if this is already tracked.

**Version and environment** — commit (`git rev-parse HEAD`), plugin version, OS,
Python version, host/version, and local or remote context source (no credentials).

**Steps to reproduce** — the smallest commands and public fixture that reproduce it.

**Expected result** — what should happen, including any expected refusal.

**Actual result** — output/error and exit code, with private content removed.

**Checks** — relevant test results, `python sky selftest`, and whether the failure
occurs on a fresh checkout. Include skips and environment limitations.

**Impact or workaround** — what is blocked and how you currently work around it.

For a possible security issue, do not publish exploit details or secrets here.
Use GitHub's private vulnerability reporting option if the repository offers it;
otherwise ask the maintainer for a private reporting route without disclosing details.
