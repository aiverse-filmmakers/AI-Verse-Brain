# AI-Verse Brain Research

This directory preserves the **full pre-implementation research and specification record** that led to the AI-Verse Brain concept.

The purpose of keeping this inside the repository is to make the work durable even if chat context is compressed or lost. These are intentionally detailed artifacts, not short summaries.

The Brain is being designed as a **universal intelligence layer for AI agents**. It should work independently with capable agents, but integrate especially well with AI-Verse OS and AI-Verse Memory.

## Working separation of responsibilities

```text
AI-Verse Brain
= intent, goals, initiative, cognition, prioritization, reflection, verification, learning, controlled self-improvement

AI-Verse OS
= structure, workspaces, routing, capabilities, connections, authority, execution boundaries

AI-Verse Memory
= persistent historical memory, recall, provenance, supersession, derived indexing
```

The Brain must not become a second OS or a second memory store.

## Research and specification files

- [Phase 1 - Full Landscape Research](PHASE-1-LANDSCAPE.md)
  - Detailed repo-by-repo research across LifeOS, Hermes, AIS-OS, Letta, OpenClaw, ACE, Hermes Self-Evolution, GEPA, Voyager, Generative Agents, Reflexion, PersonalOS, Pascal Jarvis, DeerFlow, Honcho, LangMem, Agent Zero, Magentic-One and Anthropic long-running-agent work.
  - Preserves the architectural ideas, useful mechanisms, warnings, boundaries and conclusions extracted from each.

- [Phase 2 - Full Architecture Dissection](PHASE-2-ARCHITECTURE-DISSECTION.md)
  - Detailed analysis of the control architecture beneath those systems.
  - Preserves the Direction Loop, Action Loop, Learning/Evolution Loop, authority hierarchy, initiative model, attention economy, verification model, stall detection, epistemic lifecycle, strategy evolution, self-improvement boundary, Brain planes, OS/Memory integration boundaries and anti-patterns.

- [Phase 3 - AI-Verse Brain Specification](PHASE-3-BRAIN-SPECIFICATION.md)
  - Converts the Phase 1 and Phase 2 findings into the prescriptive Brain architecture.
  - Defines ownership, non-goals, canonical primitives, authority, object envelopes, state machines, evidence, verification, adaptive cognition, 3Ms/4Cs integration, cadence triggers, proactivity levels, action permissions, attention budgets, initiative ranking, learning, strategy evolution, rollback, concurrency, prompt-injection boundaries, OS/Memory write contracts, standalone operation, installer principles and Phase 4 release gates.

- [Phase 3 - QC and Risk Matrix](PHASE-3-QC-RISK-MATRIX.md)
  - Stress-tests the specification against scope creep, duplicate truth, missing cadence, over-proactivity, permission drift, weak verification, strategy-measurement problems, infinite loops, stale state, prompt injection, concurrency, duplicate side effects, Goodhart effects, rollback, cost creep and other implementation failure modes.
  - Maps each major risk to a concrete architecture control and required implementation test.

- [Research Source Map](SOURCE-MAP.md)
  - The repositories and specific public implementation/documentation locations surfaced during the research.
  - Keeps the original sources available so future design decisions can be re-checked against the source architectures rather than relying on memory.

## Current design thesis

The missing layer is not more memory and not more filesystem structure.

It is an **Intent + Cognition + Initiative + Learning layer** that can answer:

- Where is the user trying to go?
- What is the observed current state?
- What gap exists between current and desired states?
- Which initiative would create the most progress?
- What should the agent do next?
- How should the task be pursued and verified?
- Is progress actually happening?
- What worked or failed?
- What should change next time?
- Which strategies, skills, prompts or heuristics deserve controlled improvement?

## Central design principle

> The Brain continuously works to reduce the gap between explicitly desired states and observed current states, while respecting user authority, limited attention, available capabilities, evidence, uncertainty, safety and scope boundaries.

## Non-negotiable authority boundary

The Brain may improve **how** it pursues user-approved goals, but it must not silently redefine **what** the user's goals, values, permissions, privacy boundaries or meaning of success are.

## Current status

Phase 1 and Phase 2 research are preserved in full. Phase 3 now defines the proposed Brain architecture and the QC/risk controls that Phase 4 implementation must satisfy.

No production Brain engine has been implemented yet. Phase 4 should begin from the Phase 3 schemas/controller/state model rather than from UI, prompts, or automation features.
