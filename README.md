# AI-Verse Brain

**A universal intelligence layer for AI agents: persistent intent, goals, initiative, planning, reflection, verification, learning, and controlled self-improvement.**

AI-Verse Brain is designed to work with capable agents on its own and to integrate deeply with AI-Verse OS and AI-Verse Memory without becoming either of them.

> Status: **Phase 5 alpha (`0.1.0-alpha.7`)**. The deterministic intelligence foundation is merged to `main`; this branch is adding shipment/installability. Development remains inside `AI-Verse-Brain`. Nothing in this work has been installed into or merged with AI-Verse OS or AI-Verse Memory.

## Responsibility split

```text
Brain  = why / where / what next / how to verify / how to improve
OS     = structure / scope / routing / capabilities / connections / execution boundaries
Memory = historical recall / provenance / supersession
Host   = model and tool execution
```

The Brain does not become a second OS, scheduler, memory database, connection registry, capability implementation layer, vendor model runtime, or source of hidden authority.

## What is implemented

The Brain currently includes:

- deterministic scoped Brain objects, lifecycle state machines, authority tiers, optimistic concurrency, atomic writes and scope isolation;
- Current/Desired State gap reasoning contracts, opportunity discovery, initiative ranking, dedupe, WIP caps and attention budgets;
- objective planning, progress/stall detection, attempt budgets and V0-V3 evidence-backed verification;
- derived user/agent/world beliefs with freshness and contradiction handling;
- staged reflection, learning and controlled strategy evolution with privileged self-modification blocked;
- cadence trigger contracts without owning the scheduler;
- model-neutral reasoning envelopes and a runtime-neutral end-to-end cognition pipeline;
- replay-safe external action boundaries with exact approvals, idempotency, receipts and uncertain-outcome reconciliation;
- read-only AI-Verse host detection, integration planning and doctor;
- **alpha.6:** dry-run-first initialization, versioned installation metadata, fail-closed upgrade checks, adaptive explicit-user onboarding and installation/onboarding doctor checks;
- **alpha.7:** a hardened universal JSON subprocess bridge for model/host adapters, live adapter handshake diagnostics, filtered environment forwarding, bounded I/O/timeouts and a safe reference adapter.

The runtime pipeline is:

```text
trigger
  -> bounded orientation/context
  -> reasoner adapter
  -> strict proposal parser
  -> deterministic proposal application
  -> attention/surface decision
  -> optional separately authorized action path
```

The central rule remains:

> **The model may reason about what should happen, but deterministic policy decides what may happen and the host proves what did happen.**

## Safe initialization

Install the package from a checkout during alpha development:

```bash
python -m pip install -e .
```

Inspect the installation plan first:

```bash
ai-verse-brain init /path/to/agent/root
```

No state is written by that command. Apply only after reviewing the plan:

```bash
ai-verse-brain init /path/to/agent/root --apply
```

Standalone mode owns only:

```text
.ai-verse-brain/
.ai-verse-brain/runtime/
.ai-verse-brain/installation.json
```

AI-Verse OS v2 native mode owns only Brain paths such as:

```text
operator/brain/
workspaces/<id>/brain/
runtime/ai-verse-brain/
```

Native initialization requires the host to already expose an `extensions.brain` slot. The installer reports a blocker rather than editing `AI-VERSE.yaml` implicitly.

## Adaptive onboarding

After initialization:

```bash
ai-verse-brain onboard /path/to/agent/root
```

The Brain asks only for missing Brain-owned primitives. At minimum it needs explicit user authority for:

- a desired state;
- a definition of success.

Optional answers can add goals, boundaries, constraints and ongoing practices. Current-state/profile facts remain host/OS-owned rather than being duplicated into Brain onboarding.

Prepare a JSON answers file, review it without writing:

```bash
ai-verse-brain onboard /path/to/agent/root --answers brain-onboarding.json
```

Then explicitly apply it:

```bash
ai-verse-brain onboard /path/to/agent/root --answers brain-onboarding.json --apply
```

Identical answers are deduplicated. The Brain cannot infer an unconfirmed goal into confirmed user intent.

See [`docs/INSTALLATION.md`](docs/INSTALLATION.md) and [`protocol/INSTALLATION-ONBOARDING.md`](protocol/INSTALLATION-ONBOARDING.md).

## Universal runtime adapters

Brain now has one vendor-neutral adapter transport:

```text
Brain
  -> ai-verse-brain-bridge/1.0
      -> Claude wrapper
      -> Codex wrapper
      -> Hermes wrapper
      -> local/custom runtime
```

An adapter config uses an argument array, never a shell command. Credential values do not belong in the config. Only explicitly allowlisted environment-variable names are forwarded beyond a small process environment.

Validate and live-handshake an adapter with:

```bash
ai-verse-brain adapter-doctor /path/to/adapter.json
```

A safe no-op reference implementation is included:

```bash
ai-verse-brain adapter-doctor examples/reference-adapter.json
```

The bridge can provide both `ReasonerAdapter` and `HostAdapter` implementations, but advertising an operation never grants authority. External actions still pass through Brain's independent action policy, approval, scope, idempotency and receipt gates.

See [`docs/ADAPTERS.md`](docs/ADAPTERS.md) and [`protocol/ADAPTER-BRIDGE.md`](protocol/ADAPTER-BRIDGE.md).

## Health and integration

```bash
ai-verse-brain doctor .
ai-verse-brain plan-integration .
ai-verse-brain plan-cadence --scope operator --proactivity 2
```

`doctor` is read-only. It checks host compatibility, parallel-store risk, installation/state-schema integrity, state scope/kind integrity and minimum onboarding readiness.

AI-Verse OS and AI-Verse Memory remain separate repositories. Memory is optional. Brain never silently falls back to a parallel standalone store inside an incompatible AI-Verse host.

## Development

```bash
python -m unittest discover -s tests -v
```

The implementation uses only the Python standard library and targets Python 3.9+. CI tests Python 3.9 and 3.12 on Ubuntu, macOS and Windows.

Implementation contracts live in [`protocol/`](protocol/). Full Phase 1-3 research remains in [`research/`](research/README.md).

## Remaining before public stable shipment

Alpha.7 is not the stable release. Remaining shipment work includes vendor-specific Claude/Codex/Hermes reference wrappers, scheduler hooks, migration implementations for future state schemas, one-line distribution/release packaging, end-to-end clean-machine install tests, release security/docs, observability/user commands and public-beta compatibility hardening.

## License

A release license has not yet been finalized for the Brain repository.
