# Memory Model

This skill keeps a small set of human-readable memory files plus a structured catalog that powers deterministic updates.

## Layout

- `PROFILE.md`: Stable preferences, collaboration style, and durable facts about how Codex should work with the user.
- `ACTIVE.md`: The highest-signal reminders Codex should keep in working memory right now.
- `LEARNINGS.md`: Promoted positive patterns that proved reusable.
- `ERRORS.md`: Promoted failure modes and prevention rules.
- `FEATURE_REQUESTS.md`: Persistent ideas, follow-ups, and wishlist items.
- `journal/YYYY-MM-DD.md`: Raw day-by-day events in human-readable form.
- `summaries/YYYY-MM-DD.md`: One summary per completed day, generated on the next day's first substantive preflight.
- `catalog/*.json`: Structured backing data used to render stable Markdown files.
- `state.json`: Operational state such as last snapshot time and last summarized day.

## Journal First, Stable Memory Second

Every recorded event goes to the journal first.

Stable memory is promoted from repeated observations:

- Learnings promote into `LEARNINGS.md`
- Errors promote into `ERRORS.md`
- Feature requests enter `FEATURE_REQUESTS.md` only after repeated evidence or explicit acceptance

This keeps one-off events from polluting long-lived instructions.

## Active Memory

`ACTIVE.md` is regenerated from the latest stable memory and automation state. It is intentionally short:

- recent guardrails from `ERRORS.md`
- recent proven patterns from `LEARNINGS.md`
- open items from `FEATURE_REQUESTS.md`
- snapshot and summary status from `state.json`

## Structured Metadata

Promoted learning and error entries track:

- `confidence`
- `source_dates`
- `applications`
- `last_validated`
- `evolution_note`

These fields exist to support future tightening, pruning, or demotion logic without hand-editing every Markdown file.
