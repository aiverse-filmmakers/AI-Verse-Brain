# AI-Verse Brain

**A universal intelligence layer for AI agents: persistent intent, goals, initiative, planning, reflection, verification, learning, and controlled self-improvement.**

AI-Verse Brain is designed to work with capable agents on its own and to integrate deeply with AI-Verse OS and AI-Verse Memory without becoming either of them.

> Status: Phase 4 implementation is in progress. The current branch contains the deterministic core plus the first functional Direction, Attention, Action/Progress, Evaluation, Freshness, and Learning/Evolution engines. It is still an alpha development branch and is not installed into AI-Verse OS or AI-Verse Memory.

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

## What Phase 4 now implements

### Deterministic core

- canonical Brain objects with immutable scope, revision numbers, atomic writes, and per-object locks;
- lifecycle state machines for intent, practices, opportunities, initiatives, objectives, beliefs, learning, strategies, and policies;
- explicit authority tiers and privileged-field protection;
- proactivity levels separated from action permissions;
- symbolic write routing so Brain state cannot silently replace OS or Memory truth;
- cadence trigger envelopes and idempotent receipts without implementing a scheduler;
- native AI-Verse path detection and standalone storage;
- path traversal, symlink escape, duplicate side-effect, and stale-writer protections.

### Direction and initiative

- model-proposed gaps grounded in current-state and desired-state references;
- opportunity fingerprints, exact dedupe, dismissal/rejection cooldowns, and active-gap checks;
- hard eligibility gates before scoring;
- inspectable initiative ranking;
- qualified opportunity -> proposed initiative promotion with source linkage;
- active-initiative WIP caps.

### Attention and proactivity

- P0-P4 proactivity independent from execution authority;
- notification cooldowns by fingerprint;
- per-session proactive-item limits;
- daily interruption budgets;
- interruption downgrade to normal surfacing rather than repeated nagging;
- disposable attention ledgers with bounded retention.

### Action, progress, and verification

- objective completion criteria start unverified;
- tool activity alone never counts as progress;
- state change plus evidence is required for meaningful progress;
- progress ledger, attempt budget, non-progress stall detection, blocker state, and parallel-objective limits;
- V0-V3 verification levels;
- fresh-context and independent-evaluator requirements for higher verification levels;
- criterion-level evaluation evidence;
- missing evidence resolves to `INSUFFICIENT_EVIDENCE`, never silent success.

### Beliefs, learning, and evolution

- derived model beliefs track epistemic state, confidence, evidence, observation time, expiry, and maximum age;
- stale and contradicted beliefs cannot masquerade as current truth;
- contradicted beliefs require verified evidence to reactivate;
- learning progresses through evidence gates instead of instant self-belief;
- user-confirmation evidence cannot be fabricated by lower-authority sources;
- E1/E2 strategy rules require evaluations and regression checks;
- E3/E4 cannot be runtime-promoted: core/privileged evolution must go through tested code/review rather than self-rewriting.

## Protocol contracts

- [`protocol/BRAIN-PROTOCOL.md`](protocol/BRAIN-PROTOCOL.md): runtime order and ownership boundaries.
- [`protocol/DIRECTION-ATTENTION.md`](protocol/DIRECTION-ATTENTION.md): gap/opportunity/initiative and attention semantics.
- [`protocol/ACTION-VERIFICATION.md`](protocol/ACTION-VERIFICATION.md): objective progress and evidence-backed completion.
- [`protocol/LEARNING-EVOLUTION.md`](protocol/LEARNING-EVOLUTION.md): belief freshness, learning stages, and controlled strategy evolution.
- [`protocol/WRITE-CONTRACT.md`](protocol/WRITE-CONTRACT.md): canonical write ownership.

The design evidence remains preserved in [`research/`](research/README.md), especially the Phase 3 specification and adversarial QC risk matrix.

## Development

```bash
python -m unittest discover -s tests -v
```

The current implementation intentionally uses only the Python standard library and targets Python 3.9+.

CI tests Python 3.9 and 3.12 on Ubuntu, macOS, and Windows.

## Integration status

AI-Verse OS and AI-Verse Memory are **not dependencies of the core package and have not been modified by Phase 4**. Native-mode support currently means the Brain understands the AI-Verse path contract when placed in a compatible host fixture. Installer/registration work remains a later Phase 4 slice and must preserve the one-owner-per-state rule.

## License

A release license has not yet been finalized for the Brain repository.
