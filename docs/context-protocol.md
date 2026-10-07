# The Sky Context Protocol

What a context source must answer so the harness, its skills and its agents can use it
without knowing which product it is. The knowledge port ([knowledge-port.md](knowledge-port.md))
is one source behind this protocol; the code index, a ticket tracker and the local
store (SH-083) are others. Row SH-024 in [ROADMAP.md](../ROADMAP.md).

## Why a protocol and not a tool list

Tool names are a product's. A team's search index, their code index and their ticket
tracker each have their own, and a skill written against one set breaks on the next.
The protocol names **capabilities** and the **operations** each must offer; an
**adapter** maps those operations to one server's real tool names. Skills and agents
call the protocol's names; the policy binds the server's names to actions; the adapter
joins the two.

## Capabilities and operations

Each operation names its inputs and the minimum every hit carries. A source may offer
more; a skill may rely only on what is listed here.

| Capability | Operation | Input | Every hit carries |
|---|---|---|---|
| **search** | `search.similar` | `query`, `k`, optional `types` | `id`, `title`, `score`, `excerpt`, `source`, `tenant` |
| | `search.keyword` | `query`, `k`, optional `types` | the same |
| **graph** | `graph.neighbours` | `id`, optional `edge`, `depth` | `id`, `type`, `edge`, `title` |
| | `graph.query` | a read-only query in the source's language | rows, each with `id` |
| **code** | `code.find` | `name` fragment | `qualified_name`, `file`, `line`, `kind` |
| | `code.outline` | `file` | declarations with line ranges |
| | `code.source` | `qualified_name` | the source text, `file`, `line` |
| | `code.related` | `qualified_name` | callers, callees, dependents |
| **index** | `index.refresh` | `paths` | the paths re-read, or why not. **A write**, not a read: it is the action `code.index.refresh`, automatic only for a local index, an intent for a remote one (SH-089) |
| **tickets** | `tickets.get` | `id` | `id`, `title`, `status`, `body`, `url` |
| | `tickets.search` | `query`, `k` | `id`, `title`, `status`, `url` |
| **decisions** | `decisions.find` | `question`, `k` | `id`, `question`, `answer`, `scope`, `decided_on`, `score` |
| | `decisions.record` | a decision record ([schemas/decision.schema.json](../schemas/decision.schema.json), SH-087) | `id` |
| **ingest** | `ingest.document` | a stamped document and its `type` | `id`, or a `job` to poll |
| | `ingest.status` | `job` | `state`, `detail` |

A capability a source does not offer is **absent**, never emulated: the adapter says so,
`sky doctor` shows it, and a skill that needs it stops with that reason.

## Rules every source is held to

1. **Hits are cited.** An `id` is stable and enough to fetch the hit again; a skill
   writes it where a claim rests on it.
2. **Tenants are visible.** A server that holds more than one tenant puts the tenant on
   every hit; the launcher refuses to cross a privacy boundary, and the hit shows which
   side it is on.
3. **Reads are reads.** Nothing under search, graph, code or tickets changes state.
   `index.refresh` is the one mutation on the code side and is bound to its own action;
   it is never part of the read-only code group a role holds.
4. **Writes are gated.** `ingest.document` into a remote source is the outward action
   `kb.ingest`: prepared by a run, performed by a person. Into the local store under
   `.sky/kb/` it is a local edit. `decisions.record` follows the same split.
5. **Budgets are measured, not promised.** Every hit's `excerpt` is bounded; the
   retriever's manifest (SH-068) records what was fetched and how large it was.

## Adapters

An adapter is a mapping in `.sky/context.yaml` from the protocol's operation names to a
server's tool names, with the arguments renamed where needed:

```yaml
sources:
  kb:                                 # the knowledge port, as shipped today
    server: kb
    search.similar:  { tool: kb_similarity_search, args: { query: query, top_k: k } }
    search.keyword:  { tool: kb_search,            args: { query: query, top_k: k } }
    graph.neighbours:{ tool: kb_graph_query }
    ingest.document: { tool: kb_documents_ingest }
    ingest.status:   { tool: kb_jobs_status }
  code:                               # skygraph, the first code server (SH-040)
    server: code
    code.find:    { tool: find_symbols,  args: { name: query } }
    code.outline: { tool: outline_file,  args: { file: filepath } }
    code.source:  { tool: read_source }
    code.related: { tool: related_symbols }
  local:                              # the local store (SH-083)
    server: sky_kb
    search.keyword:   { tool: search }
    graph.neighbours: { tool: neighbours }
    decisions.find:   { tool: decisions_find }
    decisions.record: { tool: decisions_record }
    ingest.document:  { tool: ingest }
```

The tool names on the right are what the policy binds to actions (SH-064) and what the
host enforces; the names on the left are what skills say. `sky policy lint` fails when
an adapter names a tool with no binding, and `scripts/check-allowlists.py` fails when it
names a tool the server does not have.

The knowledge port keeps its `kb_` prefix: it is a product's spelling, and the adapter
is where spellings belong. The decision SH-024 asked for is therefore: **bare names in
the protocol, product names in the adapter, no renaming of servers.**

## What the probes check

`sky doctor` resolves `.sky/context.yaml`, asks each server for its tool list, and shows
one row per capability: `ok` when every operation the adapter maps exists on the server,
`MISSING` with the first missing tool, or `absent` when the adapter maps nothing for it.
The row for `decisions` reads `absent` until a source offers it.

## Diagram sources

None; this page is a table.
