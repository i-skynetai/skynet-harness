# Getting started

Two minutes to see what it does. Ten to connect a knowledge base and run a real task.

## 1. Clone it and ask the policy a question

No install, no account, no knowledge base. Python 3.11 or newer is the only
requirement — the core is standard library.

```bash
git clone https://github.com/arupmmi07/skynet-harness.git
cd skynet-harness

./sky policy lint                    # does the shipped policy hold together?
./sky policy developer push          # may a developer push?
./sky policy reviewer push           # may a reviewer?
./sky policy developer edit          # may a developer do something unnamed?
```

You should see:

```
plugin/policy.yaml: clean
    4 roles, 23 actions, 13 guard rules

developer · push: needs-human — prepared by the agent, performed by you
reviewer · push: deny — the reviewer role does not have 'push'
developer · edit: deny — 'edit' is not an action this policy defines, so it is denied
```

That is the whole idea in four commands. **`push` is never a plain allow**, for anybody
— the agent prepares it and you perform it. **A reviewer cannot push** at all, because
the role does not list it. And **an action the policy has never heard of is denied**
rather than assumed harmless, which is the difference between a default-deny policy and
a list of things someone remembered to forbid.

```bash
./sky policy show                    # every role, its tools, and what it may do
./sky selftest                       # is this repository still internally sound?
```

`selftest` checks the repository against itself — that the core never imports the
plugin, that every role's tool list matches the policy, that the plugin's vendored copy
of the runtime has not drifted, that no credential is in the plugin. On a fresh clone
two checks skip and say why, which is the habit the whole project is built on: a check
that did not run says so rather than counting itself as a pass.

## 2. Check what is present

```bash
./sky doctor
```

`doctor` probes the knowledge source, retrieval, coding agent, policy, skills and test
runner, and prints a readiness table. It names what is missing rather than continuing.
A green table means a run will start; it does not promise the run will succeed.

At this point `doctor` will say there is no knowledge base, which is correct — you have
not connected one yet. That is the next step, and it is the first one that needs
anything from outside this repository:

- A coding agent already installed — Claude Code, Codex or Kimi.
- A knowledge base reachable over MCP. See [knowledge-port.md](knowledge-port.md);
  any MCP server exposing search tools will do.

## 3. Connect a knowledge base

Knowledge bases live in `~/.config/sky/kb-map.json` (or pass `--kb-map <path>`).
One entry per KB:

```json
{
  "work_kb": {
    "mcp_url": "https://your-kb.example.com/mcp/",
    "tenant_code": "DEMO0001",
    "ontology": "sky_sdlc",
    "privacy": "work",
    "pat_env": "SKY_PAT_WORK",
    "repos": ["/path/to/a/repository"]
  }
}
```

- `ontology` is the knowledge base's schema name; `privacy` is `personal`, `work` or
  `client`. Both are required.
- `pat_env` names the environment variable holding the token. The token itself never
  goes in the file.
- `repos` is how a repository resolves to a KB. A repository under a client KB never
  falls back to a default — it gets no KB and a message saying so.

Then:

```bash
export SKY_PAT_WORK=your-token-here
./sky doctor          # confirm the KB is reachable and retrieval returns
```

## 4. Run a task

```bash
./sky build --task PROJ-123 --role developer --hand claude
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

## Where everything lives

![Where the plugin, the knowledge-base setting and the token each live, and the one
path a token travels](images/onboarding-where-things-live.png)

Four locations, one token path. If a run cannot reach the knowledge base, the fault is
on that path and `sky doctor` says which step.

## Common first problems

| Symptom | Cause |
|---|---|
| `doctor` says retrieval returns nothing | The KB is reachable but empty, or the tenant is wrong. Check `tenant_code`. |
| A repository resolves to no KB | Deliberate. Add the path to a KB's `repos`, or set a `brain:` line in the repo's `CLAUDE.md`. |
| A role cannot run a command | Also deliberate. Check the role's tool list in `plugin/policy.yaml`. |
| The run produced no record | The hand exited before the harness attached. Check `doctor` first. |
