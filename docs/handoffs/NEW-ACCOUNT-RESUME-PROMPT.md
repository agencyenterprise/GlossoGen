# New Account Resume Prompt

Paste the following into a new Codex task opened at the root of this repository:

```text
I am continuing the Covenant Game multi-agent research in this repository after
moving accounts/workspaces.

Before proposing changes or launching experiments, read these files completely:

1. docs/handoffs/COVENANT-GAME-HANDOFF.md
2. docs/research/covenant-game/README.md
3. docs/research/covenant-game/research-summary.md
4. docs/research/covenant-game/experiments/README.md
5. docs/research/covenant-game/experiments/EXP-020-cross-model-compatibility/experiment.md
6. docs/research/covenant-game/experiments/EXP-021-cheap-model-seed-replication/experiment.md
7. .agents/skills/record-experiment/SKILL.md

Treat committed experiment records, bundled configs, checked analysis scripts,
and raw event logs as authoritative over conversational memory. Preserve all
existing user changes and the unrelated .claude/worktrees/ directory.

Then give me:

- a concise summary of the original objective and current scenario;
- the supported, contradicted, and untested claims;
- the exact replication status by model;
- the principal methodological limitations;
- the decision-relevant next experiment options and their cost/information
  trade-offs;
- any missing local artifacts that prevent full reproducibility.

Do not launch a run until we select one scientific question and preregister its
decision rule, conditions, seeds, model/provider, rounds, stopping rule, frozen
configs, analysis plan, and budget using the record-experiment skill.
```

## Account-migration notes

- The Git repository is the durable source of research context; account chat
  history is only supplementary.
- Ensure the current branch and commits are pushed to a remote accessible from
  the company workspace.
- Transfer raw run directories only through an approved storage location; they
  are gitignored and may contain sensitive operational data.
- Move the presentation PDF and editable source into a company-controlled
  location.
- Do not copy an entire user-level Codex configuration or authentication
  directory between accounts. Reconfigure account credentials and any private
  connectors in the company workspace.
