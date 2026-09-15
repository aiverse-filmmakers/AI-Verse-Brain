# H1 Retrieval-Intent Envelope Evaluation

Status: **REJECTED FOR CURRENT ARCHITECTURE**

Date: 2026-09-15

## Decision

Do not add an explicit Brain-owned `orientation / summary / detail / exact_evidence` retrieval-intent envelope at this time.

H1 is a ship/reject gate. The current architecture already has a clean division of responsibility:

- Brain decides whether a cognition purpose needs historical evidence and builds a bounded semantic query from the actual task and canonical context.
- Gateway G1 decides how far to descend automatically through the accepted Context Ladder.
- Gateway G2 gives the foreground runtime one bounded read-only mechanism for deeper summary/detail/source retrieval.
- OS/Memory own the progressive retrieval implementation and source validation.

Adding a Brain depth envelope now would duplicate retrieval planning without a supported Brain transport path to the progressive API.

## Current Brain behavior

Brain's `ContextAssembler` currently retrieves history only for:

- `gap_analysis`
- `reflection`
- `strategy_review`
- `evaluation`

It does not retrieve history for:

- `orient`
- `opportunity_discovery`
- `objective_planning`

That binary history-needed decision is deterministic and matches the current cognition-purpose contract.

When history is needed, Brain constructs a semantic query from the purpose plus current host context, scoped Brain state, context refs, and evidence refs. The query therefore carries task-specific cues instead of sending an internal purpose token.

## Benchmark

The executable H1 benchmark covers eight history scenarios across all four history-bearing cognition purposes.

Each purpose has two cases requiring different accepted Context-Ladder depths:

| Brain purpose | Scenario A | Scenario B |
| --- | --- | --- |
| gap_analysis | summary | detail |
| reflection | summary | detail |
| strategy_review | summary | source |
| evaluation | summary | source |

Measured results:

- binary "history needed?" accuracy from current purpose gate: **100%**
- preservation of depth-sensitive semantic cues in current Brain queries: **100%**
- best possible static purpose-to-depth mapping accuracy: **50%**
- Brain progressive-depth transport available today: **no**
- observable host effect from a Brain-only envelope: **0**

The 50% result is structural, not model quality. The same cognition purpose can legitimately require different retrieval depths depending on the actual task.

## Why a dynamic Brain envelope is also rejected

A dynamic envelope could only improve on the 50% static ceiling if Brain added another depth planner that inspected task language/context and decided summary/detail/source itself.

That would duplicate the accepted Gateway G1/G2 retrieval-planning layer.

It would also require extending the Brain host protocol. Today both the Brain HostAdapter and BridgeHostAdapter expose:

`retrieve_history(query, scope)`

There is no Brain `retrieve_history_progressive` method and no depth parameter on the required host read contract.

OS does expose a separate progressive Memory operation, but that operation is already consumed by Gateway G1/G2.

Therefore a Brain-only declarative field would have no current consumer. Making it effective would require coordinated Brain + bridge + OS changes and would create two components that can decide retrieval depth.

## Ownership consequence

Brain should continue owning:

- cognition purpose
- semantic retrieval query formation
- reasoning goals and strategy
- evaluation intent

Brain should not become a second owner of:

- Memory retrieval depth
- exact-source descent
- retrieval loop budgets
- per-run retrieval caching
- scope-bound source validation

Those are already owned by Gateway/OS/Memory.

## Revisit condition

Re-open H1 only if a future runtime needs Brain-originated retrieval intent that cannot be inferred from the semantic query and cannot be expressed through the existing Gateway G1/G2 path.

A future proposal must show measurable improvement over the current baseline and must preserve one canonical retrieval-depth authority.

Until then the correct H1 outcome is **reject, documented and tested**.
