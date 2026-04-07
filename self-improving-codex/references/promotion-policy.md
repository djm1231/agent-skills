# Promotion Policy

This skill stays conservative by default.

## Default Rule

Promote a learning or error only when both conditions are true:

1. The same normalized title has been observed on at least 2 distinct dates.
2. The event has enough signal to be reusable, usually a confidence of at least `0.6`.

If either condition is missing, keep the entry in the journal only.

## Forced Promotion

Use `record --promote` when:

- the evidence is unusually strong
- the rule is clearly durable
- waiting for a second observation would be more harmful than helpful
- you can provide a concrete `--promotion-reason` and a confidence of at least `0.75`

Forced promotion should still be rare.

## Confidence Heuristic

The manager computes confidence from repeated observation:

- start from the event confidence, default `0.6`
- add a small boost for each distinct day the pattern reappears
- cap at `0.95`

The goal is not statistical rigor. The goal is to make it obvious which entries are strong enough to trust.

## Evolution Notes

Every promoted entry stores an `evolution_note` that explains why it changed. Use it to capture:

- what triggered the promotion
- when a summary was tightened
- when a rule merged multiple similar observations

## Demotion Philosophy

This version does not auto-delete promoted memory. Instead:

- use rollback when a bad promotion contaminates memory broadly
- edit the catalog later if a rule clearly becomes stale

That keeps v1 predictable and easy to audit.
