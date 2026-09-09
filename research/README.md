# AI-Verse Brain Research

This directory preserves the **full pre-implementation research record** that led to the AI-Verse Brain concept.

The purpose of keeping this inside the repository is to make the research durable even if chat context is compressed or lost. These are intentionally detailed research artifacts, not short summaries.

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

## Research files

- [Phase 1 - Full Landscape Research](PHASE-1-LANDSCAPE.md)
  - Detailed repo-by-repo research across LifeOS, Hermes, AIS-OS, Letta, OpenClaw, ACE, Hermes Self-Evolution, GEPA, Voyager, Generative Agents, Reflexion, PersonalOS, Pascal Jarvis, DeerFlow, Honcho, LangMem, Agent Zero, Magentic-One and Anthropic long-running-agent work.
  - Preserves the architectural ideas, useful mechanisms, warnings, boundaries and conclusions extracted from each.

- [Phase 2 - Full Architecture Dissection](PHASE-2-ARCHITECTURE-DISSECTION.md)
  - Detailed analysis of the control architecture beneath those systems.
  - Preserves the Direction Loop, Action Loop, Learning/Evolution Loop, authority hierarchy, initiative model, attention economy, verification model, stall detection, epistemic lifecycle, strategy evolution, self-improvement boundary, Brain planes, OS/Memory integration boundaries and anti-patterns.

- [Research Source Map](SOURCE-MAP.md)
  - The repositories and specific public implementation/documentation locations surfaced during the research.
  - Keeps the original sources available so future design decisions can be re-checked against the source architectures rather than relying on memory.

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

These files are the detailed research record, not the final AI-Verse Brain specification. The next phase should convert the findings into canonical primitives, authority rules, state machines, schemas, adaptive cognition loops, integration contracts and the repository architecture.
