# Host and Brain Permission Intersection

AI-Verse Brain never treats its own action policy as sufficient authority for a host effect.

For every new action dispatch, effective permission is the intersection of two independent controls:

1. **Brain policy** — action class, scope, budget, reversibility, approval, replay safety, and persisted effective policy.
2. **Selected host permission** — the host/OS permission envelope for the exact immutable action request.

The stricter result wins. A host can restrict Brain, but cannot grant Brain authority that Brain policy denies.

## Host operation

Execution-capable hosts implement `authorize_action` before `request_action`.

Brain sends the normal immutable action request plus its canonical `request_fingerprint`. The host returns exactly:

```json
{
  "decision": "allow",
  "request_fingerprint": "<same sha256>",
  "scope": "workspace:example",
  "action_class": "send_message",
  "source": "os:workspace-policy",
  "reason": "workspace external_actions policy"
}
```

`decision` is one of:

- `allow`
- `approval_required`
- `deny`

The response is valid only when its fingerprint, scope, and action class match the exact request.

## Intersection rules

- Brain deny + host allow = denied.
- Brain allow + host deny = denied.
- Brain allow + host approval_required = exact explicit-user approval required.
- Brain approval_required + host allow = exact explicit-user approval required.
- Both allow = allowed only if all other Brain execution gates pass.
- Missing, malformed, stale, mismatched, or failing host permission checks = denied.

A host permission result is **not** an `ApprovalGrant`. The host cannot manufacture user approval. Exact approvals remain Brain-owned security inputs and are bound to the immutable action fingerprint.

## Time-of-check / time-of-use

Host permission is checked before the core creates a claimed dispatch record and checked again immediately at the `request_action` edge. If the second check becomes more restrictive, Brain does not call the external executor.

A late permission revocation is recorded as a safe failed attempt with `effect_occurred: false`; it is not classified as an uncertain external side effect because dispatch never happened.

## Replay behavior

Existing receipt/idempotency rules remain authoritative. Permission intersection does not make a failed or uncertain external outcome safe to retry and does not treat a trace identifier as proof of effect.

Receipt normalization and verification-evidence semantics are a separate contract and are intentionally not defined here.
