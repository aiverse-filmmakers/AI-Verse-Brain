# AI-Verse Brain

**A universal intelligence layer for AI agents: persistent intent, goals, initiative, planning, reflection, verification, learning, and controlled self-improvement.**

AI-Verse Brain is designed to work with capable agents on its own and to integrate deeply with AI-Verse OS and AI-Verse Memory without becoming either of them.

> Status: Phase 4 alpha implementation. The current branch contains the deterministic core, Direction/Attention/Action/Evaluation/Learning engines, and a read-only integration/cadence/doctor slice. Nothing in this branch has been installed into or merged with AI-Verse OS or AI-Verse Memory.

## Responsibility split

```text
Brain  = why / where / what next / how to verify / how to improve
OS     = structure / scope / routing / capabilities / connections / execution boundaries
Memory = historical recall / provenance / supersession
Host   = model and tool execution
```

The Brain does not become a second OS, scheduler, memory database, connection manager, capability registry, or autonomous authority source.

## Governing principle

> The Brain continuously works to reduce the gap between explicitly desired states and observed current states, while respecting user authority, scope isolation, limited attention, available capabilities, evidence, uncertainty, safety, permissions, and resource limits.

## Implemented Phase 4 slices

The deterministic core provides scoped canonical Brain objects, lifecycle state machines, authority and permission gates, evidence-backed verification, cadence triggers, optimistic concurrency, runtime locking, path isolation, and canonical write routing.

The functional intelligence slice adds gap/opportunity/initiative discovery, dedupe and cooldown, attention budgets, progress/stall tracking, independent evaluation, belief freshness, staged learning, and controlled strategy evolution.

The integration slice adds **read-only** host inspection, native path contracts, dry-run integration planning, cadence requests, and `doctor`. It explicitly refuses to fall back to standalone storage when an incompatible `AI-VERSE.yaml` is present.

## Integration safety

AI-Verse OS and AI-Verse Memory remain separate repositories. Memory is optional. The Brain only maps their canonical ownership boundaries and does not copy or merge their implementations.

If a compatible AI-Verse OS v2 host lacks an `extensions.brain` slot, the integration planner reports a blocker rather than editing `AI-VERSE.yaml` implicitly.

## Development

```bash
python -m unittest discover -s tests -v
ai-verse-brain doctor .
ai-verse-brain plan-integration .
ai-verse-brain plan-cadence --scope operator --proactivity 2
```

The current implementation uses only the Python standard library and targets Python 3.9+.

CI tests Python 3.9 and 3.12 on Ubuntu, macOS, and Windows.

## Protocols and research

Implementation contracts live in [`protocol/`](protocol/). The complete Phase 1-3 research and adversarial design work remains preserved in [`research/`](research/README.md).

## License

A release license has not yet been finalized for the Brain repository.
