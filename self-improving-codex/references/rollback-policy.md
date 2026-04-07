# Rollback Policy

Rollback is intentionally narrow.

## What Rollback Restores

Rollback restores only the managed memory root:

- Markdown memory files
- `journal/`
- `summaries/`
- `catalog/`
- `state.json`

It does not restore:

- skill code
- `AGENTS.md`
- Codex config files
- other memories
- project workspaces

## Safety Steps

Before restoring a target snapshot, the manager always creates a rescue snapshot with a `pre-rollback` reason. That gives you a quick undo path if the chosen snapshot was wrong.

The snapshot archive excludes the `snapshots/` directory itself so rollback never recursively restores old archives over new ones.

By default, destructive operations are only allowed against the canonical root:

- `C:\Users\djm_1\.codex\memories\self-improving-codex`

Use `--allow-unsafe-root` only for isolated test directories that were intentionally initialized by this skill.

## Retention

Snapshots are kept for `180` days by default.

Use:

```powershell
python C:\Users\djm_1\.codex\skills\self-improving-codex\scripts\memory_manager.py prune --keep-days 180
```

## Recommended Recovery Flow

1. Run `list-snapshots`.
2. Pick the snapshot created before memory quality regressed.
3. Run `rollback --id <snapshot-id>`.
4. Re-run `preflight` so `ACTIVE.md` and summary state reflect the restored memory cleanly.
