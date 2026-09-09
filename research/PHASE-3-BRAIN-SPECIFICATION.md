# Phase 3 - AI-Verse Brain Specification

## Status

**Design specification, pre-implementation.**

This document converts the full Phase 1 landscape research and Phase 2 architecture dissection into a concrete specification for AI-Verse Brain.

It is intentionally more prescriptive than the earlier research. Phase 1 asked what the strongest systems do. Phase 2 asked how their mechanisms fit together. Phase 3 decides what AI-Verse Brain should actually be, what it should own, what it must never own, how it wakes up, how it becomes proactive without becoming intrusive, how it learns without overfitting, how it verifies outcomes, and how it integrates with AI-Verse OS and AI-Verse Memory without creating duplicate sources of truth.

The design inputs for this specification are preserved in:

- [Phase 1 - Landscape Research](PHASE-1-LANDSCAPE.md)
- [Phase 2 - Architecture Dissection](PHASE-2-ARCHITECTURE-DISSECTION.md)
- [Research Source Map](SOURCE-MAP.md)

The current AI-Verse integration contracts used while writing this specification were also re-checked against:

- `AI-Verse-OS/AI-VERSE.yaml`
- `AI-Verse-OS/system/architecture/source-of-truth.md`
- `AI-Verse-OS/system/architecture/knowledge-lifecycle.md`
- `AI-Verse-Memory/README.md`
- `AI-Verse-Memory/protocol/MEMORY-PROTOCOL.md`

The purpose is to avoid designing a Brain that looks impressive in isolation but breaks the existing OS/Memory architecture when installed.

---

# 1. Product definition

AI-Verse Brain is a **universal intelligence layer for capable AI agents**.

Its purpose is to give an agent persistent direction and disciplined self-improvement.

It should help an agent continuously answer:

```text
What does the user explicitly want?
What is true now?
What important gap exists?
What initiative could reduce that gap?
What deserves attention now?
What is the smallest useful objective?
What evidence would prove success?
Are we actually progressing?
What should happen next?
What did we learn?
What should improve next time?
```

The Brain is not a model provider, chat UI, memory database, filesystem OS, task scheduler, secret manager, connection manager, or automation platform.

It is the layer that decides **why, where, what next, how deeply to reason, how to verify, and how to improve**.

---

# 2. Governing principle

The central rule is:

> **The Brain continuously works to reduce the gap between explicitly desired states and observed current states, while respecting user authority, scope isolation, limited attention, available capabilities, evidence, uncertainty, safety, permissions, and resource limits.**

A clever idea is not automatically an initiative.

A proposed action should normally pass this test:

```text
Does this action plausibly reduce an important,
evidence-backed gap between an approved desired state
and the current observed state?
```

If not, the Brain should have a high bar for consuming compute, interrupting the user, or changing persistent state.

---

# 3. Non-goals and anti-scope-creep boundary

The largest architectural risk is turning the Brain into a second operating system.

The boundary must therefore be explicit.

## AI-Verse Brain owns

```text
persistent desired direction
goals and ongoing practices
gap analysis
opportunity hypotheses
initiative discovery and portfolio state
bounded objectives and completion contracts
progress / stall reasoning
verification policy and evaluation records
derived user / agent / world hypotheses
strategy playbook
candidate learning
strategy evaluation / promotion / rollback policy
Brain-specific cadence policy
Brain-specific attention / proactivity policy
```

## AI-Verse Brain does not own

```text
workspace identity
filesystem routing
operator profile as a whole
current OS context as a whole
historical memory engine
reusable domain knowledge base
connection credentials
secret storage
skill implementation registry
agent runtime implementation
automation scheduler implementation
external side-effect execution
calendar/email/GitHub/etc. APIs
platform safety policy
```

## In AI-Verse native mode

```text
Brain = intent + initiative + cognition + evaluation + learning policy
OS    = structure + scope + authority + connections + capabilities + cadence execution
Memory = historical recall + provenance + supersession + memory indexing
Runtime = model/tool execution
```

The Brain may request or propose work to those layers. It must not silently recreate them.

---

# 4. Core architectural laws

These are normative design laws, not suggestions.

## Law 1: One canonical owner per fact or state

Every durable object must have one canonical owner.

Dashboards, summaries, indexes, daily views, context projections, and reports are derived.

They must never become independently editable competing truth.

## Law 2: Current canonical state outranks historical memory

When current state and old memory disagree, current scoped truth wins unless there is evidence that the current state itself is stale or wrong.

## Law 3: Explicit user intent outranks derived interpretation

The Brain can infer preferences and likely priorities, but derived models may not silently become user goals, values, permissions, or boundaries.

## Law 4: Proactivity is not authority

The right to notice or suggest something is not the right to execute it.

Initiative level and execution permission are separate controls.

## Law 5: Model cognition does not own deterministic bookkeeping

LLMs may interpret, plan, compare, critique, and explain.

Deterministic code should own where possible:

```text
state transitions
revision numbers
locks
retry counters
TTL / expiry
idempotency keys
notification cooldowns
deduplication
budgets
side-effect receipts
```

## Law 6: Important success starts unverified

For material objectives, completion criteria begin `unverified` and move to passed only because evidence supports them.

Producing an artifact is not proof of success.

## Law 7: Unfinished is not equivalent to progressing

The Brain must detect waiting, blocking, stalling, wrong strategy, and invalidation.

## Law 8: Learning is staged

One observation is not a principle.

Reflection creates candidates. Candidates require curation and, when appropriate, evaluation before durable promotion.

## Law 9: Self-improvement changes methods, not user sovereignty

The Brain may improve how it pursues approved goals.

It may not silently redefine what the user should want.

## Law 10: Silence is a valid intelligent action

The Brain should be rewarded for not interrupting when the expected value of interruption is low.

## Law 11: Cross-scope access is explicit

A workspace-scoped Brain operation must not silently inspect unrelated workspaces.

## Law 12: Every durable inference preserves provenance

Derived claims without recoverable evidence must remain weak hypotheses, not durable facts.

---

# 5. Five functional planes

The Brain is organized conceptually into five planes.

```text
┌──────────────────────────────────────────────┐
│              AI-VERSE BRAIN                  │
│                                              │
│  1. INTENT PLANE                            │
│     values • goals • practices • boundaries │
│     desired states • success definitions     │
│                     │                        │
│                     ▼                        │
│  2. INITIATIVE PLANE                        │
│     gaps • opportunities • initiatives       │
│     portfolio • priority • attention         │
│                     │                        │
│                     ▼                        │
│  3. COGNITION / CONTROL PLANE               │
│     3Ms • 4Cs • objectives • contracts       │
│     plans • progress • stall • verification │
│                     │                        │
│                     ▼                        │
│  4. MODEL PLANE                             │
│     user • agent • world hypotheses          │
│     confidence • evidence • freshness        │
│                     │                        │
│                     ▼                        │
│  5. LEARNING / EVOLUTION PLANE              │
│     reflection • learning • playbook         │
│     evals • promotion • rollback             │
└──────────────────────────────────────────────┘
```

These are logical planes. They do not require five duplicated software stacks.

---

# 6. Three operating loops

The Brain is not one universal seven-step chain. It has three loops operating at different timescales.

## 6.1 Direction Loop

Purpose: maintain long-horizon direction and decide what deserves attention.

```text
CURRENT STATE
      ↓
DESIRED STATE
      ↓
GAP
      ↓
OPPORTUNITY
      ↓
INITIATIVE
      ↓
PRIORITY / CAPACITY
      ↓
ACTIVE PORTFOLIO
      ↺
```

It answers:

- What matters?
- What changed?
- Which current-state claims are stale?
- Which gaps are consequential?
- Which opportunities are credible?
- Which initiatives should be proposed, activated, paused, or retired?

## 6.2 Action Loop

Purpose: execute one bounded objective without drifting.

```text
OBJECTIVE
   ↓
COMPLETION CONTRACT
   ↓
ORIENT
   ↓
PLAN
   ↓
ACT
   ↓
OBSERVE
   ↓
PROGRESS CHECK
   ↓
VERIFY
   ├── pass -> close
   ├── fail with progress -> continue
   ├── stalled -> replan
   ├── blocked -> wait / ask / escalate
   └── invalidated -> stop / supersede
```

## 6.3 Learning / Evolution Loop

Purpose: improve future behavior without uncontrolled self-modification.

```text
EXPERIENCE
    ↓
OUTCOME / EVIDENCE
    ↓
REFLECTION
    ↓
CANDIDATE LEARNING
    ↓
CURATION
    ↓
CANDIDATE STRATEGY DELTA
    ↓
EVALUATION
    ↓
PROMOTE / REJECT
    ↓
MONITOR REAL USE
    ↓
KEEP / REFINE / ROLLBACK
```

---

# 7. Canonical primitive families

To avoid ontology explosion, the Brain should use a small number of first-class object families with explicit subtypes.

The recommended v1 primitive families are:

```text
1. Intent
2. Practice
3. Gap
4. Opportunity
5. Initiative
6. Objective
7. Model Belief
8. Evaluation
9. Learning
10. Strategy Rule
11. Policy
```

Evidence is referenced everywhere and may have durable receipts, but does not need to become a giant independent knowledge layer.

## 7.1 Intent

Represents explicit desired direction.

Subtypes:

```text
desired_state
goal
boundary
constraint
success_definition
```

Stable identity and general preferences that already belong in AI-Verse OS `operator/profile/` should remain there. The Brain references them rather than duplicating them.

A Brain-created goal starts as `proposed`. Only explicit user authorization can make a materially new goal `confirmed`.

## 7.2 Practice

Represents an ongoing condition rather than a finite terminal outcome.

Examples:

```text
maintain weekly publishing consistency
review finances monthly
keep backups healthy
exercise regularly
```

A practice has a lifecycle state and a health state. It is never permanently `completed`.

## 7.3 Gap

Represents the measured or inferred difference between current state and desired state.

A Gap does not own current-state truth. It contains references to canonical current-state evidence plus a derived interpretation.

## 7.4 Opportunity

Represents a hypothesis that a particular change could create value or prevent loss.

An opportunity may be ignored, watched, dismissed, expired, or promoted into an initiative.

## 7.5 Initiative

Represents a strategic hypothesis about change.

A goal says where the user wants to go.

An initiative says what intervention the Brain believes may move toward that goal.

This distinction lets an initiative fail without invalidating the goal.

## 7.6 Objective

Represents a bounded executable outcome.

Every active Objective contains or references a completion contract.

An Objective is the unit that the Action Loop pursues.

## 7.7 Model Belief

Represents a derived hypothesis in one of three model domains:

```text
user_model
agent_model
world_model
```

It is explicitly lower authority than user intent and canonical current state.

## 7.8 Evaluation

Represents a structured judgment against explicit criteria and evidence.

Evaluation is separate from the artifact or strategy being judged.

## 7.9 Learning

Represents an epistemic candidate or validated conclusion about what tends to happen or what method tends to work.

Learning is not historical memory itself.

## 7.10 Strategy Rule

Represents one atomic, inspectable operating heuristic.

It can be added, updated, retired, reactivated, promoted, or rolled back without rewriting the entire Brain.

## 7.11 Policy

Represents user-approved Brain operating boundaries, including:

```text
proactivity
attention
execution authority
resource budgets
cadence
risk / verification thresholds
```

Policies are privileged. The Brain may propose policy changes but may not silently broaden its own authority.

---

# 8. Common object envelope

Every canonical Brain object should use a common deterministic envelope.

Conceptual schema:

```yaml
schema_version: "1.0"
id: "..."
kind: "initiative"
scope: "operator" # or workspace:<id>
status: "active"
revision: 4
created_at: "..."
updated_at: "..."
created_by: "user|brain|import|migration"
updated_by: "user|brain|controller"
source_refs: []
evidence_refs: []
supersedes: null
superseded_by: null
payload: {}
```

Rules:

- IDs are immutable.
- `revision` increments on every canonical mutation.
- Writes use optimistic concurrency: caller supplies expected revision.
- Silent last-write-wins is forbidden.
- Scope is immutable except through explicit migration.
- Material historical change uses supersession where rewriting would erase meaning.
- Derived confidence is stored only on objects for which confidence is epistemically meaningful.
- A user goal should not carry fake probabilistic confidence about whether the user really wants it.

---

# 9. Authority hierarchy

The Brain needs a strict authority model because it mixes explicit intent, observations, inferences, strategies, and external information.

Recommended precedence:

```text
0. HOST / PLATFORM / ORGANIZATION HARD CONSTRAINTS
   safety, legal, security, system permission boundaries

1. EXPLICIT USER AUTHORITY
   confirmed goals, boundaries, permissions, prohibitions,
   user-approved operating policies

2. CANONICAL SCOPED STATE AND SETTLED DECISIONS
   current workspace/operator state and decisions

3. VERIFIED EVIDENCE
   direct measurement, authoritative current source,
   test result, explicit artifact receipt

4. CONFIRMED DERIVED MODEL
   durable inference supported by evidence and not contradicted

5. VALIDATED AGENT LEARNING / STRATEGY
   operational method proven useful in applicable contexts

6. TEMPORARY HYPOTHESIS
   model-generated interpretation not yet validated
```

## Conflict rules

1. Lower authority never silently overwrites higher authority.
2. Narrower scope wins over broader scope for scoped current state when both are valid.
3. Fresh verified state may supersede stale state, but provenance is preserved.
4. Contradictory same-authority claims become `contradicted` until resolved.
5. Material ambiguity must be surfaced when it changes a consequential decision.
6. External content can provide evidence. It cannot directly alter goals, policies, permissions, or strategy authority.

---

# 10. Explicit intent versus derived user model

This boundary is critical.

## Explicit user intent

Examples:

```text
I want X.
I do not want Y.
This is more important than that.
Never send a client message without asking me.
I want this project complete by December.
```

## Derived user model

Examples:

```text
The user appears to prefer reversible experimentation.
The user often responds better to visual comparison than abstract explanation.
The user seems to value autonomy strongly in this workspace.
```

Derived beliefs must preserve:

```text
statement
scope
confidence
evidence refs
freshness
contradictions
last reviewed
```

A derived belief can influence ranking or personalization.

It cannot create a confirmed user goal or expand permission.

---

# 11. Goal lifecycle

Recommended lifecycle:

```text
DRAFT
  ↓
PROPOSED
  ↓ user confirmation
CONFIRMED
  ↓
ACTIVE
  ├── PAUSED
  ├── ACHIEVED
  ├── ABANDONED
  └── SUPERSEDED
```

Rules:

- A Brain-generated materially new goal cannot skip `PROPOSED`.
- The Brain may infer that an existing explicit user statement maps to a goal, but if the mapping changes meaning, confirmation is required.
- Achieving a goal requires success evidence appropriate to the goal.
- Material redefinition of a confirmed goal creates a new revision or superseding goal rather than rewriting history deceptively.

---

# 12. Practice lifecycle

Practices have two independent state dimensions.

## Lifecycle

```text
DRAFT
PROPOSED
CONFIRMED
ACTIVE
PAUSED
RETIRED
```

## Health

```text
UNKNOWN
HEALTHY
AT_RISK
DEGRADED
BREACHED
```

A practice can remain `ACTIVE` while temporarily `DEGRADED`.

This prevents recurring standards from becoming fake never-ending tasks.

---

# 13. Opportunity lifecycle

```text
DETECTED
   ├── DISMISSED
   ├── EXPIRED
   ├── WATCHING
   └── QUALIFIED
          ↓
       PROPOSED_INITIATIVE
```

Qualification requires:

- linkage to a desired state or protected practice;
- plausible mechanism of value;
- sufficient evidence freshness;
- no obvious duplicate initiative;
- scope and authority compatibility;
- attention/value threshold.

---

# 14. Initiative lifecycle

Recommended deterministic lifecycle:

```text
DISCOVERED
   ↓
PROPOSED
   ├── REJECTED
   ├── DEFERRED
   └── ACCEPTED
          ↓
        ACTIVE
          ├── WAITING
          ├── BLOCKED
          ├── STALLED
          ├── PAUSED
          └── REVIEW
                 ├── ACTIVE
                 ├── COMPLETED
                 ├── ABANDONED
                 └── SUPERSEDED
```

Rules:

- `DISCOVERED` means the Brain noticed it.
- `PROPOSED` means it is worth user or policy consideration.
- `ACCEPTED` means the initiative is permitted to enter the active portfolio.
- `ACTIVE` does not itself grant external side-effect permission.
- `STALLED` is distinct from `BLOCKED`.
- `COMPLETED` requires outcome verification, not merely exhaustion of planned tasks.
- A dismissed or rejected initiative must respect cooldown/deduplication policy before resurfacing.

---

# 15. Objective lifecycle and progress ledger

Recommended lifecycle:

```text
QUEUED
  ↓
READY
  ↓
RUNNING
  ├── WAITING
  ├── BLOCKED
  ├── STALLED
  ├── VERIFYING
  │      ├── PASSED
  │      ├── FAILED
  │      └── INSUFFICIENT_EVIDENCE
  ├── CANCELLED
  └── SUPERSEDED
```

The controller also stores a progress classification:

```text
progressing
waiting
blocked
stalled
wrong_strategy
invalidated
complete_unverified
verified_complete
```

## Stall rule

A retry is not progress merely because another tool call occurred.

The Brain should compare expected state change with observed state change.

A configurable number of non-progressing attempts triggers `STALLED` and mandatory replanning rather than another identical retry.

## Attempt and resource budgets

Every non-trivial objective can specify:

```text
max_attempts
max_wall_time
max_compute_or_cost
max_external_actions
approval_deadline
stop_conditions
```

Exhaustion causes `BLOCKED`, `FAILED`, or `REVIEW` depending on policy. It never silently expands the budget.

---

# 16. Completion contract

Every bounded Objective uses adaptive-depth completion criteria.

## Minimal contract

```yaml
outcome: "..."
done_when:
  - "..."
```

## Full contract

```yaml
problem: "..."
desired_state: "..."
outcome: "..."
success_criteria:
  - id: criterion-1
    statement: "..."
    status: unverified
    required_evidence: "..."
verification_method: "..."
constraints: []
boundaries: []
risks: []
dependencies: []
rollback_or_recovery: "..."
stop_conditions: []
budget: {}
```

## Default-unverified rule

Material criteria begin `unverified`.

Statuses:

```text
unverified
passed
failed
insufficient_evidence
not_applicable
```

A criterion may move to `passed` only with attached evidence.

---

# 17. Evidence model

The Brain needs strong evidence semantics without pretending every judgment can be reduced to a perfect number.

Recommended evidence classes:

```text
USER_CONFIRMATION
explicit statement from the authorized user

CANONICAL_STATE
current authoritative local state or settled decision

DIRECT_MEASUREMENT
measured metric, test output, system receipt, observed artifact state

AUTHORITATIVE_EXTERNAL
fresh trusted external source appropriate to the claim

INDEPENDENT_EVALUATION
separate evaluator judgment against explicit criteria

CORROBORATED_HISTORY
multiple relevant historical observations

SINGLE_OBSERVATION
one relevant experience or event

MODEL_INFERENCE
reasoned interpretation without direct confirmation
```

Each evidence reference should include where relevant:

```text
source ref
observed_at
freshness / expiry
scope
claim supported
integrity/checksum if applicable
```

## Evidence strength is criterion-specific

A casual wording preference may be validated by user confirmation.

A production deployment may require a test suite and live health check.

A high-stakes financial or medical action may require external authoritative confirmation and explicit approval.

There is no single global evidence threshold that fits every domain.

---

# 18. Verification depth

Verification scales with impact.

Suggested levels:

```text
V0 - trivial
quick self-check

V1 - normal
explicit criteria + direct evidence

V2 - important
criteria + direct evidence + fresh evaluator context

V3 - high-impact / hard-to-reverse
independent evaluator + authoritative evidence + rollback/recovery check + explicit approval where required
```

The Brain selects the minimum sufficient level based on:

```text
impact
irreversibility
uncertainty
novelty
cost
privacy / security sensitivity
external side effects
verification difficulty
history of failure
```

The user or host policy may always require a higher level.

---

# 19. Independent evaluator contract

For V2/V3 work, evaluator independence means:

- the evaluator receives the contract, artifact/result, and evidence;
- it does not inherit the builder's hidden reasoning;
- it cannot silently modify the artifact it judges;
- it returns criterion-level verdicts;
- `insufficient_evidence` is a valid result;
- evaluation failure does not automatically trigger unbounded retry.

If a separate model/context is unavailable, the Brain should use a fresh evaluation context and disclose the reduced independence internally in the evaluation record.

---

# 20. Adaptive cognition depth

The Brain should not force every task through the same ceremony.

Cognition depth is selected from factors such as:

```text
impact
irreversibility
uncertainty
novelty
complexity
cost
number of dependencies
risk
stakeholder count
verification difficulty
```

Suggested modes:

```text
C0 - direct
low-risk, reversible, obvious

C1 - deliberate
normal planning and quick verification

C2 - structured
explicit 3Ms/4Cs, contract, dependencies, progress ledger

C3 - rigorous
structured planning, independent evaluation, risk analysis, rollback
```

The mode is a policy output, not a personality setting.

The Brain should be able to explain which factors caused a deeper mode.

---

# 21. Three Ms integration

The Three Ms are used when a gap requires strategic intervention.

They are not mandatory ceremony for trivial objectives.

## Mindset

Ask:

```text
Where can AI or system design create meaningful leverage?
Is this gap worth solving?
What becomes possible if the constraint disappears?
```

## Method

Ask:

```text
What is the true constraint?
Can we eliminate work instead of automating it?
What is the actual process?
What measurable outcome matters?
What autonomy level is appropriate?
What evidence would show improvement?
```

## Machine

Ask:

```text
What is the smallest reliable implementation?
Which capabilities are needed?
How is it verified?
How is rollout supervised?
What can fail?
What is the kill switch or recovery path?
```

Output from 3Ms should normally become an initiative hypothesis, objective, capability request, or automation candidate, not a generic essay.

---

# 22. Four Cs integration

The Four Cs become a readiness gate.

```text
CONTEXT
Do we know enough and is it fresh enough?

CONNECTIONS
Can the host reach required systems and sources?

CAPABILITIES
Can the work be performed reliably?

CADENCE
Is this process mature enough to repeat or run proactively?
```

Readiness states:

```text
ready
needs_context
needs_connection
needs_capability
not_ready_for_cadence
blocked_by_policy
```

The Brain should not solve a missing Connection by inventing credentials or solve a missing Capability by pretending the runtime can do something it cannot.

---

# 23. Cadence: the missing trigger mechanism

Cadence is explicitly solved by separating **Brain trigger policy** from **scheduler implementation**.

The Brain decides what should happen when it is invoked.

The host OS/runtime/cron/automation layer decides when the invocation physically occurs.

This prevents the Brain from becoming a second scheduler.

## 23.1 Standard Brain trigger types

```text
explicit
session_start
session_end
scheduled_orientation
scheduled_review
event
objective_wake
blocker_resolution
external_change
manual_recovery
```

## 23.2 Trigger envelope

Every trigger should have a deterministic envelope:

```yaml
trigger_id: "..."
trigger_type: "session_start"
scope: "operator" # or workspace:<id>
occurred_at: "..."
idempotency_key: "..."
source_refs: []
payload_refs: []
```

The same idempotency key must not execute the same Brain tick twice.

## 23.3 Session start behavior

Default session start should be lightweight:

1. identify scope;
2. load active goals/practices and top active initiatives for that scope;
3. check whether current-state dependencies are stale;
4. produce a compact orientation projection;
5. do not run deep strategic review unless a trigger threshold is met.

This gives the agent persistent direction without imposing large latency on every conversation.

## 23.4 Session end behavior

Default session end should:

1. update objective/initiative progress if the session materially changed state;
2. record verification receipts;
3. identify meaningful user corrections;
4. create candidate learning only when the outcome crosses a learning threshold;
5. schedule future review if needed;
6. avoid storing a reflection merely because a session ended.

## 23.5 Scheduled orientation

Recommended default: at most once per day when enabled.

Purpose:

- refresh top priorities;
- check due/waiting objectives;
- detect urgent practice degradation;
- batch worthwhile low-priority suggestions;
- do not perform full strategic replanning every day.

## 23.6 Scheduled strategic review

Recommended default: weekly when enabled.

Purpose:

- reassess current -> desired gaps;
- review initiative portfolio;
- retire stale initiatives;
- re-check goal/practice alignment;
- inspect repeated stalls;
- consider candidate learning promotion;
- evaluate whether any repeatable workflow is mature for Cadence/automation.

## 23.7 Event-driven triggers

Event triggers are preferable to polling when a reliable host event exists.

Examples:

```text
objective due
new verified metric
approval received
blocker cleared
external system change
new workspace created
strategy evaluation completed
```

## 23.8 Standalone mode cadence

Standalone Brain should expose a deterministic command/API such as conceptually:

```text
brain tick --trigger <type> --scope <scope>
```

The installer may provide examples for cron, launchd, Windows Task Scheduler, or host-agent hooks.

It should not require a background daemon by default.

## 23.9 AI-Verse OS cadence

In native mode, AI-Verse OS owns automation jobs, triggers, policies, and scheduler execution.

Brain emits or maintains Brain trigger definitions; OS cadence invokes the Brain.

The Brain does not duplicate `automations/`.

---

# 24. Cadence maturity ladder

Not every successful workflow deserves automation.

The Brain should use a maturity ladder:

```text
M0 - ad hoc
one-off, poorly understood

M1 - assisted
repeatable with human guidance

M2 - repeatable
clear trigger, inputs, steps, outputs, verification

M3 - supervised cadence
runs on schedule/event with review and bounded side effects

M4 - delegated cadence
automated inside explicit permissions with monitoring and recovery
```

Promotion toward M3/M4 requires:

- repeated successful execution;
- clear trigger;
- stable inputs;
- explicit verification;
- known failure modes;
- idempotency where side effects exist;
- recovery/rollback plan;
- permission policy;
- attention/notification behavior.

When mature, Brain proposes a real OS automation or host scheduler job. Brain itself does not become the scheduler.

---

# 25. Proactivity levels

A single `be proactive` switch is insufficient.

The user should control how aggressively the Brain surfaces and prepares initiatives.

Recommended levels:

## P0 - Reactive

- no unsolicited initiative surfacing;
- Brain operates when explicitly asked;
- required objective wake/recovery events may still occur if user previously authorized them.

## P1 - Observant

- Brain may run background gap/health checks;
- findings remain internal or available on request;
- no unsolicited suggestions except urgent safety/expiry conditions already authorized by policy.

## P2 - Advisory - recommended default

- Brain may proactively surface high-value suggestions;
- suggestions are bounded by attention budget;
- no consequential external action without permission.

## P3 - Assistive

- Brain may perform reversible internal preparation within defined scope, such as analysis, drafting, organizing, planning, test preparation;
- external writes/messages/spending/deletion remain governed by explicit action policy.

## P4 - Delegated

- Brain may execute pre-authorized action classes within explicit scope, budget, and verification rules;
- high-stakes or privileged classes remain approval-gated regardless of level.

---

# 26. Proactivity is separate from execution authority

P4 does not mean `do anything`.

Execution authority must be represented as an action-policy matrix.

Example classes:

```text
read_local
read_connected
write_local_reversible
modify_canonical_state
external_write_reversible
send_message
publish_publicly
spend_money
create_commit_or_pr
merge_or_deploy
delete_data
change_permissions
security_sensitive
high_stakes_domain_action
```

Each action class can have a policy:

```text
deny
ask_every_time
allow_within_scope
allow_within_budget
allow_if_reversible
```

The Brain may never widen this matrix by self-improvement.

---

# 27. Attention economy and anti-annoyance policy

The proactive Brain must optimize for useful intervention, not maximum intervention.

Recommended controls:

```text
max_active_initiatives
max_proactive_items_per_session
max_interruptions_per_day
minimum_interrupt_score
quiet_periods
cooldown_after_dismissal
cooldown_after_notification
batch_low_priority_items
deduplicate_similar_opportunities
expiry for stale opportunities
scope-specific overrides
```

Recommended default active-initiative WIP cap: **3 per scope**, configurable.

The purpose is not to claim that three is universally optimal. It creates an explicit scarcity constraint so the Brain has to choose.

## Notification classes

```text
INTERRUPT
urgent, high confidence, time-sensitive, material consequence

SURFACE
high-value suggestion at a natural interaction point

BATCH
useful but not urgent; include in orientation/digest

STORE
keep as watched opportunity; no user interruption

DROP
insufficient value/confidence or duplicate
```

## Dismissal memory

Dismissed suggestions must generate a cooldown fingerprint so the Brain does not repeatedly nag with semantically equivalent proposals unless material new evidence appears.

---

# 28. Initiative qualification and ranking

Ranking should be inspectable and deterministic enough to audit.

Use a two-stage model.

## Stage 1: eligibility gate

An opportunity is not rankable until it passes:

```text
approved desired-state linkage
scope validity
permission compatibility
non-duplication
minimum evidence freshness
minimum confidence
not already rejected within cooldown
not blocked by hard boundary
```

## Stage 2: score components

Recommended normalized components:

```text
goal_alignment
expected_impact
urgency
confidence
strategic_leverage
readiness_4c
reversibility

effort_cost
attention_cost
risk
opportunity_cost
```

A default implementation may use a weighted model, but:

- every component must be inspectable;
- the final score must not hide a hard policy violation;
- hard gates outrank score;
- user priority can override ranking;
- weights may be configured by scope;
- scores should not pretend to mathematical precision when inputs are qualitative.

The Brain should preserve the component explanation so a user can understand why an initiative surfaced.

---

# 29. Current-state freshness

Gap quality depends on current-state quality.

Every current-state dependency used by a Gap or Initiative should expose:

```text
source ref
observed_at
freshness class / expires_at if appropriate
authority
contradiction status
```

Before high-impact action, the Brain revalidates stale dependencies where feasible.

A stale fact should degrade confidence rather than silently remaining current forever.

---

# 30. Derived model plane

The Model Plane contains hypotheses, not privileged truth.

## 30.1 User model

May include:

```text
interaction preferences
likely decision style
recurring friction patterns
probable priorities
communication tendencies
```

Sensitive inferences should be minimized and never persisted merely because they are interesting.

## 30.2 Agent model

May include:

```text
known runtime capabilities
common failure modes
strategies that work well
strategies that perform poorly
tool reliability
model-specific limitations
```

## 30.3 World model

May include:

```text
external dependencies
assumptions
market/system state relevant to active goals
causal hypotheses
constraints outside the user's control
```

## 30.4 Native epistemic states

```text
known
inferred
assumed
unknown
contradicted
stale
```

The Brain should prefer `unknown` over fabrication.

---

# 31. Epistemic learning lifecycle

Recommended lifecycle:

```text
OBSERVATION
    ↓
HYPOTHESIS
    ↓
PATTERN
    ↓
REFLECTION
    ↓
VALIDATED_LEARNING
    ↓
STRATEGY_CANDIDATE
```

Promotion rules vary by type.

## Direct user correction

A clear user correction can immediately become an explicit preference/constraint when appropriate, but it must be routed to the canonical owner rather than stored as a Brain strategy.

## Agent strategy inference

One outcome should normally not create a durable rule.

Promotion may require:

- repeated independent observations; or
- one strong controlled evaluation; or
- explicit user confirmation; or
- a combination defined by policy.

## Causality caution

The Brain must distinguish:

```text
correlation
plausible causal explanation
controlled evidence
```

It should not claim a strategy caused success merely because success followed its use once.

---

# 32. Reflection triggers

Reflection is expensive and noisy if performed automatically after everything.

Recommended reflection triggers:

```text
objective passed after significant work
objective failed materially
repeated stall
unexpected success
user correction
strategy regression
contradictory evidence
initiative review
scheduled weekly learning review
```

No reflection is required after a trivial normal interaction.

Most raw reflections should be ephemeral.

Persist only the resulting candidate learning or high-value evaluation when warranted.

---

# 33. Strategy playbook

The Brain's adaptive operating knowledge should be atomic rather than one giant mutable prompt.

Conceptual Strategy Rule:

```yaml
id: "verify-high-impact-output"
kind: "strategy_rule"
scope: "operator"
status: "active"
revision: 3
payload:
  applies_when:
    - "high-impact irreversible output"
  instruction:
    - "Use independent verification before declaring completion."
  exclusions: []
  helpful_evidence_count: 12
  harmful_evidence_count: 0
  evaluation_refs:
    - "eval-..."
```

Allowed lifecycle operations:

```text
ADD
UPDATE
RETIRE
REACTIVATE
ROLLBACK
```

No giant prompt rewrite should be necessary for ordinary evolution.

---

# 34. Strategy effectiveness measurement

This solves the difficult question: **did the strategy actually work?**

The Brain should collect strategy-use traces only when useful.

A trace can link:

```text
strategy rule
context / scope
objective
preconditions
outcome
verification result
user feedback
cost / attempts
stall count
```

Evidence types for effectiveness include:

```text
repeated observational success
repeated observational harm
A/B or shadow evaluation
baseline comparison
holdout evaluation
user correction / endorsement
objective-level metric change
regression test
```

## No false causal certainty

Observational success can raise confidence, but should not be labeled causal proof.

For high-impact strategy promotion, baseline or controlled evaluation should be preferred.

## Useful metrics

Depending on strategy:

```text
success rate
criterion pass rate
attempts to completion
stall frequency
resource cost
latency
user overrides
error / rollback frequency
attention cost
```

The Brain should not optimize a single metric blindly.

---

# 35. Goodhart protection and multi-objective evaluation

Self-improvement can become dangerous if one metric dominates.

Every strategy evaluation should consider a balanced objective set when relevant:

```text
quality
correctness
safety
privacy
cost
latency
user attention
reversibility
maintainability
```

Improvement on one dimension must not silently justify catastrophic regression on another.

Hard constraints remain hard constraints even if aggregate score improves.

---

# 36. Self-improvement permission tiers

Not every adaptive artifact has equal privilege.

Recommended tiers:

## E0 - Ephemeral tactic

Temporary within one objective/session.

May change freely within host constraints.

## E1 - User-local strategy rule

May become a candidate automatically.

Can auto-promote only if policy permits and evaluation thresholds pass.

Must remain reversible.

## E2 - Scope-shared durable strategy

Promotion requires stronger evidence and regression evaluation.

User review may be required depending on impact.

## E3 - Shipped/core Brain behavior

The running Brain does not overwrite it directly.

Improvement should be emitted as a patch/branch/PR with tests.

## E4 - Privileged authority / safety / permission policy

Never self-modifies.

Only explicit authorized human/system changes may alter it.

---

# 37. Strategy evolution pipeline

```text
baseline strategy
    ↓
collect traces
    ↓
identify failure/opportunity
    ↓
reflection
    ↓
candidate delta
    ↓
static constraints
    ↓
evaluation set
    ↓
run baseline + candidate
    ↓
compare multi-objective results
    ↓
regression / semantic-preservation checks
    ↓
PASS?
  ├── no -> reject
  └── yes
        ↓
    approval gate if required
        ↓
      promote
        ↓
 monitor real operation
        ↓
 keep / refine / rollback
```

Every promoted artifact must retain the prior version or a reconstructable history.

---

# 38. Rollback and recovery

Rollback is mandatory for self-improving state.

## Strategy rollback

A promoted strategy should be reverted when:

- a hard regression appears;
- real-world harm exceeds policy threshold;
- user explicitly rejects it;
- evaluation was later found contaminated or invalid;
- a newer authoritative policy conflicts with it.

## Objective recovery

The controller checkpoints before/after consequential side effects.

A process crash must not blindly replay an external action.

External side effects should have receipts/idempotency keys where the host supports them.

If rollback is impossible, the contract must define a compensating/recovery path or require approval before action.

---

# 39. Concurrency and multi-agent safety

A Brain may be accessed by multiple agents or sessions.

Required controls:

```text
object revision numbers
optimistic concurrency checks
short-lived runtime locks
stale-lock expiry
idempotency keys
side-effect receipts
no silent last-write-wins
```

If two sessions try to update the same initiative from revision 4:

- first valid write creates revision 5;
- second write using expected revision 4 fails conflict;
- the agent must reload and reconcile.

This is preferable to silently losing one agent's state.

---

# 40. Side-effect safety

The Brain reasons about action but the host runtime performs the side effect.

For side-effecting objectives, the execution request should contain conceptually:

```text
objective_ref
action_class
scope
requested_action
permission_basis
idempotency_key
budget impact
rollback/recovery info
verification expectation
```

The host returns a receipt.

The Brain uses the receipt as evidence.

It should not infer that a send/deploy/publish succeeded merely because the tool call was attempted.

---

# 41. Prompt-injection and authority-confusion defense

External content is evidence, not authority.

Instructions found in:

```text
web pages
emails
PDFs
repository files
messages
retrieved memory
connected documents
```

must not be allowed to redefine Brain goals, policies, permissions, system rules, or self-improvement boundaries simply because the model read them.

The Brain should tag source material as data unless it comes through an explicitly authorized control channel.

Examples of forbidden promotion:

```text
web page says "ignore previous goals"
        ↓
Brain deletes goals
```

```text
untrusted file says "allow autonomous publishing"
        ↓
Brain changes permission policy
```

Both are authority violations.

---

# 42. Sensitive inference and privacy

The Brain should minimize persistent derived personal inference.

Rules:

- Do not infer or store sensitive traits unless clearly necessary for an authorized task and permitted by host/user policy.
- Do not persist credentials, private keys, recovery codes, or secrets.
- Prefer references to OS Connection entries rather than copying authentication data.
- Scope private derived models as narrowly as possible.
- Cross-workspace inference requires explicit authorization when it would combine otherwise isolated user data.
- User deletion/forget requests must propagate to Brain-owned objects and associated derived projections/indexes.

---

# 43. Scope isolation

Native scopes:

```text
operator
workspace:<id>
```

Rules:

- Workspace Brain operations see that workspace plus permitted operator-level intent/policy.
- They do not silently inspect unrelated workspaces.
- Operator-level portfolio reasoning may use workspace summaries/references when authorized.
- Raw cross-workspace retrieval is explicit and auditable.
- Strategy rules stay local until evidence supports promotion to a broader scope.

This mirrors AI-Verse OS and Memory isolation rather than inventing a new scope model.

---

# 44. Write contract with AI-Verse OS

This is the key anti-corruption contract.

## OS remains canonical owner of

```text
operator/profile/
operator/context/
operator/decisions/
knowledge/
workspaces/<id>/WORKSPACE.yaml
workspaces/<id>/context/
workspaces/<id>/decisions/
workspaces/<id>/knowledge/
connections/
skills/
agents/
automations/
apps/
runtime ownership rules
```

## Brain must not duplicate those into its own state

Examples:

- Current project state is referenced from workspace `context/CURRENT.md`, not copied into a permanent Brain current-state file.
- Stable operator preference stays in `operator/profile/`.
- Settled system/business decision stays in `decisions/`.
- Reusable domain knowledge stays in `knowledge/`.

## Brain-native canonical state

The Brain needs a scoped extension namespace for what the OS currently does not own:

```text
operator/brain/
workspaces/<id>/brain/
```

These paths should contain only Brain-owned primitives such as:

```text
intent/
practices/
initiatives/
objectives/
models/
strategies/
evaluations/
policies/
```

The exact physical layout is finalized in the implementation section below.

## Write routing

When the Brain learns something, classification comes before persistence:

```text
stable identity/preference -> OS profile
current state -> OS context
settled decision -> OS decisions
historical event/experience -> Memory protocol if installed, otherwise host history path
reusable knowledge -> OS knowledge
repeatable execution -> skill/automation candidate
Brain goal/initiative/objective/model/strategy -> Brain namespace
transient thought -> no durable write
```

The Brain is therefore a **writer through contracts**, not a universal writer to arbitrary files.

---

# 45. Write contract with AI-Verse Memory

AI-Verse Memory remains the historical memory engine.

The Brain uses Memory for:

```text
historical evidence recall
prior initiative outcomes
past user corrections
strategy-use history
state transition history
relevant experiences
```

The Brain must not create a parallel general-purpose memory store.

## Durable Brain history versus Memory

Brain-owned canonical state may contain lifecycle history necessary to understand the current object.

General historical experiences belong to Memory.

Example:

```text
initiative.status = completed
initiative.evaluation_refs = [...]
```

is Brain state.

```text
"The third publishing cycle failed because the source video arrived late"
```

is historical experience and belongs in Memory when durable.

## Memory write routing

Brain-generated historical capture must use Memory's scope and writeback rules.

Current context always outranks recalled historical memory.

---

# 46. Native AI-Verse storage contract

Recommended installed canonical paths:

```text
operator/
└── brain/
    ├── intent/
    ├── practices/
    ├── initiatives/
    ├── objectives/
    ├── models/
    ├── strategies/
    ├── evaluations/
    └── policies/

workspaces/
└── <id>/
    └── brain/
        ├── intent/
        ├── practices/
        ├── initiatives/
        ├── objectives/
        ├── models/
        ├── strategies/
        ├── evaluations/
        └── policies/

runtime/
└── ai-verse-brain/
    ├── indexes/
    ├── locks/
    ├── queue/
    ├── projections/
    ├── logs/
    └── temporary-evals/
```

Rules:

- `operator/brain/` and workspace `brain/` are user-owned canonical Brain state.
- `runtime/ai-verse-brain/` is derived/disposable.
- indexes, queue caches, projections, and locks are rebuildable.
- user intent is not stored only in runtime.
- no `.ai-verse-brain/` parallel store should be created in AI-Verse OS native mode.

## Native manifest integration

Before native release, AI-Verse OS should expose an optional Brain extension slot analogous to the Memory extension contract, or the Brain installer should register one deterministically if absent.

Conceptually:

```yaml
extensions:
  brain:
    supported: true
    optional: true
    provider: ai-verse-brain
    version: "..."
    engine: "scripts/ai-verse-brain/..."
    operator_state: "operator/brain/"
    workspace_state: "workspaces/{workspace}/brain/"
    runtime: "runtime/ai-verse-brain/"
```

This specification does **not** modify AI-Verse OS. It defines the contract Phase 4 should implement.

---

# 47. Standalone storage contract

Without AI-Verse OS, Brain needs a minimal portable home:

```text
.ai-verse-brain/
├── config.yaml
├── intent/
├── practices/
├── initiatives/
├── objectives/
├── models/
├── strategies/
├── evaluations/
├── policies/
└── runtime/
    ├── indexes/
    ├── locks/
    ├── queue/
    └── projections/
```

Standalone mode may maintain only the minimum contextual references it needs.

It should not attempt to recreate the full AI-Verse OS workspace/knowledge/connection architecture.

A host adapter supplies:

```text
current context
execution capability
optional history retrieval
scheduler hooks
side-effect receipts
```

If no historical memory provider exists, Brain learning is limited to Brain-owned evaluations/strategy traces rather than becoming a replacement general memory engine.

---

# 48. Generated orientation projection

At session start, the Brain should create a small derived orientation capsule rather than loading all state.

Conceptual content:

```text
active scope
explicit top goals / practices
top active initiatives
current objective if any
hard boundaries
important blockers
stale critical assumptions
proactive items worth surfacing
```

This projection lives under runtime/derived state and can be regenerated.

It must point back to canonical Brain/OS sources.

---

# 49. User control surface

The Brain needs an inspectable control surface from day one.

At minimum the user should be able to:

```text
see confirmed goals and practices
see active initiatives and why they were ranked
approve/reject/defer an initiative
pause all proactivity
set proactivity level
set action permissions
set attention budgets
see current objectives and blockers
see why something is considered complete
inspect derived user beliefs
correct/delete a derived belief
see active strategy rules
see recent strategy promotions/rollbacks
force a strategic review
stop an objective
kill all autonomous execution
```

A CLI, agent command set, or app can expose this later, but these operations belong in the protocol from the start.

---

# 50. Kill switches

Required safety controls:

```text
PAUSE_BRAIN
stops proactive ticks but preserves state

STOP_OBJECTIVE <id>
cancels active execution request

PROACTIVITY P0
forces reactive mode

EXTERNAL_ACTIONS DENY
blocks all Brain-requested external side effects

RESET_DERIVED_MODELS
clears/rebuilds Brain-derived models without deleting user intent

ROLLBACK_STRATEGY <id> <revision>
restores previous strategy revision
```

A kill switch must not depend on the same uncertain reasoning loop it is intended to stop.

---

# 51. Resource governance

Background intelligence can create runaway cost.

Brain policy must support budgets such as:

```text
max_background_ticks_per_day
max_deep_reviews_per_week
max_eval_runs_per_strategy_candidate
max_objective_attempts
max_compute_or_token_budget
max_external_actions
max_parallel_objectives
```

When a budget is exhausted:

- the Brain stops or degrades gracefully;
- it records the block;
- it does not silently raise the budget;
- it may propose a policy change to the user.

---

# 52. Offline and degraded operation

The Brain should degrade predictably when dependencies disappear.

## No Memory

- current goals/initiatives still work;
- historical recall is limited;
- learning confidence should account for missing history.

## No OS

- standalone scope and state contract is used;
- host adapter provides execution/context.

## No external network

- local reasoning and local state continue;
- opportunities requiring live evidence remain stale/unverified.

## No independent evaluator/model

- use fresh context self-evaluation at reduced verification grade;
- do not pretend full independence.

## Missing capability/connection

- 4Cs reports the actual deficit;
- Brain may propose acquiring/building capability;
- it must not fabricate success.

---

# 53. Schema migration and compatibility

Every canonical object has `schema_version`.

Migration rules:

- migrations are explicit and idempotent;
- destructive migration requires backup/recovery path;
- unknown future fields are preserved where possible;
- downgrade limitations are reported;
- partial migration must not silently produce mixed authority;
- native installer must detect compatible AI-Verse OS schema before writing native paths;
- incompatible OS version falls back or aborts safely, never guesses.

---

# 54. Auditability

The Brain should be able to explain important decisions without exposing private hidden reasoning.

For material initiative selection or action, retain structured rationale:

```text
goal refs
gap refs
score components
key evidence
uncertainties
policy basis
permission basis
verification requirement
```

This is an audit record, not a chain-of-thought transcript.

---

# 55. Health / doctor checks

A native `doctor` should eventually verify:

```text
mode detection
canonical Brain paths
writability
schema validity
OS scope compatibility
Memory integration if present
no duplicate standalone store in native mode
strategy revision integrity
objective state integrity
stale locks
queue idempotency
permission policy validity
cadence registration
Claude/Codex/host adapter parity
runtime derived-path isolation
cross-workspace isolation
no secrets in canonical objects
ability to rebuild derived indexes/projections
```

Standalone doctor checks analogous local requirements.

---

# 56. Required QC test families

Phase 4 implementation should not be considered complete without tests covering:

```text
source-of-truth isolation
goal confirmation rules
derived-model authority boundaries
workspace isolation
cross-workspace explicit opt-in
initiative ranking reproducibility
attention cooldown/deduplication
proactivity levels
permission matrix enforcement
objective retry/stall detection
budget exhaustion
verification default-unverified behavior
independent evaluator separation
learning promotion thresholds
strategy regression rejection
strategy rollback
concurrent write conflicts
idempotent trigger replay
idempotent side-effect request handling
crash/recovery behavior
stale lock cleanup
schema migrations
standalone mode
AI-Verse OS native mode
AI-Verse OS + Memory mode
offline degraded mode
prompt-injection authority defense
secret-persistence guard
```

A separate Phase 3 QC/risk matrix is maintained beside this specification.

---

# 57. Proposed repository architecture for implementation

The **source repository** should remain separate from installed user state.

Recommended source layout:

```text
AI-Verse-Brain/
├── README.md
├── LICENSE
├── BRAIN.yaml                    # package/spec manifest, not user state
├── protocol/
│   ├── BRAIN-PROTOCOL.md
│   ├── AUTHORITY.md
│   ├── WRITE-CONTRACT.md
│   ├── CADENCE.md
│   ├── PROACTIVITY.md
│   └── EVOLUTION.md
├── schemas/
│   ├── common.schema.json
│   ├── intent.schema.json
│   ├── practice.schema.json
│   ├── gap.schema.json
│   ├── opportunity.schema.json
│   ├── initiative.schema.json
│   ├── objective.schema.json
│   ├── model-belief.schema.json
│   ├── evaluation.schema.json
│   ├── learning.schema.json
│   ├── strategy-rule.schema.json
│   └── policy.schema.json
├── engine/
│   └── ... deterministic controller / library
├── integrations/
│   ├── ai-verse-os.md
│   ├── ai-verse-memory.md
│   └── generic-agent.md
├── adapters/
│   ├── claude/
│   ├── codex/
│   └── hermes-or-generic/
├── templates/
│   ├── standalone/
│   └── native/
├── scripts/
│   ├── install.py
│   └── ...
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── fixtures/
│   └── evals/
└── research/
    ├── PHASE-1-LANDSCAPE.md
    ├── PHASE-2-ARCHITECTURE-DISSECTION.md
    ├── PHASE-3-BRAIN-SPECIFICATION.md
    ├── PHASE-3-QC-RISK-MATRIX.md
    └── SOURCE-MAP.md
```

The final implementation language is not mandated by the architecture, but a small deterministic local controller is preferred over making everything prompt-only.

---

# 58. Runtime-neutral adapter contract

The Brain should expose a compact host interface rather than hardcode one agent runtime.

Conceptual host capabilities:

```text
read_context(scope)
retrieve_history(query, scope)
list_capabilities(scope)
list_connections(scope)
request_action(action, permission_context)
request_evaluation(contract, artifact, evidence, level)
schedule_trigger(trigger)
cancel_trigger(trigger_id)
notify_user(notification)
write_route(classification, payload, scope)
```

AI-Verse OS adapter maps these to OS structures.

Standalone adapters map them to whatever the host can provide.

The core Brain should not know whether the runtime is Claude, Codex, Hermes, GPT, or another capable agent.

---

# 59. Installer principles

Phase 4 installer should follow the successful Memory design principles:

- mode detection;
- idempotent installation;
- no destructive overwrite of user state;
- native OS paths when compatible OS is detected;
- standalone fallback otherwise;
- one bounded canonical runtime integration, not duplicated full instructions;
- skill/adapter parity;
- doctor at the end;
- migration dry-run before applying legacy changes;
- derived indexes remain disposable;
- secrets never written.

Native install should not create `.ai-verse-brain/`.

---

# 60. Brain context injection strategy

The Brain should not dump its entire state into every prompt.

Use progressive disclosure:

```text
1. scope + hard policy
2. active intent/practices
3. top active initiatives/objective
4. exact supporting models/evidence only when needed
5. historical Memory recall only when needed
6. deeper knowledge via OS routing only when needed
```

This reduces context bloat and makes authority clearer.

---

# 61. Goal conflict handling

Users can have conflicting goals.

The Brain must not secretly resolve value conflicts by choosing one.

It should detect conflict types such as:

```text
resource conflict
time conflict
explicit priority conflict
constraint conflict
mutually exclusive outcomes
```

Resolution order:

1. explicit user priority if available;
2. hard boundaries/constraints;
3. current commitments/accepted initiatives;
4. impact and urgency ranking;
5. ask user when the unresolved conflict is material.

A conflict should remain explicit until resolved.

---

# 62. Initiative invalidation

An initiative should be invalidated when its underlying assumptions fail.

Examples:

- the goal was superseded;
- the gap no longer exists;
- external state changed;
- the proposed mechanism repeatedly failed;
- a new hard constraint makes it impossible;
- expected value fell below attention threshold.

Invalidation must not be interpreted as failure of the user goal itself.

---

# 63. Stale-task resurrection prevention

The Brain must never repeatedly revive abandoned or outdated work merely because it appears in history.

Controls:

```text
terminal lifecycle states
supersession links
expiry / review dates
cooldown fingerprints
current-state authority over memory
explicit user dismissal
no heartbeat scanning of arbitrary historical tasks
```

Scheduled orientation reviews only active/watching state, not the entire historical archive by default.

---

# 64. Metric gaming protection

When a goal has metrics, the Brain should distinguish the metric from the actual desired state.

Example:

```text
Desired state: healthier audience engagement
Metric: comments per post
```

The Brain should not optimize comments by using manipulative content if that violates quality, brand, or user boundaries.

Success definitions should include qualitative/hard constraints where necessary.

Metrics are evidence, not the user's values themselves.

---

# 65. Human override

The user can always:

- reprioritize goals;
- cancel initiatives;
- mark a model belief wrong;
- require more verification;
- lower proactivity;
- narrow permissions;
- reject strategy changes;
- force rollback;
- disable background cadence.

A human override is recorded with provenance so the Brain learns from it without reframing it as an error by the user.

---

# 66. What the Brain may autonomously change

Allowed within policy:

```text
initiative rankings
objective plans
reversible tactics
attention batching
hypothesis confidence
strategy candidate generation
low-risk local strategy rules after evaluation
review scheduling
stale opportunity expiry
progress classifications
```

---

# 67. What the Brain may not autonomously change

Never silently self-modify:

```text
confirmed user values
goals
identity
hard boundaries
permission matrix
privacy policy
risk tolerance
approval requirements
meaning of success
platform/system safety constraints
scope isolation rules
self-improvement privilege tiers
```

Material changes become proposals requiring authorized confirmation.

---

# 68. Definition of a high-quality Brain action

A good Brain action is:

```text
aligned
scoped
permission-valid
evidence-aware
fresh enough
proportionate in reasoning depth
attention-efficient
bounded
verifiable
recoverable where needed
learnable
```

If an action cannot be verified or safely bounded, the Brain should often propose/plan rather than execute.

---

# 69. Minimal day-one functional slice

The first implementation should not attempt every advanced feature at once.

However, it must establish the architecture correctly.

Minimum v0.1 capability:

```text
native + standalone mode detection
canonical goals/practices
explicit authority rules
gap generation
initiative proposal and ranking
WIP/attention policy
objective contracts
progress/stall state
verification receipts
session-start orientation
session-end update
scheduled tick interface
proactivity levels
permission matrix
atomic strategy playbook
candidate learning
basic strategy evaluation/rollback
OS write routing
Memory recall/write integration when installed
schema validation
doctor
QC tests for isolation/idempotency/concurrency
```

Advanced optimization algorithms can improve later without changing the object model.

---

# 70. Phase 4 implementation order

Recommended order:

```text
1. schemas + common object envelope
2. deterministic local state controller
3. authority / scope / write router
4. goals + practices
5. gap + opportunity + initiative engine
6. ranking + attention + proactivity policies
7. objective controller + completion contract
8. verification + evaluator abstraction
9. trigger/cadence interface
10. model beliefs + freshness
11. learning + strategy playbook
12. strategy eval + rollback
13. AI-Verse OS adapter
14. AI-Verse Memory adapter
15. standalone adapter
16. installer
17. doctor
18. test/eval suite
19. documentation
20. release QC
```

This order prevents UI or automation work from locking in a weak state model too early.

---

# 71. Phase 4 release gates

A release candidate should fail if any of these are true:

```text
Brain can silently create confirmed user goals from inference
Brain duplicates OS current state as competing truth
Brain creates its own general historical memory in native mode
cross-workspace access can occur silently
proactivity level grants undeclared side-effect authority
external content can modify privileged policy
completion can pass without evidence where evidence is required
stalled objectives retry forever
trigger replay causes duplicate effects
concurrent writes can silently overwrite state
strategy promotion has no rollback
core policy can self-modify
background cadence has no budget
user cannot disable proactivity
runtime deletion destroys canonical intent
installer creates standalone state inside native OS
```

---

# 72. Final architecture relationship

```text
                         AI-VERSE BRAIN

       Why?        Where are we going?       What next?
       │                  │                      │
       └──── Intent ──────┴──── Initiatives ─────┘
                              │
                    Cognition / Control
                              │
                Objectives • Progress • Verify
                              │
                     Learning / Evolution
                              │
               Strategy • Eval • Rollback
                              │
          ┌───────────────────┼───────────────────┐
          ▼                   ▼                   ▼
    AI-Verse OS        AI-Verse Memory        Host Runtime
    scope              history                model/tools
    current truth      recall                 execution
    capabilities       provenance             side effects
    connections        supersession           evaluation
    cadence engine
```

---

# 73. Final specification statement

AI-Verse Brain should not be defined by a branded seven-step prompt.

Its advantage should come from the architecture beneath the prompt:

- explicit desired-state direction;
- strict user authority;
- current-state freshness;
- falsifiable initiatives;
- capacity-aware prioritization;
- attention-aware proactivity;
- bounded objectives;
- adaptive cognition depth;
- 3Ms leverage analysis;
- 4Cs readiness and cadence maturity;
- deterministic lifecycle control;
- evidence-backed verification;
- independent evaluation when warranted;
- stall detection and replanning;
- epistemically staged learning;
- atomic strategy evolution;
- measurable self-improvement;
- regression checks and rollback;
- scoped write contracts;
- prompt-injection resistance at the authority layer;
- resource governance;
- concurrency and idempotency;
- graceful standalone operation;
- deep but non-duplicative integration with AI-Verse OS and AI-Verse Memory.

The Brain's job is not to maximize autonomous activity.

Its job is to create **reliable, evidence-backed progress toward user-approved desired states with the least unnecessary attention, risk, duplication, and wasted effort possible, while becoming measurably better at doing so over time.**

That is the standard Phase 4 implementation should be judged against.
