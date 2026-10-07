# Purpose Strategic Intent Contract

**Status:** IN PROGRESS — Purpose Context Slice 3.2

AI-Verse Brain represents Purpose v1 `problem`, `mission`, and strategic `strategy` as subtypes of the existing canonical `intent` object. They do not create new object kinds and `strategy` is not the self-learning `strategy_rule` object.

## Canonical subtypes

- `intent:problem`
- `intent:mission`
- `intent:strategy`

Each uses the existing Intent payload contract: required `subtype` and non-empty `statement`, plus only the already-supported optional Intent fields unless a later reviewed contract adds more.

## Lifecycle/status rules

The three Purpose strategic intent subtypes use the existing Intent lifecycle unchanged:

```text
DRAFT
  -> PROPOSED
      -> CONFIRMED
          -> ACTIVE
              -> PAUSED
                  -> ACTIVE
              -> ACHIEVED
              -> ABANDONED
              -> SUPERSEDED
          -> ABANDONED
          -> SUPERSEDED
      -> ABANDONED
```

Canonical transition set is therefore exactly the existing Brain Intent state machine:

- `DRAFT -> PROPOSED`
- `PROPOSED -> CONFIRMED | ABANDONED`
- `CONFIRMED -> ACTIVE | ABANDONED | SUPERSEDED`
- `ACTIVE -> PAUSED | ACHIEVED | ABANDONED | SUPERSEDED`
- `PAUSED -> ACTIVE | ABANDONED | SUPERSEDED`
- `ACHIEVED`, `ABANDONED`, and `SUPERSEDED` are terminal.

Purpose-specific meaning does not introduce extra statuses:

- `DRAFT` / `PROPOSED` are not current confirmed strategic truth and are excluded from the Purpose snapshot.
- `CONFIRMED`, `ACTIVE`, and `PAUSED` are current strategic states eligible for the Purpose snapshot while Brain owns direction for the exact scope.
- `ACHIEVED`, `ABANDONED`, and `SUPERSEDED` remain historical/non-current and are excluded from current Purpose truth, though owner history/provenance may reference them when relevant.

## Lifecycle laws

1. Purpose does not create a parallel mission/problem/strategy lifecycle.
2. The generic Brain Intent state machine remains the sole lifecycle authority for these subtypes.
3. A Purpose read never changes lifecycle state.
4. `PAUSED` remains current known strategic intent but is explicitly paused; Purpose must not render it as active execution.
5. Terminal records are never silently revived; a replacement requires normal canonical mutation/supersession rules.
6. Status semantics are identical in operator and workspace scopes; scope changes do not copy or transfer a strategic intent.

## NEXT

Define the confirmation/authority requirements for these privileged strategic intent subtypes before accepting them as confirmed/current direction.
