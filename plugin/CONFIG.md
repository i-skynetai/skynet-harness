# Where a skill gets its configuration

Every `/sky:*` skill needs three things that are **not** written in the skill:
which knowledge base to talk to, which ontology to use, and what a ticket id
looks like here. They are not written in the skill because a skill is shipped
to everyone and those three differ per person, per project and per company.

Read this once at the start of a skill that touches the knowledge base.

---

## 1. The tool names — check before you call

A knowledge-base tool's full id is `mcp__<server>__<tool>`. Both ways this project
connects a knowledge base — `sky build`, and `sky setup init`'s registration — name
the server `kb`, so the tool is called `mcp__kb__kb_search`.

**Look at the tools you actually have before you call one.** A call to a name this
session does not have does not raise an error you will see — the tool is simply
absent, and the honest-sounding conclusion "the knowledge base has nothing on this"
is wrong. If no `mcp__kb__…` tool is present, stop and say so: this session has no
knowledge base, which is a setup problem (`sky setup doctor`), not an empty one.

Throughout the skills, a tool is named by its bare name — `kb_search`,
`kb_similarity_search`, `kb_documents_ingest`. Prefix it with `mcp__kb__`.

## 2. The tenant — required on every knowledge-base call

Resolve in this order, and stop at the first that answers:

1. **`$SKY_TENANT`.** The launcher sets it from the knowledge base it resolved,
   and that resolution has already passed the privacy check — the launcher
   refuses to cross a privacy boundary, so a tenant arriving this way is one
   you may use.
2. **The KB map** — `~/.config/sky/kb-map.json`. It is a
   JSON object of entries. Take the entry whose `repos` path is the **longest**
   prefix of the working directory. Longest, so a checkout nested inside
   another resolves to the nearer one.
3. **The map's `default: true` entry**, but only when nothing owns this
   directory *and* that default is class `work`. A `client` or `personal`
   default is never reached by falling back — ask instead.
4. **Ask the user once**, and reuse the answer for the rest of the session.

**Server guard, before using a map entry.** Compare the entry's `mcp_url` with
the address this session is actually connected to. If they differ, stop and
name both: this directory's knowledge base is on a different server from the
one you are talking to. Do not read from one and write to the other.

## 3. The ontology

From the same map entry's `ontology` field. Two exceptions, both in `ingest`:
a document whose type is a skill uses `sky_skill`, and session or task memory
uses `agent_context` — and only when the knowledge base actually offers them,
which you check with `kb_ontologies_list`.

Never hard-code an ontology name in a step. Ontology names are global to the
platform and differ between installations.

## 4. The ticket prefix

From the policy's `tickets.prefix`. It is empty by default, and empty means
**this installation has not told you what a ticket looks like** — so do not
invent a pattern, and do not assume the examples you have seen. Ask the user
for the ticket id rather than trying to recognise one.

Where a skill writes `<TICKET>` it means an id of whatever shape this
installation uses — never a literal, and never one you saw in an example.

## 5. The layer, and what is never configurable

`layer` is always `project` on every write. It is the only tenant-isolated
layer; the others are global, so a write with the default layer publishes
across tenants. This is not a setting and is never offered as one.

---

## Skills own tools

In `policy.yaml`, roles grant ordered `skills` and optional `base_tools`; skills
declare their tools. Groups expand before top-level tool bindings are checked.
Each new-style tool binds to a permitted action, and MCP bindings require a
`reviewed_by` handle. Outward tools remain unavailable: prepare intents instead.
Legacy role `tools` lists still work and cannot be mixed with the new keys.

Run `sky policy render` after a policy change. It preserves existing role templates
and writes their tools plus the plugin source `registry.json`; it refuses malformed
or missing templates before writing. `sync-agents` is an alias, `check-agents`
reports drift, and `sky policy lint` checks the registry as well as agent files.
`sky policy show` names declared skills granted to no role (SH-082).

## Managed project configuration

Each Git worktree may declare `managed: true` in `.sky/project.yaml`. Optional
fields are `org_plugin` (`marketplace/plugin`, or an unambiguous bare name), `kb`,
repository-relative `sessions_dir`, and `context.max_chars` (default 40000).
Absent configuration or `managed: false` leaves existing discovery unchanged.
Explicit policy overrides bypass layers and the command says so.

Shipped, org and project patches merge under the shipped action/guard ceiling.
Use `sky policy show --layers`, then `sky policy lint` and `sky policy render`.
Managed render owns only recorded project agents/skills and `.sky/registry.json`;
it never writes an installed plugin. Unknown removals, collisions and unowned or
edited generated files refuse. Narrowed/added roles remain unavailable to
`sky build` until SH-062 supplies effective identity selection.

## If any of this is missing

`sky setup doctor` answers the configuration questions — is there a map, does
it name a token variable, is that variable set, is a server registered.
`sky doctor` answers the running-system questions. A skill that cannot resolve
a tenant should say which of the two to run, not guess a value.
