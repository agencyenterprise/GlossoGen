# Documentation style

How a documentation page here is shaped, and the review it gets when it changes.
The [writing rules in CLAUDE.md](../CLAUDE.md#writing) apply to every committed
word; this page adds what is specific to documentation. It is repository-only,
like everything else that is about working on the platform rather than using it.

## Where a page lives

| A page about | Lives | Example |
|---|---|---|
| Using the platform | the site: `nav` in [mkdocs.yml](../mkdocs.yml) | [evaluation.md](evaluation.md) |
| Working on the platform | the repository only | [Architecture.md](../Architecture.md), this page |
| What a study found | the repository only | [learnings.md](learnings.md), [communication-metrics.md](communication-metrics.md) |

Repository-only pages under `docs/` are listed in `REPO_ONLY_DOCS` in
[scripts/docs_hooks.py](../scripts/docs_hooks.py), which drops them from the build
and turns links to them into GitHub permalinks. Leaving a page out of the nav is
not enough: mkdocs publishes every file in `docs/` whether the nav names it or not.

## The shape of a page

- The first sentence is the page's job. The block right after it is the command or
  table the reader came for. No preamble.
- Each section answers one question a reader arrives with.
- An enumeration of three or more parallel facts is a table: flags, knobs, metrics,
  event types, prerequisites.
- A gotcha is a bold-led paragraph that states the action first, as in
  "**Wait for `simulation_ended` before evaluating.**" The reason follows in one
  or two sentences.
- The page ends with links to where the reader goes next.

## Prose earns its place

- **Rationale stays only when it changes what the reader does.** "Wait for
  `simulation_ended`, because round N's result is recorded when it ends" stays: it
  stops a reader corrupting their data. Why an interface was designed one way
  belongs in [Architecture.md](../Architecture.md) or in the commit that made the
  choice.
- **One home per fact**; every other page links there instead of restating it.
  Restated facts drift apart. The budget explanation lives in
  [scenarios.md](scenarios.md), the cost model in
  [running-simulations.md](running-simulations.md#understanding-cost).
- **A number is measured and reproducible, or absent.** Ranges come from the code
  ("the priced models span 25× on input"), costs from runs that happened, with the
  command that reproduces them.
- **Shown output is pasted from a terminal**, never written by hand. A reader who
  cannot match the page against their screen assumes their run is broken.
- **No machine tells.** The aphorism contrast ("the budget is a knob, not a
  rule") reads generated: the negated half is a strawman nobody proposed. Say
  what the thing is, and keep a negation only when it names a real alternative
  the reader would otherwise pick, the way "`agent_max_tokens`, not
  `LLM_MAX_TOKENS`" separates two settings that exist and get confused. The same
  goes for "not just X", paired fronted participles ("Installed, it is X;
  cloned, it is Y"), inflated words (robust, seamless, leverage, comprehensive),
  filler openers (Additionally, Moreover, it's important to note), and
  rule-of-three lists when three is not the real count. Finding these
  means reading every sentence; grepping finds the shapes but cannot make the
  call.
- **No counts of things that change.** "The four probe metrics" becomes a lie when
  the fifth lands, and nothing fails when it does. Name the property instead.

## Density bands

```bash
VIRTUAL_ENV= uv run --no-sync python scripts/measure_docs_style.py docs/*.md README.md
```

prints these per page. The bands come from this repository's own pages: the ones
that read well measure inside them, and the ones that had to be rewritten measured
outside.

| Measure | Band | Evidence |
|---|---|---|
| Prose words per heading | ≤ 150 | Readable pages measure 23–140; the rewritten ones measured 156–655 |
| Average sentence length | ≤ 20 words | The page that read worst averaged 25.2 |
| Paragraph length | None over 100 words; over 60 has to earn it | Before the first rewrite pass, `docs/` held 66 paragraphs over 60 words |
| Mid-sentence em-dashes | None | A dash defining a list item is fine; see CLAUDE.md |

A band triggers a review, nothing more. A page over one gets read again, and
prose that survives that reading stays.

## The review, per page

1. **Claim ledger.** Every command, flag, path and number on the page, checked
   against the code: flags against `_build_parser` in
   [cli.py](../src/glossogen/cli.py), metric names against `GENERIC_METRIC_NAMES`,
   knobs against the presets, anchors against the heading they point at. Each
   claim ends up verified, stale, or a question for a maintainer.
2. **Rewrite against the ledger.** Facts come from the ledger rather than from
   copy-editing the old prose.
3. **Measure.** Run the script before and after.
4. **Build.** `make docs-build` is strict and has to pass.
5. **Commit one page per commit**, with the before and after word counts and what
   the ledger caught in the message.
