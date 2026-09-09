# Research Source Map

This file preserves the repositories and specific public materials consulted or identified during Phase 1 and Phase 2 so later design work can return to the original systems rather than relying only on condensed recollection.

This is a research map, not a dependency list and not an endorsement of every implementation choice in these projects.

---

## LifeOS

Main repository:
https://github.com/danielmiessler/LifeOS

The Algorithm:
https://github.com/danielmiessler/TheAlgorithm

Releases:
https://github.com/danielmiessler/LifeOS/releases

Relevant research topics:

- TELOS / persistent personal intent
- Current State -> Ideal State
- Ideal State Artifacts
- adaptive Algorithm depth
- verification and completion criteria
- persistent goal-oriented personal harness
- source-of-truth drift risks in evolving personal OS architectures

Examples of issue/discussion material examined or surfaced during research:

https://github.com/danielmiessler/LifeOS/issues/1489
https://github.com/danielmiessler/LifeOS/discussions/1847

---

## Hermes Agent

Repository:
https://github.com/NousResearch/hermes-agent

Goals documentation / implementation areas:
https://github.com/NousResearch/hermes-agent/blob/main/hermes_cli/goals.py
https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/goals.md

Memory documentation:
https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/memory.md

Relevant research topics:

- persistent goals
- completion contracts
- external/independent judging
- turn budgets
- stop conditions
- background review
- skill learning
- memory gating
- session search
- scheduled autonomy

---

## Hermes Agent Self-Evolution

Repository:
https://github.com/NousResearch/hermes-agent-self-evolution

Relevant research topics:

- execution traces
- candidate prompt/skill evolution
- DSPy / GEPA-assisted optimization
- regression checks
- semantic-preservation gates
- test/eval-driven promotion
- PR-based review rather than direct uncontrolled production mutation

---

## GEPA

Repository:
https://github.com/gepa-ai/gepa

README:
https://github.com/gepa-ai/gepa/blob/main/README.md

Relevant research topics:

- trace-aware textual optimization
- diagnostic reflection
- candidate evolution
- Pareto-aware multi-objective optimization
- optimizing prompts/configuration/strategies rather than model weights

---

## ACE - Agentic Context Engineering

Repository:
https://github.com/ace-agent/ace

Relevant research topics:

- Generator -> Reflector -> Curator
- evolving playbook
- incremental delta updates
- stable rule IDs
- helpful/harmful evidence counters
- grow-and-refine
- context collapse
- brevity bias
- avoiding monolithic prompt rewrites

---

## Voyager

Repository:
https://github.com/MineDojo/Voyager

Relevant research topics:

- automatic curriculum
- self-directed frontier selection
- skill library
- compositional procedural learning
- environment feedback
- self-verification
- competence compounding

---

## Letta Code

Repository:
https://github.com/letta-ai/letta-code

Relevant research topics:

- persistent agent identity
- evolving memory
- immutable experience vs mutable state
- skills/procedural knowledge
- long-horizon continuity
- deterministic constraints in harness rather than fragile memory
- inspectable/versioned evolution

---

## OpenClaw

Repository:
https://github.com/openclaw/openclaw

Start documentation:
https://github.com/openclaw/openclaw/blob/main/docs/start/openclaw.md

Heartbeat documentation:
https://github.com/openclaw/openclaw/blob/main/docs/gateway/heartbeat.md

Relevant research topics:

- SOUL / IDENTITY / USER separation
- heartbeat
- cron
- ambient awareness vs scheduled work
- scheduler-owned deterministic state
- recall-loop prevention
- proactive-agent boundaries

---

## Generative Agents

Research repository:
https://github.com/joonspk-research/generative_agents

Related implementation repository:
https://github.com/joonspk-research/genagents

Relevant research topics:

- observation memory
- importance / recency / relevance
- reflection from accumulated experience
- higher-order abstraction
- reflection influencing planning and future behavior

---

## Reflexion

Repository:
https://github.com/noahshinn/reflexion

Relevant research topics:

- Actor -> Evaluator -> Self-Reflection
- verbal reinforcement
- learning from failures without model-weight retraining
- compact lessons applied to future attempts

---

## PersonalOS

Repository:
https://github.com/nicolas-diez/personal-os

Relevant research topics:

- GOALS.md as an active planning input
- backlog prioritization
- P0/P1 limits
- weekly energy/capacity throttling
- daily orientation
- weekly planning
- advisor self-evaluation
- per-skill learning

---

## Pascal Jarvis

Repository:
https://github.com/phronesis-io/pascal-jarvis

Task-system design:
https://github.com/phronesis-io/pascal-jarvis/blob/main/docs/design_task_system.md

Status note:
The repository is archived and should be treated as architectural research rather than a dependency.

Relevant research topics:

- proactive intent state machines
- intent closure based on acknowledgement/evidence/TTL rather than sending a notification
- bounded retries
- deterministic lifecycle bookkeeping
- attention budgets
- batching low-value interventions
- completion receipts
- finite tasks vs ongoing practices

---

## DeerFlow

Repository:
https://github.com/bytedance/deer-flow

Relevant research topics:

- long-horizon planning
- subagent decomposition
- persistent memory
- sandboxed execution
- candidate-memory classification
- scope / durability / authority before writeback
- deterministic persistence gates

---

## Honcho

Repository:
https://github.com/plastic-labs/honcho

Peer-card documentation surfaced during research:
https://github.com/plastic-labs/honcho/blob/main/docs/v3/documentation/features/advanced/peer-card.mdx

Example scope-contamination issue surfaced during research:
https://github.com/plastic-labs/honcho/issues/912

Relevant research topics:

- derived representations of users/agents
- peer models
- conclusions vs deductions vs representation
- asynchronous inference
- perspective-aware knowledge
- provenance and scope contamination risk

---

## LangMem

Repository:
https://github.com/langchain-ai/langmem

Relevant research topics:

- background memory extraction
- behavioral/prompt optimization separated from memory extraction
- long-term memory utilities
- learning as multiple products rather than one generic memory store

---

## Agent Zero

Repository:
https://github.com/agent0ai/agent-zero

Relevant research topics:

- project-scoped isolation
- memory
- profiles
- scheduled operations
- plugins
- skills
- modular agent architecture

---

## Magentic-One / Microsoft AutoGen

Repository:
https://github.com/microsoft/autogen

Magentic-One implementation area surfaced during research:
https://github.com/microsoft/autogen/blob/main/python/packages/autogen-ext/src/autogen_ext/teams/magentic_one.py

Relevant research topics:

- Task Ledger
- Progress Ledger
- completion assessment
- progress assessment
- stall detection
- replanning after repeated non-progress
- multi-agent coordination

---

## Anthropic long-running agent harness

Repository:
https://github.com/anthropics/cwc-long-running-agents

Relevant research topics:

- default-failing/unverified criteria
- fresh-context evaluator
- evaluator cannot modify the work under evaluation
- continuation until evidence changes criterion state
- handoff state for long-running work across context boundaries

---

## AIS-OS

Repository:
https://github.com/nateherkai/AIS-OS

Relevant research topics:

- Three Ms
- Four Cs
- AI leverage diagnosis
- capability/system-building method
- operator-brain framing

For AI-Verse Brain, the research conclusion is that 3Ms and 4Cs are best used inside a larger directional architecture rather than asked to serve as the full persistent-intelligence model.

---

## AI-Verse OS

Repository:
https://github.com/aiverse-filmmakers/AI-Verse-OS

Relevant architecture already present before Brain work:

- universal workspaces
- operator/workspace isolation
- source-of-truth hierarchy
- context vs memory vs knowledge vs decisions
- domain-neutral architecture
- progressive disclosure
- local inspectable truth
- derived runtime/indexes
- Four Cs
- Three Ms
- capability registry
- connections / agents / automations / apps

Brain research must preserve these boundaries rather than duplicating them.

---

## AI-Verse Memory

Repository:
https://github.com/aiverse-filmmakers/AI-Verse-Memory

Relevant architecture already present before Brain work:

- Markdown canonical memory
- rebuildable SQLite index
- scoped operator/workspace recall
- provenance
- confidence
- importance
- temporal history
- supersession
- deduplication
- native AI-Verse OS integration
- current context outranks historical memory
- local-first operation

Brain research must use Memory as historical evidence rather than creating a second competing memory system.

---

# Cross-system concepts to preserve for the specification phase

The most important cross-system mechanisms identified are:

```text
Current State -> Ideal State
persistent explicit intent
privileged user authority
separate derived user model
gap detection
initiative discovery
automatic curriculum
initiative portfolios
capacity-aware priority
attention cost
bounded proactive behavior
finite goals vs ongoing practices
completion contracts
progress ledgers
stall detection
replanning
explicit verification
independent evaluation when warranted
reflection
candidate learning
epistemic maturity
atomic strategy playbook
ADD / UPDATE / RETIRE strategy deltas
evaluation sets
regression tests
promotion
rollback
persistent agent continuity
deterministic lifecycle bookkeeping
```

These are the raw architectural ingredients that Phase 3 should convert into a unified AI-Verse Brain specification.
