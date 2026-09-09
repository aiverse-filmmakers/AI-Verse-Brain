# Integration and Cadence Contract

This slice keeps all implementation inside AI-Verse-Brain. It does not install into, merge with, or modify AI-Verse OS or AI-Verse Memory.

## Host detection

Brain distinguishes three cases:

```text
standalone
compatible AI-Verse OS v2 unified-workspace
incompatible AI-Verse manifest
```

If `AI-VERSE.yaml` exists but the host is not a compatible v2 `unified-workspace` layout, Brain **refuses standalone fallback**. This prevents accidental creation of a second parallel state hierarchy inside an older or incompatible AI-Verse repository.

## Read-only native path contract

For compatible native mode Brain maps ownership without copying it:

```text
Brain state       operator/brain/ or workspaces/<id>/brain/
current state     operator/workspace context CURRENT.md
history           operator/workspace memory
settled decisions operator/workspace decisions
knowledge         shared/workspace knowledge
```

Only the Brain-state path is Brain-owned.

## Memory

AI-Verse Memory is optional. Detection is informational and read-only. Brain does not copy Memory code, create a second historical store, or require Memory for standalone operation.

## Extension registration

The current AI-Verse OS contract may not yet expose `extensions.brain`. The integration planner therefore reports this as a blocker rather than silently patching `AI-VERSE.yaml`.

A future explicit integration step may register Brain only after the OS contract intentionally exposes a supported slot.

## Integration planner

`plan_integration()` is dry-run/read-only. It reports intended ownership paths, blockers, and notes. It performs no installation.

## Doctor

`run_doctor()` is read-only. It checks:

- host contract compatibility;
- accidental standalone store inside native mode;
- optional Brain extension slot;
- optional Memory presence;
- Brain JSON scope matching its physical operator/workspace location;
- Brain JSON kind matching its canonical kind directory.

Warnings are not failures. Scope leakage and incompatible host fallback are failures.

## Cadence ownership

Brain owns **when cognition would be useful**, not scheduler implementation.

`plan_cadence()` emits scheduling requests for a host. It does not create cron jobs or background daemons.

All proactivity levels can use session start/end hooks. P0/P1 receive no default scheduled background cadence. P2+ may request bounded scheduled orientation and strategic review.

The orientation interval is derived from `max_background_ticks_per_day`; increasing proactivity does not bypass this resource cap and does not grant action permissions.
