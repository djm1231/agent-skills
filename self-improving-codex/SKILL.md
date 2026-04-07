---
name: self-improving-codex
description: Codex self-improvement workflow for recording task outcomes, summarizing prior-day work, promoting repeated learnings or errors into stable memory, creating periodic memory snapshots, and rolling back memory state safely. Use implicitly on most new non-trivial threads and substantive tasks so Codex can maintain long-lived habits across sessions, update PROFILE/ACTIVE/LEARNINGS/ERRORS/FEATURE_REQUESTS memory files, checkpoint memory after meaningful work, summarize yesterday's journal on the first substantial task of a new day, or recover from a bad memory state. Skip only for trivial chat or tasks with no durable value.
---

# Self-Improving Codex

## Overview
Use this skill to keep Codex's local memory consistent, useful, and recoverable. It combines a human-readable memory layout with a deterministic Python manager so Codex can record lessons quickly without turning one bad update into permanent prompt pollution.

## Workflow

1. Run preflight before substantive work.
   - Use `python <skill-dir>/scripts/memory_manager.py preflight`.
   - This initializes the memory store if needed.
   - This also summarizes unsummarized prior days and creates a snapshot when more than 2 hours have passed since the last snapshot.
2. Record outcomes after the task.
   - Use `record --kind learning` for successful patterns worth remembering.
   - Use `record --kind error` for mistakes, regressions, or failure modes.
   - Use `record --kind feature-request --accept-feature-request` only when a request is explicitly accepted as a long-term item. Unaccepted requests stay in the journal until they repeat.
3. Let promotion stay conservative.
   - Raw events always land in the daily journal first.
   - Stable memory is updated only after repeated observations on different days, unless `--promote --promotion-reason ... --confidence 0.75+` is explicitly used.
4. Use snapshots for safety, not as a replacement for judgment.
   - List snapshots before rollback.
   - Roll back only the memory directory managed by this skill.

## Commands

The manager script lives in `scripts/memory_manager.py`.

Common commands:

```powershell
python C:\Users\djm_1\.codex\skills\self-improving-codex\scripts\memory_manager.py init
python C:\Users\djm_1\.codex\skills\self-improving-codex\scripts\memory_manager.py preflight
python C:\Users\djm_1\.codex\skills\self-improving-codex\scripts\memory_manager.py record --kind learning --title "Use targeted repo searches first" --summary "Searching the real codebase before asking questions prevents low-value clarification loops."
python C:\Users\djm_1\.codex\skills\self-improving-codex\scripts\memory_manager.py list-snapshots
python C:\Users\djm_1\.codex\skills\self-improving-codex\scripts\memory_manager.py rollback --id 2026-04-07T16-30-00+08-00
```

Useful flags:

- `--memory-root <path>`: Use an isolated memory directory for testing.
- `--now <iso-datetime>`: Simulate time for validation or backfills.
- `--promote`: Force a learning or error into stable memory only with `--promotion-reason` and confidence `>= 0.75`.
- `--accept-feature-request`: Accept a feature request into long-term memory immediately instead of waiting for repeated evidence.

## Recording Guidance

Prefer short, durable statements.

- Good learning title: `Search likely config files before asking for paths`
- Bad learning title: `Today I searched some files and it worked`
- Good error title: `Do not roll back memory outside the managed skill root`
- Bad error title: `Rollback issue`

Keep summaries stable enough that they will still be true later. Put temporary specifics in `--details` or the journal entry, not in the promoted rule text.

## Managed Memory

This skill manages:

- `PROFILE.md`
- `ACTIVE.md`
- `LEARNINGS.md`
- `ERRORS.md`
- `FEATURE_REQUESTS.md`
- `journal/`
- `summaries/`
- `snapshots/`
- `catalog/`
- `state.json`

Read these references when needed:

- `references/memory-model.md`
- `references/promotion-policy.md`
- `references/rollback-policy.md`

## Safety Rules

- Keep long-lived changes inside the managed memory directory instead of rewriting `AGENTS.md` for routine learning.
- Treat rollback as memory-only recovery. Do not use it to restore skill code, config files, or unrelated workspaces.
- Expect stable memory to be curated. If a rule is only seen once, keep it in the journal unless the evidence is unusually strong.
