# GlossoGen

**[Documentation](https://agencyenterprise.github.io/GlossoGen/)** ·
[Quickstart](https://agencyenterprise.github.io/GlossoGen/latest/quickstart/) ·
[Scenarios](https://agencyenterprise.github.io/GlossoGen/latest/scenarios/) ·
[Live demo](https://emergentcomms.ai/demo)

A platform for running controlled experiments on teams of LLM agents. A scenario
puts several agents in a simulated task with their own roles, channels and tools;
the platform plays it out in rounds, records every message, tool call and model
response, and scores the run with the metrics you pick. The scenarios shipped
here study communication under pressure: no agent holds enough information to
succeed alone, and in most of them every character sent costs against a
per-round budget. Under that pressure agents compress, abbreviate, and invent
shorthand.

![Platform overview](images/platform_overview.webp)

Everything else lives in the
**[documentation](https://agencyenterprise.github.io/GlossoGen/)**: installing,
running and evaluating simulations, the web UI, the fork and swap flows, and how
to ship scenarios and metrics in a package of your own.

## Install

glossogen needs Python 3.12 and is not on PyPI, so pin a tag from
[the releases page](https://github.com/agencyenterprise/GlossoGen/releases):

```bash
uv add "glossogen @ git+https://github.com/agencyenterprise/GlossoGen.git@<tag>"
# or, with pip:
pip install "git+https://github.com/agencyenterprise/GlossoGen.git@<tag>"
```

[Installation](https://agencyenterprise.github.io/GlossoGen/latest/installation/) covers
the `.env` layout, the optional extras, and working on the platform from a clone.

## Contributing

[CONTRIBUTING.md](CONTRIBUTING.md) covers the conventions, the test suite and how
releases are cut. `make lint` and `make test` need to pass before a pull request.
For anything security-related, follow [SECURITY.md](SECURITY.md) rather than
opening a public issue.
