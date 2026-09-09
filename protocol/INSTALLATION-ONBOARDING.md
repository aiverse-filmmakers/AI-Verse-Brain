# Installation and Onboarding Contract

This protocol defines the shipment boundary for initializing AI-Verse Brain and capturing its first user-authorized intent.

## Installation ownership

Brain installation may create only Brain-owned paths.

Standalone:

- `.ai-verse-brain/`
- `.ai-verse-brain/runtime/`
- `.ai-verse-brain/installation.json`

AI-Verse OS v2 native mode:

- `operator/brain/`
- `runtime/ai-verse-brain/`
- `operator/brain/installation.json`

Workspace Brain state is created lazily under `workspaces/<id>/brain/` when a valid scoped Brain write occurs.

The installer MUST NOT:

- patch `AI-VERSE.yaml`;
- create a standalone `.ai-verse-brain` store inside a compatible AI-Verse host;
- copy AI-Verse Memory state or implementation;
- write operator profile, OS current context, decisions, knowledge, connections, secrets, capabilities, or scheduler state;
- silently fall back to standalone mode when an incompatible `AI-VERSE.yaml` is present.

## Dry-run first

`ai-verse-brain init` is read-only and emits an installation plan.

Mutation requires:

```bash
ai-verse-brain init --apply
```

The applied operation is idempotent. Re-running it on a valid installation preserves the original installation identity and user Brain state.

## AI-Verse native prerequisite

Native initialization requires a compatible AI-Verse OS v2 unified-workspace host and an existing `extensions.brain` registration slot.

If the slot is absent, initialization fails closed. The Brain installer reports the blocker but does not edit the OS manifest.

## Version safety

`installation.json` stores both an installation-marker schema version and a Brain state schema version.

The package refuses to operate through initialization when:

- the state schema is newer than the installed package supports;
- the state schema is older and no explicit migration has been applied;
- the stored host mode no longer matches the detected host mode;
- the marker is malformed.

There is no destructive implicit migration path.

## Onboarding ownership

Onboarding captures only Brain-owned intent and practice state from explicit user input:

- desired state;
- success definition;
- concrete goals;
- boundaries;
- constraints;
- ongoing practices.

It does NOT copy or take ownership of:

- current-state/profile facts;
- historical memory;
- reusable knowledge;
- capabilities;
- connections;
- scheduler configuration.

Those remain host/OS/Memory responsibilities.

## Explicit authority

Only answers supplied through an explicit onboarding apply operation may become `CONFIRMED` intent/practice objects.

The Brain may ask for missing intent, but it may not infer a desired state, success definition, goal, boundary, or constraint into confirmed user intent.

The minimum orientation-ready onboarding state is:

1. at least one confirmed `desired_state`;
2. at least one confirmed `success_definition`.

Everything else may be added progressively.

## Adaptive onboarding

Onboarding is not a fixed questionnaire. It asks only for missing primitives. If confirmed state already exists, that question disappears.

Re-applying identical answers is idempotent and does not create duplicate canonical intent objects.

## Doctor

`ai-verse-brain doctor` remains read-only. It validates:

- host compatibility;
- parallel-store risk;
- installation marker integrity;
- supported state schema;
- scope/kind integrity;
- presence of the minimum explicit intent needed for orientation.

Warnings do not mutate or repair user state automatically.
