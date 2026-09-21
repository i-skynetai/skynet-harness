# Getting started

Ten minutes: check readiness, connect a knowledge base, run one task.

## 1. Requirements

- Python 3.11 or newer. The core uses the standard library only.
- A coding agent already installed — Claude Code, Codex or Kimi.
- A knowledge base reachable over MCP. See [knowledge-port.md](knowledge-port.md);
  any MCP server exposing search tools will do.

## 2. Check what is present

```bash
git clone https://github.com/arupmmi07/skynet-harness.git
cd skynet-harness
python3 -m sky doctor
```

`doctor` probes the knowledge source, retrieval, coding agent, policy, skills and test
runner, and prints a readiness table. It names what is missing rather than continuing.
A green table means a run will start; it does not promise the run will succeed.

## 3. Connect a knowledge base

Knowledge bases live in `config/kb-map.json`. One entry per KB:

```json
{
  "work_kb": {
    "mcp_url": "https://your-kb.example.com/mcp/",
    "tenant_code": "DEMO0001",
    "pat_env": "SKY_PAT_WORK",
    "repos": ["/path/to/a/repository"]
  }
}
```

- `pat_env` names the environment variable holding the token. The token itself never
  goes in the file.
- `repos` is how a repository resolves to a KB. A repository under a client KB never
  falls back to a default — it gets no KB and a message saying so.

Then:

```bash
export SKY_PAT_WORK=your-token-here
python3 -m sky doctor          # confirm the KB is reachable and retrieval returns
```

## 4. Run a task

```bash
python3 -m sky build --issue PROJ-123 --role developer --hand claude
```

This resolves the KB, applies the developer role's tool list, builds an explicit
environment with the Git credential paths blocked, launches the hand, and records the
run.

`--role` is one of `developer`, `reviewer`, `architect`, `security`. The role decides
the tool list, and the tool list is the real boundary — see [policy.md](policy.md).

## 5. Read the evidence

Each managed run leaves a local record: identity, the events that happened, the result,
and the usage the coding agent reported. The model does not write this record, which is
why "I opened a pull request" cannot appear in it unless a pull request was opened.

## Common first problems

| Symptom | Cause |
|---|---|
| `doctor` says retrieval returns nothing | The KB is reachable but empty, or the tenant is wrong. Check `tenant_code`. |
| A repository resolves to no KB | Deliberate. Add the path to a KB's `repos`, or set a `brain:` line in the repo's `CLAUDE.md`. |
| A role cannot run a command | Also deliberate. Check the role's tool list in `plugin/policy.yaml`. |
| The run produced no record | The hand exited before the harness attached. Check `doctor` first. |
