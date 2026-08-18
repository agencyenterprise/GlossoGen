# MCP integration

The backend exposes an MCP server at `/mcp`, so an LLM client such as Claude Code
or Cursor can browse runs and launch simulations directly. It is mounted inside the
existing FastAPI app and protected by OAuth 2.0.

**Requires `OAUTH_ISSUER_URL`**, set to the public backend URL (e.g.
`http://localhost:8000`). Without it the endpoint is not mounted.

## Connecting

Click **MCP** on the runs page for copy-paste instructions, or configure manually.

Claude Code:

```bash
claude mcp add-json glossogen-runs '{"type":"http","url":"http://localhost:8000/mcp"}'
```

Cursor, in `.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "glossogen-runs": {
      "url": "http://localhost:8000/mcp"
    }
  }
}
```

No auth headers. The client discovers OAuth metadata at
`/mcp/.well-known/oauth-authorization-server` and handles registration,
authorization and token refresh on its own, using the authorization-code flow with
PKCE and dynamic client registration.

Every token is bound to one group at consent time, so each tool call is scoped
automatically:

- **Local mode** auto-approves to the synthetic `local` group.
- **Clerk mode** parks the authorization request, redirects the browser to the
  frontend at `/mcp-consent?request_id=...` where Clerk forces sign-in, and the
  user picks which organization to authorize. The frontend posts back with a fresh
  Clerk JWT; the backend resolves the active org to a group, mints the code bound
  to that `group_id`, and redirects to the client's callback.

Access tokens last an hour, refresh tokens thirty days. Token state lives in
Postgres, or in memory in no-database local mode, where re-authenticating after a
restart is the only consequence.

## Tools

| Tool | |
|---|---|
| `list_scenarios` | Available scenarios with their knobs presets, metrics and supported models |
| `list_runs` | Paginated, filterable by scenario, model, fork status, run status and labels |
| `get_run_metadata` | Agents, channels, configuration, evaluation summary, labels, full lineage |
| `list_derived_runs` | Every run derived from a parent, with derivation type, round boundaries and headline scores |
| `get_run` | Full content with messages; opt-in reasoning, tool use, debug logs, system prompts |
| `get_knobs_schema` | A scenario's knobs JSON Schema plus its preset names |
| `get_knobs_preset` | One preset's payload |
| `start_run` | Launch a simulation with scenario, model, provider and knobs |
| `export_run_artifacts` | Download URL for a tar.gz bundle of the run directory |
| `export_agent_thread` | One agent's thread as a drop-in Anthropic or OpenAI request body |

A run-start conversation usually goes: `get_knobs_schema` to see the fields and
preset names, `get_knobs_preset` to load a baseline, then `start_run` with the
model, provider and final knobs. `start_run` validates provider names and agent ids
in `model_overrides` before launching, so a typo fails fast instead of producing a
misconfigured run.

`list_derived_runs` reads the runs-index parent linkage, so it can return fewer
runs than a grouping label that spans a whole experiment family.

## From the CLI

The same OAuth flow gives the CLI a way to talk to a deployed, Clerk-protected
backend. It calls the existing REST endpoints; there is no separate upload feature
on the server.

```bash
# One-time: sign in. Opens the browser to the Clerk-gated consent page; the CLI's
# loopback server collects the code and writes ~/.glossogen/credentials.json (0600).
glossogen login --url https://your-backend.example.com

# Which group is this token bound to?
glossogen whoami

# Diff local runs against the remote and upload what is missing. Idempotent on
# run_id, so re-running is safe.
glossogen push-to-prod --label baseline --runs-dir ./runs
```

`push-to-prod` flags:

- `--scenario <name>` (repeatable) restricts to specific scenarios.
- `--label <label>` (repeatable, AND) requires every listed label.
- `--include-incomplete` allows runs with no evaluation report; by default those
  are skipped, which is what keeps crashed runs out.
- `--dry-run` prints the diff without sending bytes.
- `--concurrency N` (default 1, clamped to 16) parallelizes uploads. Keep it small:
  each upload holds its bundle in memory.

For runs already on the remote whose local labels or report have since changed:

```bash
glossogen sync-metadata-to-prod --runs-dir ./runs
```

It PUTs local labels when they differ from the remote's, and PUTs the local
evaluation report unconditionally, treating local as the source of truth. Same
`--scenario` and `--dry-run` flags; `--concurrency` defaults to 4 (clamped to 8), higher
than `push-to-prod` because the bodies are a label list and a JSON report rather
than a bundle.

The identity middleware accepts an MCP OAuth bearer for `/mcp/*` tool calls and for
`/api/g/{slug}/...` REST calls alike, so one token covers browsing in Claude Code,
pushing bundles and syncing labels.
