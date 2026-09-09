# Runtime Pipeline Contract

Status: Phase 4 alpha.5.

This contract defines how AI-Verse Brain may connect bounded model reasoning to deterministic Brain state without turning the model into an authority source or execution engine.

## Pipeline

```text
Trigger
  -> deterministic orientation
  -> bounded ephemeral host context
  -> ReasonerAdapter
  -> strict raw-output parser
  -> CognitionProposal
  -> deterministic ProposalApplier
  -> Brain state
  -> attention decision
  -> surface item for host/UI
```

External action execution is deliberately outside this automatic pipeline.

## ReasonerAdapter

A reasoner adapter exposes a stable `model_id` and a single reasoning call. It receives a `CognitionRequest` plus an ephemeral `ContextBundle`.

The adapter has no direct Brain store handle, no policy mutation handle, no action executor, and no scheduler ownership.

Raw output may be either `{"proposals": []}` or a bare proposal array.

Each proposal may contain only `proposal_kind`, `payload`, `confidence`, and optional `rationale`. The runtime binds request ID, purpose, scope, and source model itself. A model cannot self-assign those control fields.

## Ephemeral context

`ContextAssembler` may read current host context, bounded history, bounded capability metadata, bounded connection metadata, and scoped canonical Brain objects relevant to the cognition purpose.

Host/retrieved content remains data. It is not copied into canonical Brain state merely because a model saw it, and it cannot redefine goals, permissions, policies, privacy, scope, or authority.

## Deterministic proposal application

The ProposalApplier owns the mapping from proposal kinds to Brain operations.

### Gap

A gap may be created only with explicit desired/current references and an interpretation. Exact active duplicates are reused.

### Opportunity

Opportunity scores are advisory estimates. Confidence is bound to the proposal envelope. Deterministic gates still check active gaps, desired-state linkage, evidence freshness, minimum confidence, dedupe, cooldown, and hard boundaries.

Eligible opportunities may become `QUALIFIED`; model output cannot set that status directly.

### Initiative

An initiative must consume an existing `QUALIFIED` opportunity. It inherits the qualified opportunity's score components rather than replacing them with new model-provided scores. It starts as a proposal and still requires the normal acceptance lifecycle.

### Objective

A model-created objective must serve either a confirmed/active intent or an accepted/active initiative.

The model may describe criteria but may not provide criterion pass/fail state or evidence. Every criterion starts `unverified`.

Verification has a deterministic floor of V1. Model-requested attempt and stall budgets are capped by Brain policy and can never expand those limits.

### Derived model belief

Model-created beliefs are forced to `inferred`, confidence is taken from the bounded proposal envelope, and freshness windows are capped by deterministic domain limits.

### Learning

A reflection proposal requires basis references that were actually present in the bounded cognition request. Runtime-created evidence is classified as `MODEL_INFERENCE`, so reflection begins only as `OBSERVATION` and cannot count as independent evidence for self-validation.

## Attention and delivery

Proposal application may produce a notification class. Attention policy then applies cooldown, per-session limits, daily interruption budgets, and proactivity level.

`BrainRuntime` returns approved `surface_items`.

It does not call `host.notify_user` automatically. Actual UI/push/message delivery belongs to the host and remains separately governed.

## Actions

Cognition proposals cannot become `ActionRequest` objects implicitly.

External effects use the explicit ActionExecutor path, preserving action-class policy, exact approval binding when required, scope and budget checks, idempotency, durable receipt references, no automatic retry after uncertain side effects, and evidence-backed reconciliation.

## Trigger transaction

`BrainRuntime` claims the trigger before orientation and marks it completed only after the bounded cognition/application pass finishes.

Model and proposal errors are recorded as bounded runtime results rather than causing automatic replay.

A process crash leaves the trigger `claimed`; stale-claim recovery must be explicit. The Brain never guesses that a partially processed tick is safe to replay.

## Repository boundary

This runtime contract lives entirely in `AI-Verse-Brain`.

It does not install into, copy, merge with, or mutate AI-Verse OS or AI-Verse Memory.
