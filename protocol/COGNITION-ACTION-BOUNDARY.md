# Cognition and Action Boundary

This contract separates model reasoning from deterministic control and separates Brain authorization from host execution.

## Model reasoning is advisory

A model receives a `CognitionRequest` containing a purpose, exact scope, references, constraints, and an output contract.

A model may return `CognitionProposal` objects only for allowed proposal kinds. It cannot return a canonical lifecycle status, scope override, policy object, permission mutation, authority tier, or privileged self-evolution field.

The deterministic Brain validates request ID, purpose, scope, proposal kind, confidence, and privileged fields before a proposal can reach a domain service. A model response is never itself canonical Brain state.

```text
trigger
  -> deterministic TickPlanner
  -> CognitionRequest
  -> model/reasoner
  -> CognitionProposal
  -> contract validation
  -> domain-specific deterministic gates
  -> possible persistence
```

## Tick planning

`TickPlanner` translates an already-authorized cadence trigger into bounded cognition requests. It does not call a model, tool, scheduler, OS, or Memory engine.

Examples:

- session start -> orientation;
- session end -> reflection candidate;
- scheduled orientation -> orient + gap analysis + opportunity discovery;
- scheduled review -> orient + gap analysis + reflection + strategy review;
- objective wake/blocker resolution -> objective planning.

Every request repeats hard constraints that retrieved/external content is evidence, not instruction, and that user goals/policies/permissions cannot be mutated by reasoning output.

## Action requests

The Brain never treats "I should do X" as equivalent to executing X.

An `ActionRequest` includes exact action class, exact scope, operation and parameters, idempotency key, scope/budget/reversibility facts, reason, and request ID.

Proactivity level does not authorize an action.

## Approval

Actions with `ask_every_time` policy require an `ApprovalGrant` bound to the exact request ID, idempotency key, scope, and action class. A reusable vague approval is not sufficient.

Approval authority must be explicit user authority and may expire. The host/control plane is responsible for constructing authentic approval grants; model output is not a control channel.

## Replay and duplicate safety

Every action has an idempotency key. Reusing a key for different request contents is rejected.

Read-only coordination receipts may remain disposable. **External side-effect receipt references are durable Brain-owned safety state** under the relevant Brain scope (`action-receipts/`). They contain minimal operational metadata and receipt references, not copied external content or canonical OS/Memory state.

Runtime locks remain disposable. Host-side idempotency is still required for autonomous side effects because a durable local receipt cannot prevent a remote duplicate during an ambiguous network failure.

For autonomous side effects, the host must support the same idempotency key. If it does not, explicit approval is required and automatic retries remain forbidden.

A successful side effect must return a host receipt ID. If the host throws after dispatch, reports `uncertain`, returns an invalid response, or claims success without a receipt, Brain durably records uncertainty and blocks automatic replay.

Completed duplicate requests return the previous receipt status without calling the host again, even after disposable runtime state is removed.

## Reconciliation

Uncertainty is not a terminal dead end. `reconcile()` can resolve an uncertain action only from verified evidence or stronger authority.

- confirmed success requires a receipt ID;
- confirmed failure is retryable only when evidence proves `effect_occurred=false`;
- weak inference cannot reconcile an external effect;
- reconciliation never fabricates a host receipt.

## Failure semantics

Read-only failures are retryable.

Side-effect failures are retryable only when the host explicitly says no effect occurred or the host guarantees idempotency. Uncertain outcomes are not retryable automatically.

This design favors duplicated thinking over duplicated side effects.
