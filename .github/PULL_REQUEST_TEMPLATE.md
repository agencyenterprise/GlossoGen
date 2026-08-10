## What this changes

## Why

## Verification
<!-- How do you know it works? Commands run, output observed. "Lint passes" is
     necessary but rarely sufficient. -->

## Releasing

This pull request was opened with **`release:patch`** applied automatically.
Change it if that is wrong — exactly one of these must be set, and a required
check enforces it.

| Label | From `0.1.2` | Use for |
| --- | --- | --- |
| `release:patch` | `0.1.3` | Fixes, docs, internal changes — **the default** |
| `release:minor` | `0.2.0` | New functionality, backward compatible |
| `release:major` | `1.0.0` | Breaking change |
| `norelease` | — | Merges without cutting a release |

To swap the label, add the new one first and then remove `release:patch` — the
check will flag the moment both are on.

**Do not edit the version in `pyproject.toml` yourself.** On merge, a workflow
runs `uv version --bump <label>`, commits the result, tags it `vX.Y.Z`, and
publishes both images — so a hand-edit only conflicts with that commit.

Be aware what a release label does end to end: the tag publishes images, and
glossogen-deploy promotes them to production on its next hourly poll. Merging a
labelled PR is a deploy. Use `norelease` if you are not ready for that — the
change still lands on `main` and ships with whatever release comes next.

## Checklist
- [ ] `make lint` passes
- [ ] `make gen-api-types` produces no diff (if a response model changed)
- [ ] Docstrings on new modules and public functions
- [ ] No dead code left behind

