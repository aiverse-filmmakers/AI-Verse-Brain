# AI-Verse Brain

**A universal intelligence layer for AI agents: persistent intent, goals, initiative, planning, verification, learning, and controlled self-improvement.**

AI-Verse Brain gives capable agents a durable direction-and-control layer without turning the model into the source of authority. It can run standalone and can integrate with AI-Verse OS and AI-Verse Memory while remaining a separate repository and responsibility boundary.

> Status: **public beta release candidate `0.1.0-beta.1`**.

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
- safe initialization, onboarding, migration planning and health checks.

The central rule is:

> **The model may reason about what should happen, but deterministic policy decides what may happen and the host proves what did happen.**

## Install

Python 3.9+ is required.

For the beta tag:

```bash
python -m pip install "git+https://github.com/aiverse-filmmakers/AI-Verse-Brain.git@v0.1.0-beta.1"
```

Or with `pipx`:

```bash
pipx install "git+https://github.com/aiverse-filmmakers/AI-Verse-Brain.git@v0.1.0-beta.1"
```

During development from a checkout:

```bash
python -m pip install -e .
```

## Initialize safely

Brain is dry-run-first. Inspect what it would create:

```bash
ai-verse-brain init /path/to/agent/root
```

No state is written by that command. Apply only after review:

```bash
ai-verse-brain init /path/to/agent/root --apply
```

Standalone mode owns only Brain paths under `.ai-verse-brain/`.

Native AI-Verse OS v2 mode owns only Brain paths such as:

```text
operator/brain/
workspaces/<id>/brain/
runtime/ai-verse-brain/
```

If an AI-Verse host is incompatible or lacks the native Brain extension contract, initialization reports a blocker instead of editing host-owned canonical OS configuration or silently creating a competing standalone store.

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

## Use Claude, Codex or Hermes as the reasoner

The built-in vendor wrappers are **reasoner-only**. They do not become Brain's host/action executor and cannot bypass Brain permissions.

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
ai-verse-brain run-tick . --vendor claude --trigger explicit
```

Or supply a current-context file explicitly:

```bash
ai-verse-brain run-tick . --vendor codex --context-file ./CURRENT.md --trigger explicit
```

In native AI-Verse mode the read-only host can discover the canonical `operator/context/CURRENT.md` or scoped workspace `context/CURRENT.md`. It does not copy that content into a competing canonical store merely because the reasoner saw it.

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
ai-verse-brain cadence-hooks . --vendor claude --scope operator --proactivity 2
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

`doctor` is read-only. It checks host compatibility, parallel-store risk, installation/state-schema integrity, scoped Brain state and minimum onboarding readiness.

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
