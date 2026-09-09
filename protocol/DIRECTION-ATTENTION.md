# Direction and Attention Protocol

This protocol defines how AI-Verse Brain discovers useful work without becoming an uncontrolled task generator or an annoying notification engine.

## Direction chain

```text
confirmed desired state
        +
canonical observed current state
        ↓
       GAP
        ↓
   OPPORTUNITY
        ↓
qualified candidate
        ↓
    INITIATIVE
        ↓
user/policy acceptance
        ↓
active portfolio
```

## Gap

A gap is Brain-owned interpretation, not current-state truth. It must reference both:

- desired-state refs;
- current-state refs.

It may record assumptions and unknowns. A gap can be resolved or invalidated when the underlying state changes.

## Opportunity

An opportunity is a hypothesis for reducing one or more active gaps. It carries confidence, optional mechanism, expiry, normalized score components, and a deterministic fingerprint.

The fingerprint binds scope + sorted gap refs + normalized semantic key. A reasoner may provide a deliberate `dedupe_key` for equivalent wording.

Before an opportunity is persisted/surfaced, the Brain checks:

- linked desired state;
- valid scope;
- permission compatibility;
- duplicate state;
- evidence freshness;
- minimum confidence;
- cooldown;
- hard boundaries.

Hard-gate failure beats score.

## Dedupe and cooldown

A matching active opportunity or initiative blocks duplication.

A user-dismissed opportunity, rejected initiative, or abandoned initiative creates a cooldown using canonical object state. The Brain may not bypass that cooldown by rephrasing the same proposal when the same semantic fingerprint/dedupe key is supplied.

Cooldown is a restraint, not a deletion of history.

## Initiative

An initiative must be traceable to a qualified opportunity and active gaps. The initiative's score components must match the qualified source opportunity at creation so it cannot silently inflate its own priority during promotion.

Proposed initiatives remain proposals. Accepting an initiative is distinct from discovering one.

Active initiative WIP is capped by policy.

## Ranking

Ranking is inspectable. Positive factors include goal alignment, expected impact, urgency, confidence, strategic leverage, 4C readiness, and reversibility. Costs include effort, attention, risk, and opportunity cost.

No ranking formula can override a failed hard gate.

## Notification classes

```text
INTERRUPT  urgent/high-value proactive interruption
SURFACE    normal proactive surfacing
BATCH      defer to a digest/docket
STORE      retain without user interruption
DROP       ineligible for surfacing
```

The notification class is not execution authority.

## Proactivity levels

```text
P0 REACTIVE   no unsolicited surfacing
P1 OBSERVANT  observe/store, do not unsolicited-surface
P2 ADVISORY   proactively surface useful proposals
P3 ASSISTIVE  may prepare more work, still subject to action permissions
P4 DELEGATED  broad proactive operation only inside separately granted permissions
```

Moving from P2 to P4 does not grant send/publish/spend/delete/deploy permissions.

## Attention budget

The disposable Attention Ledger enforces:

- fingerprint notification cooldown;
- per-session proactive item cap;
- per-day interruption cap;
- bounded retention of delivery bookkeeping.

If an item qualifies as `INTERRUPT` after the interruption budget is exhausted, it is downgraded to `SURFACE` rather than repeatedly interrupting or silently disappearing.

Canonical dismissal/rejection remains on Brain objects; the delivery ledger is disposable.
