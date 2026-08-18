# Security Policy

## Reporting a vulnerability

**Please do not open a public issue for security problems.**

Report privately through GitHub's
[private vulnerability reporting](https://github.com/agencyenterprise/GlossoGen/security/advisories/new)
on this repository. That creates a draft advisory only maintainers can see.

Please include what you can:

- what the issue is and roughly how bad you think it is
- steps to reproduce, or a proof of concept
- the version or commit you tested
- whether it is already public anywhere

We will acknowledge receipt and tell you whether we consider it in scope. If we
fix it, we will credit you in the advisory unless you would rather we did not.

## Supported versions

This project is pre-1.0 and moves quickly. Fixes land on `main` and ship in the
next tagged release; older tags are not patched. If you are running a deployment,
track the latest release.

## Containment of simulated agents

All experiments take place in a closed environment. A simulated agent has no
pathway to another model, to the host system, or to anything outside its own
run.

**The tool surface is the whole surface.** The only tools an agent can call come
from a `comms` MCP server that the run process starts on `127.0.0.1` and that
dies with that process. It exposes communication primitives (read notifications,
read a channel, post to a channel, list channels, list members) plus whatever
tools the running scenario declares, and each agent is served only the subset its
allowlist permits. There is no shell, no filesystem access, no HTTP fetch, no
code execution, and no way for an agent to add a tool. Scenario tools read and
write simulation world state held in memory; nothing an agent writes is ever
executed.

**Agents cannot reach each other except through channels.** Agent identity is
resolved from the MCP connection URL, not from tool arguments, so one agent
cannot act as another. Membership is checked on every read and every send, so an
agent cannot address a channel it does not belong to.

**Agents do not originate model calls.** The runner holds the provider
credentials and issues each inference request on the agent's behalf. An agent has
no way to choose a model, reach a different provider, or direct its output
anywhere but a channel in its own simulation. The only network egress during a
run is the platform's own call to the configured inference endpoint, which may be
a hosted provider or a self-hosted server the operator points it at.

**Runs are bounded and terminal.** The game clock ends the simulation at
`round_count` and each agent runner stops at `max_agent_turns`. What an agent
produced is left behind as an append-only event log under `runs/`, read
afterwards by humans and by the evaluation pipeline. No output of a simulation is
fed back into a live system.

The operator-facing side of the platform (the FastAPI server, its provider keys,
the subprocesses it launches) is a normal piece of software with normal
privileges, and the notes below apply to it. The containment claim above is about
the simulated agents, which never touch it.

## Scope

Reports about the platform itself are in scope: the simulation runtime, the
evaluation pipeline, the FastAPI server (including the identity middleware and
the MCP OAuth flow), and the Next.js frontend.

Some things are known, documented properties rather than vulnerabilities:

- **Local mode performs no authentication.** With `CLERK_SECRET_KEY` unset, every
  request runs as `local-user` in the `local` group. It exists for local
  development and must not be exposed to a network. This is stated in
  [Deployment](docs/deployment.md) and [Web UI](docs/web-ui.md#authentication), and
  is not a finding.
- **Simulations execute LLM-authored tool calls** against scenario-defined tools
  by design. That is what the platform is for.
- **The server spawns subprocesses that spend money** on the operator's provider
  keys. There is no spend cap in the platform; any authenticated user who can
  start a run can incur cost.

A way to escape those documented boundaries, such as reaching another tenant's runs,
bypassing the identity middleware, executing code outside a simulation's intended
surface, is very much in scope.

## Operator notes

Two things matter most when deploying this:

**Set `CLERK_SECRET_KEY`.** Without it the server is unauthenticated. There is no
warning loud enough to substitute for checking.

**Provider keys are spending credentials.** They are read from the environment and
used by subprocesses the server launches. Scope them to the minimum and set
billing alerts with your provider. The platform enforces no budget of its own.
