# Skills Receipt and Brain Verification Boundary

This protocol defines how Brain consumes `aiverse-execution-receipt-v2` without confusing execution accounting with verified objective completion.

## Two separate decisions

A Skills receipt can feed two independent Brain paths:

1. **Action outcome translation** — `translate_action_receipt(...)` converts the Skills execution status and effect certainty into Brain's `succeeded / failed / uncertain` host-response contract.
2. **Objective verification** — `evaluation_from_receipt(...)` maps criterion-addressed evidence into Brain `CriterionVerdict` objects and an `EvaluationResult`.

A successful action outcome never closes an objective by itself.

## Exact identity binding

Brain independently requires the receipt to match the current action's:

- immutable `request_fingerprint`;
- scope;
- action class;
- operation.

The caller must also supply the capability identity selected for this execution:

- provider `aiverse-skills`;
- qualified capability ID;
- immutable generation ID;
- package SHA-256 digest using `aiverse-package-sha256-v1`.

A stale generation, different capability, changed package digest, or different action fingerprint is rejected before the receipt can be interpreted.

For completed actions, the public `ActionExecutor` retains this bounded `execution_binding` inside the durable action receipt ledger. Replay therefore keeps the immutable capability identity associated with the completed action.

## Execution status mapping

Brain does not map Skills strings by name alone.

| Skills status | Effect state | Brain action status |
| --- | --- | --- |
| `success` | valid success effect | `succeeded` |
| non-success | `not_occurred` | `failed` |
| non-success | `occurred` or `uncertain` | `uncertain` |

`uncertain` uses Brain's existing no-blind-retry behavior for side effects.

For a successful side-effect receipt, `effect.state` must be `occurred` and the effect source must be `ai_verse_os`. A skill runtime cannot self-certify an external effect and have Brain treat it as successful.

`trace_id` is correlation metadata only. It cannot substitute for the stable `receipt_id` and cannot be used as criterion evidence.

## Evidence provenance

Receipt evidence never supplies a raw Brain evidence-class label. Brain derives the class from evidence kind plus source provenance:

| Receipt evidence | Provenance | Brain class |
| --- | --- | --- |
| observation | skill runtime or OS | `SINGLE_OBSERVATION` |
| measurement | OS | `DIRECT_MEASUREMENT` |
| canonical state | OS | `CANONICAL_STATE` |
| user confirmation | user | `USER_CONFIRMATION` |
| authoritative external | external authority | `AUTHORITATIVE_EXTERNAL` |
| independent evaluation | independent evaluator | `INDEPENDENT_EVALUATION` |

Unsupported pairings fail closed. The skill runtime therefore cannot label its own observation as direct measurement, canonical state, authoritative external evidence, or independent evaluation.

Receipt-derived `EvidenceRef` objects preserve `source_kind`, `source_ref`, and `independence` in addition to the existing evidence reference, claim, scope, timestamps, and integrity fields. Those provenance fields are optional for legacy Brain evidence and required by the Skills receipt bridge.

## Criterion and independence rules

Receipt verdicts must name actual criterion IDs on the target Brain objective. Unknown IDs are rejected rather than ignored.

The receipt's verification context must satisfy its declared independence. For `fresh_context`, builder and evaluator context IDs are required and must differ. A passed criterion must contain evidence capable of supporting the declared independence level.

Brain then applies its existing V0–V3 evaluator rules. In particular:

- V1+ cannot pass on model inference alone;
- V2/V3 require strong evidence for passed criteria;
- V2 requires at least fresh-context evaluation;
- V3 requires an independent model/evaluator or authoritative external verification.

## Completion authority

`evaluation_from_receipt(...)` is read-only with respect to the objective. It only constructs and validates an `EvaluationResult`.

`apply_receipt_to_objective(...)` is a convenience path owned by Brain and delegates final state changes to the existing `EvaluationService.apply_to_objective(...)`.

Therefore:

- Skills does not mark a Brain objective complete;
- a receipt saying `success` does not mark a Brain objective complete;
- a trace or receipt ID is not verification proof;
- missing criterion evidence becomes insufficient evidence;
- only Brain's evaluator can transition a `VERIFYING` objective to `PASSED` after all required criteria and verification floors are satisfied.
