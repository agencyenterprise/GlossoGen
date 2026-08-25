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
next tagged release. Older tags are not patched. If you are running a deployment,
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
write simulation world state held in memory. Nothing an agent writes is ever
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

- **Single-tenant mode performs no authentication.** With no identity provider installed, every
  request runs as `local-user` in the `local` group. It exists for local
  development and must not be exposed to a network. This is stated in
  [Deployment](docs/deployment.md#authentication), and
  is not a finding.
- **Simulations execute LLM-authored tool calls** against scenario-defined tools
  by design.
- **Nothing in the platform caps spend.** Three things start a process that spends
  the operator's provider keys, and each needs a different thing to reach:
  `glossogen run` and `glossogen evaluate` need a shell on the host; the MCP
  `start_run` tool needs an OAuth token consented to a group; and
  `POST /api/g/{slug}/runs/{scenario}/{run_dir_name}/evaluate` pays for whichever
  judge-backed metrics it was asked for, and is the one of the three that can be
  switched off, with `ENABLE_EVALUATIONS=false`. No REST endpoint starts a
  simulation, so signing in to the web UI does not get you one: the UI's only
  spending button is Run Eval, which calls that endpoint. Once a process is
  started, nothing bounds what it spends.

Escaping one of those boundaries is in scope. Reading another group's runs, getting
past the identity middleware, or making a simulation execute something its tool
surface does not allow: report any of those.

## Operator notes

Two things matter most when deploying this:

**Install an identity provider.** Without one the server is unauthenticated.

**Provider keys are spending credentials.** They are read from the environment and
used by subprocesses the server launches. Scope them to the minimum and set
billing alerts with your provider. The platform enforces no budget of its own.
