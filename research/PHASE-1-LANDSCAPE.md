# Phase 1 - Landscape Research

## Purpose

This phase surveyed leading open-source agent systems, personal AI operating systems, cognitive architectures, persistent-memory agents, self-improvement frameworks and long-horizon planning systems to identify the strongest ideas for a future **AI-Verse Brain**.

The target is not another memory database, another filesystem layout, or another runtime-specific prompt pack. The target is a **universal intelligence layer** that can give a capable AI agent persistent direction, initiative, goal pursuit, planning discipline, reflection, verification, learning and controlled self-improvement.

It should be usable with many capable runtimes, but integrate especially deeply with AI-Verse OS and AI-Verse Memory.

The working system family is:

```text
AI-Verse OS
= structure, workspaces, routing, capabilities, connections, source-of-truth rules, authority, execution boundaries

AI-Verse Memory
= persistent historical memory, recall, provenance, supersession, rebuildable indexing

AI-Verse Brain
= intent, goals, initiative, cognition, prioritization, planning, reflection, verification, learning, controlled self-improvement
```

The research question was:

> What would the best persistent intelligence layer for an AI agent look like if we combined the strongest ideas in personal AI operating systems, autonomous agents, cognitive architectures, goal systems, reflection loops and self-improving agent research, while keeping AI-Verse's architectural discipline?

---

# Systems researched

## 1. LifeOS

Repository:
https://github.com/danielmiessler/LifeOS

Related Algorithm repository:
https://github.com/danielmiessler/TheAlgorithm

### Why it matters

LifeOS is one of the clearest examples of a personal AI harness with an explicit long-term directional spine. It is not just a set of tools. It tries to give the agent a persistent understanding of what the user values, where they are, where they want to go, and what progress means.

### Strong ideas

- **Current State -> Ideal State** as a persistent directional model.
- A TELOS-style representation of identity, values, principles, goals and desired future state.
- **Ideal State Artifacts** that turn a vague objective into an inspectable specification.
- Explicit verification criteria rather than assuming that producing something means the task is complete.
- A persistent goal-oriented operating harness rather than a purely reactive assistant.
- A reasoning/process layer called The Algorithm.
- Newer versions move away from excessive fixed ceremony and toward adaptive reasoning depth.
- Verification increasingly behaves like a first-class system concern rather than a final sentence in a prompt.
- Progress is intended to be tied to observable state, not merely model confidence.

### What AI-Verse Brain should learn

The Brain needs a durable answer to:

```text
Where am I now?
Where am I trying to go?
What does success actually look like?
What gap separates the two?
What should change next?
```

The Brain should have explicit long-horizon intent objects rather than relying on recent conversation context to infer goals each time.

### What not to copy blindly

- A rigid fixed seven-step algorithm for every task.
- Multiple independent files that can represent the same canonical goal state and drift.
- A personal-life-specific folder ontology as the universal core.
- A system where derived dashboard views can accidentally become competing sources of truth.

### Important lesson

LifeOS demonstrates the exact weakness identified in AI-Verse OS: architectural discipline alone does not create directional agency. A system can know where data belongs and still not know what it should be trying to improve.

---

## 2. Hermes Agent

Repository:
https://github.com/NousResearch/hermes-agent

### Why it matters

Hermes combines a practical agent runtime with persistent goals, memory, skills, background review, scheduling and procedural improvement.

### Strong ideas

- Goals can survive individual turns.
- A goal can be treated as a **completion contract**, not just a sentence.
- Separate judging/evaluation can decide whether work actually satisfies the contract.
- Failed verification can cause another iteration rather than premature completion.
- Turn budgets and stop conditions bound autonomous work.
- Background reflection can run outside the foreground interaction.
- Memory writes and skill creation can be treated as candidates rather than automatically trusted facts.
- Procedural knowledge can become a reusable skill.
- Successful repeated behavior can be promoted into a capability.
- The agent can search prior sessions and use historical evidence without requiring the user to restate everything.

### Important distinction

Hermes-style persistent goals are usually **execution goals**:

```text
Do this concrete thing.
Continue until the completion condition is satisfied.
```

That is different from a LifeOS-style long-horizon intent:

```text
This is the direction I want my life, company, project or practice to move toward.
```

AI-Verse Brain should have both, but they should be different object types.

### What AI-Verse Brain should learn

- Bounded persistence.
- Explicit completion contracts.
- Separate evaluation from generation.
- Background reflection.
- Candidate memory and skill gates.
- Do not make the foreground task carry every learning responsibility.

### What not to copy blindly

- Treating all goals as session-level execution goals.
- Letting memory, skills and user intent collapse into one general persistence mechanism.

---

## 3. AIS-OS

Repository:
https://github.com/nateherkai/AIS-OS

### Why it matters

AIS-OS is relevant because AI-Verse inherited and neutralized useful conceptual frameworks from it, especially the Three Ms and Four Cs.

### Strong ideas

#### Three Ms

```text
Mindset
Method
Machine
```

A useful interpretation:

- **Mindset**: where can AI create leverage?
- **Method**: what is the actual process, constraint and desired result?
- **Machine**: what is the smallest reliable system that can execute it?

#### Four Cs

```text
Context
Connections
Capabilities
Cadence
```

A useful interpretation:

- **Context**: does the system know enough?
- **Connections**: can it reach the systems and sources it needs?
- **Capabilities**: can it perform the work reliably?
- **Cadence**: can mature work run repeatedly or proactively?

### What AI-Verse Brain should learn

The 3Ms and 4Cs are extremely useful **inside a larger intelligence architecture**.

The Brain can use them after it identifies a gap:

```text
Gap detected
    ↓
3Ms diagnose leverage and design an intervention
    ↓
4Cs check readiness to execute and sustain it
```

### What not to copy blindly

3Ms and 4Cs are not enough to serve as:

- identity
- long-term intent
- goal hierarchy
- current-state model
- initiative portfolio
- reflection system
- evaluator
- self-improvement lifecycle

Their strongest role is **strategy and execution-readiness**, not the entire brain.

---

## 4. Letta / Letta Code

Repository:
https://github.com/letta-ai/letta-code

### Why it matters

Letta treats the agent as something that persists over time rather than as a sequence of independent chats.

### Strong ideas

- Persistent agent identity.
- Mutable memory separate from immutable historical experience.
- Procedural skills as a separate layer.
- Context and agent state can evolve over time.
- Git-backed or inspectable evolution is preferable to opaque hidden state.
- Deterministic constraints should live in the harness, not in fragile learned memory.
- A persistent agent can become better through accumulated experience without necessarily changing model weights.

### What AI-Verse Brain should learn

The Brain may need a **persistent agent strategy identity**, but this must remain subordinate to user authority.

Useful separation:

```text
USER INTENT
what the user wants

AGENT STRATEGY IDENTITY
how this Brain tends to operate effectively

EXPERIENCE
what happened

PROCEDURE
what method tends to work
```

### What not to copy blindly

The Brain must never treat its own evolving identity as permission to redefine the user's goals or values.

---

## 5. OpenClaw

Repository:
https://github.com/openclaw/openclaw

### Why it matters

OpenClaw is especially relevant to proactive agents because it separates identity, user modeling, memory and scheduler behavior.

### Strong ideas

- Separation of constructs such as `SOUL.md`, `IDENTITY.md`, `USER.md`, memory and operating instructions.
- Proactive behavior should not depend on the model rediscovering stale work from arbitrary context.
- **Heartbeat** and **cron** are different concepts.
- Recurring deterministic work belongs in explicit scheduling machinery.
- Ambient awareness can be periodic and bounded.
- The LLM should not own deterministic scheduler bookkeeping.
- Recall loops and repeated stale-task resurrection need explicit prevention.

### What AI-Verse Brain should learn

Proactivity needs architecture, not just a prompt saying "be proactive."

Useful distinction:

```text
AUTOMATION
Do this known recurring thing at a known time/event.

AMBIENT AWARENESS
Periodically inspect whether something important has changed.

INITIATIVE DISCOVERY
Notice a valuable new opportunity or problem that was not already scheduled.
```

These should not be the same mechanism.

### What not to copy blindly

- Giving the model control over deterministic timing/state-machine logic.
- Letting heartbeat become an unbounded random task generator.

---

## 6. ACE - Agentic Context Engineering

Repository:
https://github.com/ace-agent/ace

### Why it matters

ACE is one of the most relevant findings for a self-improving Brain.

It treats an agent's operational knowledge as an evolving **playbook**, not as a monolithic prompt that gets repeatedly rewritten.

### Core pattern

```text
Generator
   ↓
trajectory / attempt
   ↓
Reflector
   ↓
what helped / hurt / was missing
   ↓
Curator
   ↓
small structured deltas to the playbook
```

### Strong ideas

- Grow-and-refine rather than rewrite-everything.
- Stable rule identities.
- Incremental ADD / UPDATE / RETIRE operations.
- Evidence about whether a rule was helpful or harmful.
- Avoid context collapse caused by compressing an evolving instruction set into an ever-smaller prompt.
- Avoid brevity bias where optimization gradually removes useful nuance.
- Preserve useful operational knowledge while still allowing evolution.

### What AI-Verse Brain should learn

The Brain's self-improving strategy layer should probably consist of **atomic strategies/heuristics with evidence**, not one giant mutable system prompt.

Example conceptual rule:

```yaml
strategy:
  id: verify-source-before-claim
  status: active
  helpful: 18
  harmful: 1
  confidence: 0.94
  applies_when:
    - factual research
  instruction:
    - verify material claims against authoritative evidence
```

### What not to copy blindly

The playbook cannot become another canonical location for user truth. It should store **operational strategy**, not user identity or goals.

---

## 7. Hermes Agent Self-Evolution

Repository:
https://github.com/NousResearch/hermes-agent-self-evolution

### Why it matters

This project moves beyond generic reflection into **controlled optimization of agent artifacts**.

### Strong ideas

A strong self-improvement pipeline looks more like:

```text
current artifact
    ↓
evaluation set
    ↓
generate candidate variants
    ↓
execute candidates
    ↓
measure
    ↓
run constraints / regression tests
    ↓
select winner
    ↓
review / PR
    ↓
promote
```

rather than:

```text
AI thinks of a better prompt
    ↓
overwrite production prompt
```

### What AI-Verse Brain should learn

- Improvements should be candidates.
- Candidate improvements should be tested.
- Regression protection matters.
- Semantic preservation matters.
- Holdout examples are useful.
- High-impact changes should support human review.
- Promotion and rollback need to be explicit operations.

### What not to copy blindly

Do not allow optimization machinery to modify privileged user-intent objects.

---

## 8. GEPA

Repository:
https://github.com/gepa-ai/gepa

### Why it matters

GEPA is useful because it improves agent behavior using textual execution feedback, not just scalar reward.

### Strong ideas

- Read the full trajectory and diagnostics.
- Ask why a behavior succeeded or failed.
- Generate candidate improvements from that diagnosis.
- Optimize textual artifacts such as prompts, policies or instructions.
- Multi-objective/Pareto-aware optimization can prevent one metric from dominating everything.

### What AI-Verse Brain should learn

Self-improvement can optimize things such as:

- planning heuristics
- tool-routing instructions
- verification rubrics
- initiative-ranking strategies
- prompt templates
- retrieval strategies
- skill procedures

It should not optimize:

- user values
- user goals
- privacy boundaries
- permissions
- ethical constraints
- meaning of success

without user authority.

---

## 9. Voyager

Repository:
https://github.com/MineDojo/Voyager

### Why it matters

Voyager introduced an especially relevant concept: **automatic curriculum**.

The agent does not merely ask "what task did the user give me?" It asks what frontier or capability it should pursue next in order to make progress.

### Strong ideas

- Automatic curriculum chooses what to learn or attempt next.
- Skill library compounds successful procedures.
- Environment feedback provides real verification.
- Skills can be composed into more complex behavior.
- The agent expands competence instead of repeatedly solving from scratch.

### What AI-Verse Brain should learn

This maps directly to **initiative discovery**.

Given:

```text
user goals
current state
constraints
available capabilities
known gaps
```

the Brain should be able to ask:

> What is the highest-value missing capability, intervention, experiment or next step?

### What not to copy blindly

Open-ended exploration must remain tied to user-approved direction. The Brain should not pursue novelty for its own sake.

---

## 10. Generative Agents

Repository:
https://github.com/joonspk-research/generative_agents

Related research implementation:
https://github.com/joonspk-research/genagents

### Why it matters

Generative Agents is foundational for the distinction between raw experience and higher-order reflection.

### Strong ideas

- Observations become memories.
- Accumulated memories can trigger reflection.
- Reflection creates higher-order abstractions.
- Reflections influence later planning and behavior.
- Importance, recency and relevance can affect retrieval.

### What AI-Verse Brain should learn

The Brain should not store only raw events.

Useful ladder:

```text
observation
    ↓
experience
    ↓
pattern
    ↓
reflection
    ↓
validated learning
    ↓
strategy or principle
```

### What not to copy blindly

A reflection is still an inference. It should not become an authoritative user fact merely because the model generated it.

---

## 11. Reflexion

Repository:
https://github.com/noahshinn/reflexion

### Why it matters

Reflexion demonstrates how an agent can improve from evaluation feedback without retraining model weights.

### Core pattern

```text
Actor
  ↓
Evaluator
  ↓
Self-Reflection
  ↓
next attempt informed by lesson
```

### Strong ideas

- Failure can produce a compact verbal lesson.
- Lessons can affect future attempts.
- Learning can happen at the context/policy level rather than weight level.

### What AI-Verse Brain should learn

The Brain should have a reflection primitive, but reflection should feed a candidate-learning pipeline rather than automatically becoming truth.

---

## 12. PersonalOS by Nicolas Diez

Repository:
https://github.com/nicolas-diez/personal-os

### Why it matters

PersonalOS is smaller than some systems but particularly relevant because it connects high-level goals to everyday prioritization.

### Strong ideas

- `GOALS.md` influences actual backlog priority.
- Limits on P0/P1 prevent everything from becoming urgent.
- Weekly energy/capacity affects planning aggressiveness.
- Daily orientation and weekly planning convert long-term direction into current action.
- Advisor behavior can be self-evaluated against criteria.
- Per-skill learnings can accumulate.

### What AI-Verse Brain should learn

Goal pursuit needs **capacity-aware portfolio management**.

A Brain that finds 40 useful initiatives should not activate all 40.

Potential concepts:

- active initiative cap
- work-in-progress limit
- priority tiers
- attention budget
- energy/capacity factor
- deferred queue
- review horizon

### What not to copy blindly

Fixed domain copilots such as work/personal should not be hardcoded into the universal core. AI-Verse workspaces already provide a more general isolation primitive.

---

## 13. Pascal Jarvis

Repository:
https://github.com/phronesis-io/pascal-jarvis

The repository is archived, so it should be treated as architectural research rather than a dependency.

### Why it matters

Pascal Jarvis contains useful patterns for **closed-loop proactive intents**.

### Strong ideas

- A proactive intent is a state machine, not just a reminder.
- Sending a notification is not equivalent to completing the intent.
- An intent can require acknowledgement, evidence, timeout, bounded retries or terminal closure.
- Deterministic bookkeeping should not be delegated to the LLM.
- Attention is scarce.
- Lower-value interventions can be batched rather than interrupting constantly.
- Deduplication matters.
- Completion receipts create an explicit evidence trail.
- Finite goals and recurring practices should be different objects.

### What AI-Verse Brain should learn

Initiatives need lifecycle state.

Possible states:

```text
proposed
accepted
active
waiting
blocked
stalled
completed
abandoned
superseded
```

A proactive system should also understand interruption cost.

### What not to copy blindly

Do not depend on the archived implementation. Take the architectural ideas only.

---

## 14. DeerFlow 2.0

Repository:
https://github.com/bytedance/deer-flow

### Why it matters

DeerFlow is relevant for long-horizon planning, subagent orchestration, sandboxed execution and controlled persistence.

### Strong ideas

- Break long tasks into coordinated subproblems.
- Persistent memory is useful, but candidate information can be classified before writeback.
- Scope, durability and authority can be evaluated before persistence.
- Deterministic write gates reduce accidental contamination.
- Long-running execution benefits from isolated environments and explicit task state.

### What AI-Verse Brain should learn

Before promoting a learning, ask questions like:

```text
What scope does this apply to?
How durable is it?
How authoritative is the evidence?
Is this explicit user truth, derived inference or agent strategy?
Where should it be written?
```

This aligns strongly with AI-Verse OS's existing source-of-truth architecture and AI-Verse Memory's provenance model.

---

## 15. Honcho

Repository:
https://github.com/plastic-labs/honcho

### Why it matters

Honcho is relevant for building evolving representations of people and agents from accumulated interactions.

### Strong ideas

- A derived representation can be different from explicit factual conclusions.
- The system can model preferences, tendencies and interaction patterns over time.
- Expensive inference can run asynchronously.
- Perspective matters: what one agent believes about another is not necessarily objective truth.

### Critical warning

Derived user models are extremely useful but dangerous when scope or provenance is weak.

AI-Verse Brain should never silently transform:

```text
agent inference:
"The user probably values autonomy"
```

into:

```text
canonical user goal:
"Maximize autonomy"
```

Instead:

```yaml
hypothesis:
  statement: "Autonomy appears to be a recurring preference"
  confidence: 0.68
  evidence:
    - ...
  authority: derived
  requires_confirmation_for_goal_change: true
```

### What AI-Verse Brain should learn

Explicit user intent and derived user modeling must be separate authority classes.

---

## 16. LangMem

Repository:
https://github.com/langchain-ai/langmem

### Why it matters

LangMem is useful because it distinguishes extracting memories from optimizing behavior.

### Strong ideas

- Long-term memories can be extracted in the background.
- Prompt/behavior optimization can be a separate operation.
- Durable knowledge and behavioral adaptation do not need to be the same mechanism.

### What AI-Verse Brain should learn

The Brain should not treat all learning as memory.

There are different products:

```text
historical memory
user model
world model
strategy update
skill update
prompt update
initiative update
```

Each deserves its own authority and writeback rules.

---

## 17. Agent Zero

Repository:
https://github.com/agent0ai/agent-zero

### Why it matters

Agent Zero contributes practical patterns around projects, profiles, skills, memory, scheduled operation and extensibility.

### Strong ideas

- Project-scoped isolation.
- Profiles and reusable agent behavior.
- Scheduled operations.
- Plugins and skills as modular extensions.
- Avoiding hard dependency on one monolithic runtime architecture.

### What AI-Verse Brain should learn

The Brain should remain modular and portable.

It should not require one particular model provider, agent runtime, UI, vector database, or cloud service.

---

# Additional architecture references identified during research

## Magentic-One / AutoGen

Repository area:
https://github.com/microsoft/autogen

### Important idea

Magentic-One uses a distinction similar to:

```text
Task Ledger
Progress Ledger
```

The important lesson is that **unfinished is not the same as progressing**.

The Brain should track states such as:

```text
progressing
waiting
blocked
stalled
wrong strategy
invalidated
completed
```

Repeated failure to make progress should trigger replanning rather than another identical attempt.

---

## Anthropic long-running agent harness research

Repository:
https://github.com/anthropics/cwc-long-running-agents

### Important ideas

- Start criteria in a failing/unverified state.
- A fresh-context evaluator can assess evidence independently.
- The evaluator should not be allowed to modify the artifact being evaluated.
- Work continues until evidence changes status.
- Agent-maintained handoff state helps long-running work survive context boundaries.

### What AI-Verse Brain should learn

Verification should not be a self-congratulatory final step by the same context that produced the result.

For high-impact work, evaluation should be independent enough to catch optimism and context bias.

---

# The main discovery from Phase 1

The word **brain** hides multiple distinct capabilities.

The research suggests at least five separate kinds of intelligence:

```text
1. INTENT
   What ultimately matters?
   What does better mean?
   Where are we trying to go?

2. COGNITION
   How should I think about this?
   How much reasoning is warranted?
   What method should I use?

3. INITIATIVE
   What should I notice, propose or work on
   without waiting for the user to explicitly ask?

4. LEARNING
   What worked?
   What failed?
   What should change next time?

5. EVOLUTION
   Which strategies, skills, prompts,
   heuristics or procedures should improve?
```

AI-Verse OS and AI-Verse Memory already provide infrastructure below these layers.

```text
AI-Verse OS
    ↓
scope
workspaces
connections
capabilities
knowledge
source of truth
execution boundaries

AI-Verse Memory
    ↓
history
recall
provenance
supersession
```

The Brain should answer the questions above those layers.

---

# Emerging conceptual model

```text
                       AI-VERSE BRAIN

            ┌────────── INTENT ──────────┐
            │                            │
        identity                    ideal state
        values                      outcomes
        principles                  goals
            │                            │
            └───────────┬────────────────┘
                        ↓
                 GAP / OPPORTUNITY
                        ↓
                    INITIATIVES
                        ↓
                    PRIORITIES
                        ↓
                     COGNITION
                        ↓
                      PLAN
                        ↓
                      ACTION
                        ↓
                    EVIDENCE
                        ↓
                    REFLECTION
                        ↓
                     LEARNING
                        ↓
                    EVOLUTION
                        │
                        └──────────────↺
```

---

# Strongest ideas to combine

## LifeOS

Provides the directional spine:

```text
Current State
    ↓
Ideal State
    ↓
Gap
    ↓
Desired outcomes
    ↓
Verification
```

## Voyager

Adds initiative discovery:

```text
What should be learned, built, investigated or improved next
in order to create the greatest goal-aligned progress?
```

## PersonalOS

Adds portfolio discipline:

```text
goals
  ↓
backlog
  ↓
priorities
  ↓
capacity-aware selection
  ↓
week
  ↓
today
```

## OpenClaw

Adds bounded ambient awareness and a clean distinction between:

- deterministic recurring work
- periodic awareness
- newly discovered initiative

## Pascal Jarvis

Adds closed-loop proactive intent lifecycle, anti-nagging and attention budgets.

## Generative Agents + Reflexion

Add reflection and higher-order learning.

## ACE

Adds structured, incremental playbook evolution.

## Hermes Self-Evolution + GEPA

Add measurable optimization, evals, regression checks, candidate selection, promotion and rollback.

## Letta

Adds persistent agent continuity and a clean distinction between identity, memory, experience and procedure.

## Honcho

Adds derived user representation while highlighting the need for strict provenance and perspective boundaries.

## AIS-OS / 3Ms + 4Cs

Add leverage diagnosis and execution readiness.

---

# Non-negotiable self-improvement boundary

A central rule emerged very strongly:

> **The Brain may autonomously improve HOW it pursues user-approved goals. It may not autonomously change WHAT the user's goals, values, boundaries or permissions are.**

### Candidate self-improvement targets

```text
strategies
heuristics
skills
plans
routing policies
prompts
evaluation methods
retrieval strategies
procedures
initiative-ranking heuristics
```

### Privileged objects that must not silently self-modify

```text
user values
user goals
user identity
permissions
privacy boundaries
risk tolerance
approval policy
ethical constraints
meaning of success
```

---

# Another major discovery: not every thought deserves persistence

The stronger systems converge on a staged epistemic model.

Bad model:

```text
agent thought
    ↓
permanent memory
```

Better model:

```text
observation
    ↓
candidate insight
    ↓
reflection
    ↓
validated learning
    ↓
durable strategy / principle
```

A possible maturity ladder for Brain beliefs:

```text
hypothesis
    ↓
observed pattern
    ↓
corroborated pattern
    ↓
validated learning
    ↓
operating principle
```

Every stage should preserve provenance and confidence.

---

# Authority hierarchy emerging from research

Not all information should have equal authority.

```text
EXPLICIT USER INTENT
"I want X."
"I don't want Y."
"Never do Z."
"This is important."

        ↓ highest authority

CANONICAL OBSERVED STATE
verified facts about current reality

        ↓

DERIVED USER MODEL
"The user appears to prefer..."
"Evidence suggests..."

        ↓

AGENT STRATEGY
"This method tends to work for this user/context."

        ↓

TEMPORARY HYPOTHESIS
"Maybe this pattern matters."
```

Derived representations must never silently overwrite explicit intent.

---

# Phase 1 working relationship between repositories

```text
                 AI-VERSE BRAIN
          Intent • Goals • Initiative
       Planning • Reflection • Learning
        Prioritization • Improvement
                    │
          ┌─────────┴─────────┐
          │                   │
     AI-VERSE OS       AI-VERSE MEMORY
     structure          remembering
     execution          history
     isolation          recall
     connections        provenance
     capabilities       supersession
```

A portable Brain should also be able to run in a reduced mode:

```text
generic capable agent
        +
AI-Verse Brain
```

while obtaining richer behavior when AI-Verse OS and Memory are available.

---

# Phase 1 central thesis

> **The Brain continuously works to reduce the gap between explicitly desired states and observed current states, while respecting user authority, limited attention, available capabilities, evidence, uncertainty, safety and scope boundaries.**

This is substantially more precise than simply telling an agent to "be proactive."

It provides a test for initiative:

```text
Does this proposed action reduce an important, evidence-backed gap
between an approved desired state and observed current state?
```

If not, the Brain should have a high bar for interrupting the user or consuming resources.

---

# Phase 1 shortlist: strongest architectural DNA

The systems most worth deeper line-by-line architectural study were:

1. LifeOS - persistent intent, Current State -> Ideal State, verification.
2. Hermes Agent - persistent execution goals, background learning, skill promotion.
3. ACE - safe incremental playbook evolution.
4. Hermes Self-Evolution - evidence-gated artifact improvement.
5. GEPA - trace-based textual optimization.
6. Voyager - automatic curriculum and capability compounding.
7. OpenClaw - bounded proactive cognition and scheduler separation.
8. Generative Agents - memory -> reflection -> planning.
9. Reflexion - evaluator-driven verbal learning.
10. PersonalOS - goals -> priorities -> capacity-aware daily action.
11. Pascal Jarvis - proactive-intent lifecycle and attention economics.
12. Letta - persistent agent continuity and evolving strategy identity.
13. Honcho - derived user representations and provenance boundaries.
14. Magentic-One - progress ledger and stall detection.
15. Anthropic long-running-agent harness - independent verification and handoff.
16. DeerFlow - long-horizon execution and persistence gating.
17. AIS-OS - Three Ms and Four Cs as leverage/readiness methods.

Phase 2 then dissected the architecture beneath these feature lists and started defining the actual intelligence model.
