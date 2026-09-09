# AI-Verse Brain Write Contract

Every durable write has exactly one canonical owner.

## Brain-owned

Brain may canonically own:

- intent objects it is authorized to hold;
- practices;
- gaps;
- opportunities;
- initiatives;
- objectives;
- derived model beliefs;
- evaluations;
- learning objects;
- strategy rules;
- Brain policy objects created/changed only with required user authority.

In native AI-Verse mode these live only under `operator/brain/` or `workspaces/<id>/brain/`.

## Not Brain-owned

Brain must route rather than duplicate:

```text
stable identity / enduring preference -> OS profile
current canonical state             -> OS context
settled decision                     -> OS decisions
historical event / experience        -> Memory history
reusable domain knowledge            -> OS knowledge
repeatable execution                 -> capability/skill candidate
transient thought                     -> no durable canonical write
```

Brain does not create a parallel copy after routing a write elsewhere.

## Runtime-only state

The following may exist under Brain runtime storage and are disposable:

- object locks;
- trigger receipts;
- direction coordination locks;
- attention delivery/cooldown ledger;
- temporary queues/projections/checkpoints that can be reconstructed.

Runtime state is not allowed to become the only record of user intent, initiative acceptance, objective completion, dismissal, rejection, learning, or policy.

## Native mode rule

Compatible AI-Verse native mode uses the OS's existing operator/workspace boundaries. Brain does not modify workspace identity, OS context, Memory history, scheduler implementation, capabilities, connections, or secrets as part of its own canonical state.

## Standalone rule

Standalone mode stores Brain-owned state under `.ai-verse-brain/`. Host adapters may map external context/history providers but may not redefine Brain-owned objects into a second OS or memory hierarchy.
