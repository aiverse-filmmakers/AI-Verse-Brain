# AI-Verse Brain

**A universal intelligence layer for AI agents: persistent intent, goals, initiative, planning, verification, learning, and controlled self-improvement.**

AI-Verse Brain gives capable agents a durable direction-and-control layer without turning the model into the source of authority. It can run standalone and can integrate with AI-Verse OS and AI-Verse Memory while remaining a separate repository and responsibility boundary.

> Status: **public beta release candidate `0.1.0-beta.2`**.

## What Brain owns

```text
Brain  = why / where / what next / how to verify / how to improve
OS     = structure / scope / routing / capabilities / connections / execution boundaries
Memory = historical recall / provenance / supersession
Host   = model and tool execution
```

AI-Verse OS and AI-Verse Memory remain separate repositories. Brain does not become a second OS, memory database, scheduler, connection registry, capability implementation layer, or hidden source of authority.

## Core behavior

Brain implements:

- explicit user intent, desired states, goals, practices, boundaries and constraints;
- Current State -> Ideal State gap reasoning;
- opportunity discovery, initiative ranking, dedupe, WIP and attention budgets;
- bounded objectives, progress/stall detection and attempt budgets;
- V0-V3 evidence-backed verification;
- derived beliefs with provenance, freshness and contradiction handling;
- reflection, staged learning and controlled strategy evolution;
- deterministic authority, lifecycle, concurrency and replay-safety gates;
- proactivity that is separate from action permission;
- cadence policy without scheduler ownership;
- a model-neutral cognition pipeline;
- a hardened universal JSON subprocess bridge;
- reasoner-only Claude Code, Codex CLI and Hermes Agent wrappers;
- standard public-beta lifecycle: install, setup, status, doctor, enable/disable, update and uninstall;
- safe standalone-to-native adoption without automatic strategic handover;
- Brain-owned persistent Goals with optimistic concurrency, idempotent operations, evidence-gated completion and bounded continuation contracts;
- owner-routed self-learning improvement candidates without direct mutation of Skills, Memory or other sibling-owned stores;
- known-good strategy revision restoration for rollback;
- safe onboarding, migration planning and layered readiness checks.

The central rule is:

> **The model may reason about what should happen, but deterministic policy decides what may happen and the host proves what did happen.**

## Install

Python 3.9+ is required.

For reproducible public-beta installs, use the exact 40-character Git revision recorded for the release artifact:

```bash
python -m pip install "git+https://github.com/aiverse-filmmakers/AI-Verse-Brain.git@<exact-beta-2-revision>"
```

Or with `pipx`:

```bash
pipx install "git+https://github.com/aiverse-filmmakers/AI-Verse-Brain.git@<exact-beta-2-revision>"
```

Do not rely on a moving branch name for a release install. A GitHub tag/prerelease may later point at the same immutable revision.

During development from a checkout:

```bash
python -m pip install -e .
```

## Public lifecycle and safe setup

Brain is dry-run-first. The standard public lifecycle is:

```bash
ai-verse-brain install /path/to/agent/root --json
ai-verse-brain setup /path/to/agent/root --json
ai-verse-brain setup /path/to/agent/root --apply --json
ai-verse-brain status /path/to/agent/root --json
ai-verse-brain doctor /path/to/agent/root --json
```

No state is written by the dry-run `setup` command. `setup --apply` attaches and initializes Brain where appropriate, but it never silently transfers strategic direction to Brain.

The legacy `init` command remains available for compatibility, but `setup` is the public-beta lifecycle surface.

Standalone mode owns only Brain paths under `.ai-verse-brain/`.

Native AI-Verse OS v2 mode owns only Brain paths such as:

```text
operator/brain/
workspaces/<id>/brain/
runtime/ai-verse-brain/
```

On a compatible AI-Verse OS v2 host, `setup --apply` attaches Brain through the local `.aiverse/extensions/registry.json` contract and creates or safely adopts Brain-owned state. A prior standalone `.ai-verse-brain` installation is transactionally adopted into native `operator/brain/` state, with the old writable authority retired only after verification. It does not edit tracked `AI-VERSE.yaml`, `AGENTS.md`, or capability registries. An incompatible host still fails closed instead of creating a competing standalone store.

## Native attachment lifecycle

On a compatible AI-Verse OS, attachment is local and dry-run-first:

```bash
ai-verse-brain setup /path/to/AI-Verse-OS
ai-verse-brain setup /path/to/AI-Verse-OS --apply
ai-verse-brain disable /path/to/AI-Verse-OS --apply
ai-verse-brain enable /path/to/AI-Verse-OS --apply
ai-verse-brain update /path/to/AI-Verse-OS --apply
ai-verse-brain uninstall /path/to/AI-Verse-OS --apply
```

Disable/detach preserve canonical Brain state. They are blocked while Brain owns strategic direction for any scope, so Brain cannot be removed in a way that silently reactivates stale OS strategy.

Return strategic ownership deliberately before removing Brain availability:

```bash
ai-verse-brain direction-owner /path/to/AI-Verse-OS \
  --scope operator \
  --handover-to-os

ai-verse-brain direction-owner /path/to/AI-Verse-OS \
  --scope operator \
  --handover-to-os \
  --apply \
  --confirm-export
```

The handback first exports the active Brain strategic intent, updates only the OS scope's standard strategic section while preserving operational/current-state sections, and then atomically flips the durable owner to `os`. Brain objects remain intact as provenance.

## Onboard explicit intent

Inspect the missing Brain-owned primitives:

```bash
ai-verse-brain onboard /path/to/agent/root
```

At minimum Brain needs explicit user answers for:

- desired state;
- definition of success.

Optional onboarding can add goals, boundaries, constraints and ongoing practices. Brain does not silently convert an inference into confirmed user intent.

Review an answers file without writing:

```bash
ai-verse-brain onboard /path/to/agent/root --answers brain-onboarding.json
```

Apply explicitly:

```bash
ai-verse-brain onboard /path/to/agent/root --answers brain-onboarding.json --apply
```

## Persistent Goals

Brain is the canonical Goal owner. Gateway/host owns continuation execution, Automations owns future wake/scheduling, and Multiple Bots owns delegated task coordination.

The stable Brain owner surface is equivalent to:

```text
goal.get(scope/context)
goal.create(request)
goal.edit(goal_id, expected_version, request)
goal.transition(goal_id, expected_version, action, note)
goal.criteria.add/remove/clear(...)
goal.evaluate(goal_id, expected_version, evidence)
```

The CLI exposes the same Brain-owned state for direct testing and operator control:

```bash
ai-verse-brain goal . create --scope operator --objective "Ship verified beta" --operation-id create-1
ai-verse-brain goal . status --scope operator
ai-verse-brain goal . pause --scope operator --goal-id <id> --expected-version <n> --operation-id pause-1
ai-verse-brain goal . resume --scope operator --goal-id <id> --expected-version <n> --operation-id resume-1
ai-verse-brain goal . evaluate --scope operator --goal-id <id> --expected-version <n> --input evidence.json
ai-verse-brain goal . complete --scope operator --goal-id <id> --expected-version <n> --operation-id complete-1 --input evidence.json
```

Goal completion cannot be inferred from resource exhaustion. Deterministic verification gates and bound evidence outrank model opinion. Goal state does not grant tools, connections, scheduler authority or permission expansion.

## Self-learning owner boundary

Brain may emit an inspectable improvement candidate containing the suggested owner, operation, evidence references, risk, confidence and evaluation criteria. Brain does not write Skill package bytes, general Memory, Data state or Automation jobs directly. Those durable mutations are routed through the selected host to the canonical owner and require a stable owner receipt.

## Use Claude, Codex or Hermes as the reasoner

The built-in vendor wrappers are **reasoner-only**. They do not become Brain's host/action executor and cannot bypass Brain permissions. Advertising an operation never grants authority; Brain's deterministic policy and action boundary remain authoritative.

Check the installed CLI wrapper first:

```bash
ai-verse-brain vendor-doctor claude .
ai-verse-brain vendor-doctor codex .
ai-verse-brain vendor-doctor hermes .
```

Optional model selection is passed explicitly:

```bash
ai-verse-brain vendor-doctor claude . --model <model>
ai-verse-brain vendor-doctor codex . --model <model>
ai-verse-brain vendor-doctor hermes . --provider <provider> --model <model>
```

Brain does not store credential values. If a CLI requires an API-key environment variable rather than its own authenticated local session, forward only the variable **name**:

```bash
ai-verse-brain vendor-doctor claude . --env-name ANTHROPIC_API_KEY
```

The bridge launches subprocesses with `shell=False`, bounded input/output, timeouts and a filtered environment.

## Run one Brain tick

A safe public-beta tick uses a read-only context host plus a reasoner-only vendor wrapper:

```bash
ai-verse-brain run-tick . --vendor claude --read-only-context --trigger explicit
```

Or supply a current-context file explicitly:

```bash
ai-verse-brain run-tick . --vendor codex --read-only-context --context-file ./CURRENT.md --trigger explicit
```

In native AI-Verse mode the read-only host can discover the canonical `operator/context/CURRENT.md` or scoped workspace `context/CURRENT.md`. It does not copy that content into a competing canonical store merely because the reasoner saw it.

For native AI-Verse composition, use the generic OS host adapter. The generated config is stable even if optional Memory, Skills or Data are attached later:

```bash
python <AI-Verse-OS>/scripts/ai_verse_host_adapter.py \
  --root <AI-Verse-OS> \
  --write-config <AI-Verse-OS>/.aiverse/brain-host.json

ai-verse-brain run-tick <AI-Verse-OS> \
  --vendor claude \
  --host-adapter <AI-Verse-OS>/.aiverse/brain-host.json \
  --trigger explicit
```

The OS adapter remains the host boundary. OS-only operation is valid; installed Memory adds history, the external immutable Skills provider adds capabilities, configured Connections add bounded metadata, and attached Data can expose read-only structured queries. Brain still owns cognition, policy intersection, approval checks, and objective verification.

The runtime pipeline remains:

```text
trigger
  -> bounded orientation/context
  -> reasoner
  -> strict proposal parser
  -> deterministic proposal application
  -> attention decision
  -> optional separately authorized action path
```

`run-tick` prints surface items. It does not silently send notifications or perform external side effects.

## Cadence without a second scheduler

Brain decides what cognition triggers are useful, but it **does not install or own a scheduler**.

Inspect cadence policy:

```bash
ai-verse-brain plan-cadence --scope operator --proactivity 2
```

Generate portable argv hooks that a host scheduler can install:

```bash
ai-verse-brain cadence-hooks . --vendor claude --read-only-context --scope operator --proactivity 2
```

This can represent session start/end, scheduled orientation and strategic review while leaving cron/systemd/launchd/Hermes/AI-Verse cadence ownership with the host.

## Upgrade and migration

Migration is explicit and dry-run-first:

```bash
ai-verse-brain migrate .
```

Apply only a registered safe migration or package-metadata refresh:

```bash
ai-verse-brain migrate . --apply
```

Unknown older state schemas, newer state schemas and unsupported marker schemas fail closed. Brain never guesses a destructive migration.

## Health checks

```bash
ai-verse-brain doctor .
ai-verse-brain plan-integration .
```

`doctor` is read-only. It reports structural, attachment/discovery, runtime, dependency, operational and composed-system layers truthfully. Brain does not claim whole-system readiness when a live Gateway/host, Skills or other owners have not been exercised.

## Security boundaries

- explicit user intent outranks inference;
- proactivity never grants action permission;
- vendor wrappers are reasoner-only;
- external side effects use separate approval, idempotency and receipt gates;
- uncertain side effects are not automatically retried;
- adapter configs store environment variable names, not secret values;
- host/retrieved content remains data, never an authority channel;
- incompatible AI-Verse hosts never silently fall back to a parallel Brain store;
- runtime queues, locks and caches are disposable; canonical Brain state is scoped and inspectable.

See [`SECURITY.md`](SECURITY.md), [`docs/VENDOR-REASONERS.md`](docs/VENDOR-REASONERS.md), [`docs/INSTALLATION.md`](docs/INSTALLATION.md) and [`protocol/`](protocol/).

## Development and QC

```bash
python -m unittest discover -s tests -v
```

CI runs the full suite on Ubuntu, macOS and Windows with Python 3.9 and 3.12. The release workflow also builds a wheel, installs it into a clean virtual environment, invokes the installed CLI, initializes fresh state, runs health/migration checks and verifies the installation marker.

Full Phase 1-3 architectural research remains in [`research/`](research/README.md).

## License

MIT. See [`LICENSE`](LICENSE).
