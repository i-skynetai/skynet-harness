# The knowledge port

The harness retrieves from a knowledge base over MCP. It is not tied to any particular
one — the port is a small set of operations plus a tool-name prefix.

## The operations

| Operation | Purpose |
|---|---|
| `search` | orchestrated search across the KB |
| `similarity_search` | raw vector hits, no synthesis — fast |
| `agentic_search` | vector hits plus one-hop graph evidence |
| `context_search` | retrieval with an answer synthesised |
| `layer_search` | per-layer breakdown |
| `graph_query` | read-only graph query, for precise structural answers |
| `ontologies_list` / `ontologies_get` | discover and fetch ontologies |
| `jobs_status` / `jobs_output` | poll asynchronous work |
| `documents_ingest` | write a document; starts a job. An outward action (`kb.ingest` in the policy), used by `/sky:learn` and `sky doctor --deep` |

A provider does not have to implement all of them. `doctor` reports which are present
and the skills degrade to what exists — a missing `graph_query` means graph-shaped
questions are unavailable, not that the run fails.

## The prefix

MCP tools are named `<prefix>_<operation>` — the default prefix is `kb`, giving
`kb_search`, `kb_graph_query`, and so on. The full tool name a host sees is
`mcp__<server>__<prefix>_<operation>`.

To point the harness at a knowledge base whose tools use a different prefix, change it
in `plugin/policy.yaml` where the allowlist names the tools, and in `KB_PREFIX` in
`core/sky/probes.py`, which the readiness checks use. Nothing else in the core knows
the prefix; a test fails if a check calls a tool the policy does not name.

## Writing a provider

A provider is an MCP server exposing the operations above. The harness calls it over
JSON-RPC:

```json
{
  "jsonrpc": "2.0", "id": 1, "method": "tools/call",
  "params": {
    "name": "kb_search",
    "arguments": { "tenant_code": "DEMO0001", "query": "how does ingest work" }
  }
}
```

Three things the harness expects:

1. **Tenant scoping on every call.** `tenant_code` is passed on every request. A KB that
   ignores it will leak between tenants, and the harness has no way to detect that.
2. **A bearer token.** Supplied from the environment variable named in `pat_env`. The
   token never appears in a config file.
3. **An honest empty result.** Return no hits rather than an approximation. A probe that
   counts another tenant's rows as healthy is worse than a probe that fails.

## Configuring one

`config/kb-map.json`:

```json
{
  "work_kb": {
    "mcp_url": "https://your-kb.example.com/mcp/",
    "tenant_code": "DEMO0001",
    "pat_env": "SKY_PAT_WORK",
    "repos": ["/path/to/a/repository"]
  },
  "client_kb": {
    "mcp_url": "https://other-kb.example.com/mcp/",
    "tenant_code": "DEMO0002",
    "pat_env": "SKY_PAT_CLIENT",
    "repos": ["/path/to/a/client/repository"]
  }
}
```

Resolution order for a repository: a path listed under a KB's `repos`, then a `brain:`
line in the repository's `CLAUDE.md` or `AGENTS.md`, then the default.

**A repository under a client KB never falls back to a work default.** It gets no KB and
a message saying so. Retrieving a client's answer from the wrong knowledge base is worse
than retrieving nothing.
