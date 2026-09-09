# Action, Progress, and Verification Protocol

The Action Loop keeps an agent working toward a bounded outcome without confusing activity with progress or self-declaring success.

## Objective contract

An objective is a bounded outcome. It may contain problem, desired state, criteria, constraints, boundaries, risks, dependencies, stop conditions, verification level, and budget.

Every material criterion begins `unverified`.

## Progress states

Brain distinguishes at least:

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

Objective lifecycle status and progress interpretation are separate fields.

## Attempt observation

An attempt records a state token representing criterion-relevant observed state, plus evidence refs and an optional blocker.

Rules:

- first observation establishes baseline;
- repeating the same state is not progress;
- changing the state without evidence is not meaningful progress;
- changed state + evidence can reset the non-progress counter;
- external blocker moves the objective to BLOCKED;
- exhausting `max_attempts` moves the objective to BLOCKED rather than silently increasing the budget;
- repeated non-progress moves the objective to STALLED.

The agent must replan, wait, request help, or stop according to state. `not finished` is never equivalent to `keep trying forever`.

## Parallelism

The controller enforces a policy cap on simultaneously active objectives. This prevents long-horizon agents from multiplying work until attention and resources collapse.

## Verification levels

```text
V0  trivial / low consequence
V1  normal material work
V2  important work requiring stronger evidence and at least fresh-context evaluation
V3  high-impact work requiring independent model/evaluator or authoritative external verification
```

The selected evaluation level may equal or exceed the objective's floor, never fall below it.

## Evaluator independence

```text
same_context
fresh_context
independent_model
external_authoritative
```

V2 requires at least `fresh_context`.

V3 requires at least `independent_model` or `external_authoritative`.

Fresh-context evaluation records both builder and evaluator context IDs and they must differ.

## Criterion evidence

A passed criterion requires evidence refs.

For V1+, model inference alone cannot pass a criterion.

For V2/V3, a passed criterion needs strong evidence such as user confirmation, canonical state, direct measurement, authoritative external evidence, or independent evaluation.

Missing criterion verdicts become `insufficient_evidence`.

## Completion

An objective can reach `PASSED` only when:

- at least one criterion passes;
- every material criterion is passed or explicitly not applicable;
- every passed criterion has evidence;
- required verification independence is satisfied.

Otherwise the deterministic result is `FAILED` or `INSUFFICIENT_EVIDENCE`.

The builder does not gain authority by writing "done" in prose.
