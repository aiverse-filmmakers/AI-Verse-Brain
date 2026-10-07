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

Canonical transition set is exactly the existing Brain Intent state machine:

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

## Confirmation / authority rules

`problem`, `mission`, and strategic `strategy` are privileged strategic intent subtypes.

They inherit the existing Brain Intent confirmation gate unchanged:

- creating an Intent directly as `CONFIRMED` requires `assert_goal_confirmation` authority;
- transitioning `PROPOSED -> CONFIRMED` requires the same gate;
- the current Brain gate accepts only explicit-user authority or the stronger host hard-constraint tier; model hypotheses, validated strategy, derived model state, verified evidence, canonical scoped state, and external data cannot independently confirm these strategic intents;
- external data cannot directly create Brain control state or drive lifecycle transitions;
- in native AI-Verse mode, Brain may confirm/write strategic Intent only when Brain is the active direction owner for that exact scope; OS-owned direction requires explicit handover first.

Purpose-specific laws:

1. An LLM may propose a problem, mission, or strategy as non-confirmed candidate intent, but it cannot promote it into current Purpose truth on its own.
2. Purpose snapshot eligibility begins only at the existing confirmed/current states (`CONFIRMED`, `ACTIVE`, `PAUSED`).
3. Seeing, deriving, or explaining a Purpose trajectory grants no mutation authority.
4. A cross-scope relation grants no authority to confirm or change the referenced scope's strategic intent.
5. The `PRIVILEGED_INTENT_FIELDS` registry includes `problem`, `mission`, and `strategy` so future privileged-field/self-evolution checks treat them as strategic, not ordinary model state.
6. No special lower-authority shortcut exists for strategy merely because Brain also has `strategy_rule`; the two semantics remain separate.

## Supersession and versioning

Purpose uses Brain's existing object identity and revision model; it does not create a second version system.

- The canonical version of an owner-backed strategic intent is the existing `BrainObject.revision` for its stable object `id`.
- An in-place edit of the same canonical object increments/changes that object's revision through the existing owner write path. Purpose canonical refs therefore keep the same `(owner, scope, kind, id)` and expose the observed revision as `version`.
- A semantically replacement intent is a different canonical object and may carry the existing `supersedes` / `superseded_by` linkage. Replacement is explicit; timestamp order, storage order, text similarity, or "latest record" heuristics never imply supersession.
- A valid Purpose supersession link must stay inside the same exact scope and the same strategic intent subtype. `mission` cannot silently supersede `problem`, `strategy` cannot supersede `mission`, and operator/workspace records cannot supersede one another.
- Superseded strategic intents transition through the existing terminal `SUPERSEDED` state and are excluded from current Purpose truth. They remain historical canonical records; Purpose must not delete or rewrite them.
- No singleton assumption is introduced. Multiple current problems, missions, or strategies may coexist when canonically confirmed. Supersession identifies a replacement chain; it is not a uniqueness rule.
- A broken, cross-scope, cross-subtype, circular, or otherwise unverifiable supersession link is not authoritative Purpose truth. The read surface must reject or expose it as invalid/partial rather than guessing a replacement.
- Creating a candidate that declares `supersedes` does not itself retire the prior record. The prior record remains current until the canonical lifecycle mutation marks it `SUPERSEDED` under the normal strategic owner and authority rules.
- Replacing already-confirmed strategic intent is a material strategic mutation. The eventual mutation path must require the same explicit-user-level authority used for privileged strategic confirmation; a derived Purpose projection cannot authorize it.

### Purpose read law

Purpose resolves current strategic truth from canonical lifecycle state plus exact observed revision. It never chooses a winner merely because one object has a higher revision, newer timestamp, or a `supersedes` pointer whose counterpart was not canonically superseded.

## No silent migration / reinterpretation

Adding the new subtype vocabulary changes what future canonical writes may express; it does not change the meaning of any existing record.

1. Existing `intent:desired_state`, `intent:goal`, `intent:boundary`, `intent:constraint`, and `intent:success_definition` records keep their original subtype and semantics.
2. Canonical `goal` objects remain goals. They are not converted into `intent:mission`, `intent:problem`, or `intent:strategy` based on wording, hierarchy, age, or model judgment.
3. `strategy_rule` remains the controlled self-learning strategy-rule object. It is never reclassified as strategic `intent:strategy` merely because its text appears strategic.
4. OS profile/current-context Markdown, generated direction views, Memory history, Data records, and external source text are not silently imported into the new Brain subtypes.
5. Loading, reading, upgrading package code, rebuilding a Purpose projection, installing Purpose support, or changing direction owner performs no subtype rewrite and creates no new strategic intent.
6. Historical objects whose text resembles a problem/mission/strategy remain historical objects of their original kind/subtype until an explicit owner-routed canonical mutation or migration is requested and authorized.
7. A future migration tool, if ever introduced, must be explicit, previewable, scope-bound, idempotent, provenance-preserving, and confirmation-bound for privileged strategic intent. No such migration is part of Purpose v1 Slice 3.2.
8. Purpose snapshot classification is exact-subtype based. It must not infer `problem`, `mission`, or `strategy` from free text, source filenames, generated views, or neighboring records.

### Compatibility law

Repositories containing only pre-Purpose Brain objects remain valid. The absence of the new subtypes means the corresponding Purpose sections are canonically empty/absent according to the read contract; it is never an instruction to synthesize them.

## NEXT

Add exhaustive unit coverage for subtype validation, lifecycle/authority, exact-scope ownership, current snapshot classification, supersession semantics, and no-silent-migration compatibility before closing Slice 3.2.
