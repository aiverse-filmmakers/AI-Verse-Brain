# AI-Verse Brain

**A universal intelligence layer for AI agents: persistent intent, goals, initiative, planning, reflection, verification, learning, and controlled self-improvement.**

AI-Verse Brain is designed to work with capable agents on its own and to integrate deeply with AI-Verse OS and AI-Verse Memory without becoming either of them.

> Status: Phase 4 alpha implementation. Everything on the current branch remains inside `AI-Verse-Brain`; nothing has been installed into or merged with AI-Verse OS or AI-Verse Memory.

## Responsibility split

```text
Brain  = why / where / what next / how to verify / how to improve
OS     = structure / scope / routing / capabilities / connections / execution boundaries
Memory = historical recall / provenance / supersession
Host   = model and tool execution
```

## Current Phase 4 capabilities

The Brain now has a deterministic control core, Direction and Attention engines, progress/stall tracking, independent verification, belief freshness, staged learning/evolution, read-only AI-Verse integration inspection, cadence planning, and a read-only doctor.

Alpha.4 adds the missing cognition/action boundary:

- model-neutral cognition request/proposal envelopes;
- models can propose but cannot write lifecycle status, policy, permissions, scope, or privileged fields;
- deterministic tick planning maps cadence events to bounded reasoning jobs without invoking a model;
- action requests are separate from proactive recommendations;
- exact user approvals bind to request ID + idempotency key + scope + action class;
- every action carries an idempotency key;
- completed duplicate actions return the previous result without re-executing;
- autonomous side effects require host idempotency support;
- side-effect success requires a host receipt;
- uncertain external outcomes are blocked from automatic retry.

This preserves the central rule: **the model may reason about what should happen, but deterministic policy decides what may happen and the host proves what did happen.**

## Integration safety

AI-Verse OS and AI-Verse Memory remain separate repositories. Memory is optional. The Brain does not copy, merge, or mutate those repositories during Phase 4 development.

If a compatible AI-Verse OS v2 host lacks an `extensions.brain` slot, the integration planner reports a blocker rather than editing `AI-VERSE.yaml` implicitly.

## Development

```bash
python -m unittest discover -s tests -v
ai-verse-brain doctor .
ai-verse-brain plan-integration .
ai-verse-brain plan-cadence --scope operator --proactivity 2
```

The implementation uses only the Python standard library and targets Python 3.9+. CI tests Python 3.9 and 3.12 on Ubuntu, macOS, and Windows.

Implementation contracts live in [`protocol/`](protocol/). Full Phase 1-3 research remains in [`research/`](research/README.md).

## License

A release license has not yet been finalized for the Brain repository.
