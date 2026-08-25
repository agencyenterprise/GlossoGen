# GlossoGen

**[Documentation](https://agencyenterprise.github.io/GlossoGen/)** ·
[Quickstart](https://agencyenterprise.github.io/GlossoGen/latest/quickstart/) ·
[Scenarios](https://agencyenterprise.github.io/GlossoGen/latest/scenarios/) ·
[Live demo](https://emergentcomms.ai/demo)

A platform for studying how LLM agents communicate when they have to. Agents are
put in a simulated task where no single one of them holds enough information to
succeed, so nothing gets solved without talking. In most scenarios every character
they send then costs against a fixed per-round budget, and under that pressure they
compress, abbreviate, and invent shorthand. The platform records all of it and
scores it afterwards.

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
