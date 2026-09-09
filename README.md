# AI-Verse Brain

**A universal intelligence layer for AI agents: persistent intent, goals, initiative, planning, reflection, verification, learning, and controlled self-improvement.**

AI-Verse Brain is designed to work with capable agents on its own and to integrate deeply with AI-Verse OS and AI-Verse Memory.

> Status: Phase 4 implementation is in progress. The current branch establishes the deterministic core. It is not yet a stable release and should not be installed into production AI-Verse OS repositories.

## Responsibility split

```text
Brain  = why / where / what next / how to verify / how to improve
OS     = structure / scope / routing / capabilities / connections / execution boundaries
Memory = historical recall / provenance / supersession
Host   = model and tool execution
```

The Brain does not become a second OS, scheduler, memory database, connection manager, or autonomous authority source.

## Governing principle

> The Brain continuously works to reduce the gap between explicitly desired states and observed current states, while respecting user authority, scope isolation, limited attention, available capabilities, evidence, uncertainty, safety, permissions, and resource limits.

## Phase 4 core

The first implementation slice establishes:

- a common canonical object envelope with revisions and immutable scope;
- deterministic lifecycle state machines;
- explicit authority tiers and privileged-field protection;
- proactivity levels separated from action permissions;
- hard-gated initiative ranking with inspectable score components;
- completion criteria that begin unverified and require evidence to pass;
- cadence trigger envelopes and idempotent trigger claims without implementing a scheduler;
- native AI-Verse and standalone storage layouts;
- optimistic-concurrency atomic writes;
- symbolic write routing so Brain state cannot silently become OS or Memory truth;
- a runtime-neutral host protocol;
- JSON Schemas and unit tests.

The full design rationale is preserved in [`research/`](research/README.md), especially the [Phase 3 specification](research/PHASE-3-BRAIN-SPECIFICATION.md) and [QC risk matrix](research/PHASE-3-QC-RISK-MATRIX.md).

## Development

```bash
python -m unittest discover -s tests -v
```

The core currently uses only the Python standard library. Python 3.9+ is targeted.

## License

A release license has not yet been finalized for the Brain repository.
