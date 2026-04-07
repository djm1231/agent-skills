# agent-skills

A collection of reusable agent skills for Codex and other AI coding agents.

## Available skills

### `self-improving-codex`

A Codex-native self-improvement skill that helps Codex build durable working memory across sessions without turning one-off observations into permanent prompt pollution.

It includes:

- structured long-term memory files
- conservative promotion of repeated learnings and recurring errors
- automatic preflight checks for substantive work
- periodic memory snapshots
- safe rollback for memory state recovery

## Install

Install the skill from this repository:

```bash
npx skills add djm1231/agent-skills/self-improving-codex
```

## Repository layout

```text
self-improving-codex/
├── SKILL.md
├── agents/
│   └── openai.yaml
├── references/
│   ├── memory-model.md
│   ├── promotion-policy.md
│   └── rollback-policy.md
└── scripts/
    └── memory_manager.py
```
