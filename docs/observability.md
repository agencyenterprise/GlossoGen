# Observability

Simulation agents are instrumented through
[pydantic-ai](https://ai.pydantic.dev/)'s OpenTelemetry support, exporting every
LLM call (prompts, completions, tool calls, token usage, latency, cost) to a
**local, self-hosted [Langfuse](https://langfuse.com/)**, never a cloud endpoint.

```bash
make langfuse-up      # start the stack (web, worker, postgres, clickhouse, redis, minio)
make langfuse-down    # stop it
make langfuse-logs    # tail langfuse-web
```

## Pointing runs at the stack

A run traces when these three variables are in your `.env`:

```bash
LANGFUSE_PUBLIC_KEY=pk-lf-local-dev
LANGFUSE_SECRET_KEY=sk-lf-local-dev
LANGFUSE_HOST=http://localhost:3001
```

Those exact values are what the stack seeds on first boot and what
`.env.example` pre-fills, so an `.env` copied from it needs nothing. An `.env`
written before these lines existed needs them added.

## Reading a run's traces

The UI is at <http://localhost:3001>, since the frontend dev server owns 3000.
First boot takes a couple of minutes while migrations run.

Log in with:

- email `local@glossogen.dev`
- password `local-dev-password`

The account, the org, the project and the API keys above are all seeded on
first boot, so nothing has to be created in the UI.

Each run is one Langfuse session keyed by `run_id`. Every agent's cycles sit
underneath it, tagged by `agent_id` / `role_name` / `model` / `provider` /
`scenario`, and each generation carries its `round_number`.

## When tracing is on

Only for `glossogen run`. The judge and probe calls in `glossogen evaluate` are
not traced. If the stack is down or the keys are blank, a run logs one warning
and proceeds untraced. Telemetry never blocks a simulation.

The `make` targets above assume a checkout. Running the stack from an installed
package takes one extra step, in
[Tracing from your own project](installation.md#tracing-from-your-own-project).
