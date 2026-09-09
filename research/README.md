# AI-Verse Brain Research

This directory preserves the research that led to the AI-Verse Brain concept before implementation begins.

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

## Research phases

- [Phase 1 - Landscape Research](PHASE-1-LANDSCAPE.md)
  - Survey of leading repos and architectures relevant to persistent intent, goal pursuit, proactive agents, self-improvement, reflection, learning, identity and long-horizon agency.
  - Extracts the strongest architectural ideas from each system.

- [Phase 2 - Architecture Dissection](PHASE-2-ARCHITECTURE-DISSECTION.md)
  - Goes below feature lists into control loops, state models, evaluators, planning patterns, initiative systems, verification, user modeling, attention management and controlled evolution.
  - Produces the first coherent conceptual architecture for AI-Verse Brain.

## Current research thesis

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

## Central design principle emerging from research

> The Brain continuously works to reduce the gap between explicitly desired states and observed current states, while respecting user authority, limited attention, available capabilities, evidence, uncertainty, safety and scope boundaries.

## Non-negotiable authority boundary

The Brain may improve **how** it pursues user-approved goals, but it must not silently redefine **what** the user's goals, values, permissions, privacy boundaries or meaning of success are.

## Status

These files are research artifacts, not the final AI-Verse Brain specification. The next phase should convert the findings into canonical primitives, authority rules, state machines, schemas, adaptive cognition loops, integration contracts and the repository architecture.
