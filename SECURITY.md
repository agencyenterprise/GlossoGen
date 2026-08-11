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

## Scope

Reports about the platform itself are in scope: the simulation runtime, the
evaluation pipeline, the FastAPI server (including the identity middleware and
the MCP OAuth flow), and the Next.js frontend.

Some things are known, documented properties rather than vulnerabilities:

- **Local mode performs no authentication.** With `CLERK_SECRET_KEY` unset, every
  request runs as `local-user` in the `local` group. It exists for local
  development and must not be exposed to a network. This is stated in the README
  and is not a finding.
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
