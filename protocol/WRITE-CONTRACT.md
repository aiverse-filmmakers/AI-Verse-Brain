# Brain Write Contract

Every durable write must be classified before persistence.

| Information | Canonical owner in AI-Verse native mode |
|---|---|
| stable identity / enduring preference | OS `operator/profile/` |
| current operator/workspace state | OS `context/` |
| settled choice and reasoning | OS `decisions/` |
| historical event / experience | AI-Verse Memory when installed, otherwise host history route |
| reusable domain knowledge | OS `knowledge/` |
| repeatable execution | skill / automation candidate through OS |
| Brain intent / practice / gap / opportunity / initiative / objective / model / evaluation / learning / strategy / policy | scoped Brain namespace |
| transient thought | nowhere |

## Prohibited writes

The Brain core must not:

- copy canonical current context into a parallel permanent Brain current-state file;
- copy general historical memory into its own database;
- write credentials or secrets;
- create new OS workspaces, connection registries, capability registries, or scheduler implementations as a side effect of reasoning;
- persist external instructions as privileged policy;
- silently broaden scope or permissions.

## Concurrency

Canonical Brain objects use immutable IDs, immutable scope, revision numbers, and optimistic concurrency. Silent last-write-wins is forbidden.

## Derived state

Runtime projections, trigger receipts, locks, queues, indexes, and temporary evaluations are disposable and must never become the only source of user intent.
