# Learning, Belief Freshness, and Evolution Protocol

AI-Verse Brain separates observation, belief, learning, and strategy so a single model inference cannot rewrite the agent's operating doctrine.

## Derived belief model

A `model_belief` belongs to one of:

- user model;
- agent model;
- world model.

It records statement, epistemic state, confidence, evidence, observation time, optional expiry, optional maximum age, last review, and contradiction refs.

Epistemic states include:

```text
known
inferred
assumed
unknown
contradicted
stale
```

A derived model is never equivalent to explicit user intent.

## Freshness

Beliefs can become stale because:

- explicit expiry is reached;
- maximum age is exceeded;
- all supporting expiring evidence has expired;
- contradiction evidence arrives.

A stale/contradicted belief cannot silently be treated as current truth.

Contradicted beliefs require verified evidence or stronger authority to reactivate.

## Learning lifecycle

```text
OBSERVATION
  -> HYPOTHESIS
  -> PATTERN
  -> REFLECTION
  -> VALIDATED_LEARNING
  -> STRATEGY_CANDIDATE
  -> PROMOTED or REJECTED
```

A PATTERN requires repeated independent observations or explicit user confirmation.

VALIDATED_LEARNING requires no unresolved contradiction and at least one controlled evaluation, three independent observations, or explicit user confirmation.

External data cannot directly drive learning lifecycle transitions; it must be interpreted as evidence first.

`USER_CONFIRMATION` evidence may only be asserted under explicit user authority.

## Causality

Observed success is not automatically causal proof. Learning records evidence strength separately from causal claim.

Supported evidence-strength concepts include single observation, corroborated, controlled, and user-confirmed.

A strategy should not claim causality merely because it was present when an outcome improved.

## Strategy tiers

```text
E0  ephemeral tactic, never canonical-promoted
E1  local low-risk strategy rule
E2  broader strategy with stronger impact/scope
E3  core Brain behavior/code
E4  privileged authority/policy boundary
```

E1 activation requires the configured minimum number of evaluations plus `regression_passed=true`. Automatic E1 promotion is policy-controlled.

E2 activation requires stronger evaluation and, by default, explicit user approval.

E3 and E4 cannot be activated through runtime Brain state. E3 changes must go through tested code/review/PR-style promotion. E4 remains privileged authority policy.

## Monitoring and rollback

Active strategy rules accumulate helpful/harmful evidence and evaluation refs. Regression failure or harmful evidence can justify retirement or rollback according to policy.

Self-improvement never grants itself a higher evolution tier or permission class.
