# Installing AI-Verse Brain

AI-Verse Brain `0.1.0-beta.1` is a public beta release candidate. The installation flow is dry-run-first and preserves Brain's ownership boundary.

## 1. Install

Python 3.9+ is required.

From the beta tag:

```bash
python -m pip install "git+https://github.com/aiverse-filmmakers/AI-Verse-Brain.git@v0.1.0-beta.1"
```

Or:

```bash
pipx install "git+https://github.com/aiverse-filmmakers/AI-Verse-Brain.git@v0.1.0-beta.1"
```

From a development checkout:

```bash
python -m pip install -e .
```

Brain has no required third-party runtime Python dependencies.

## 2. Inspect the target before writing

```bash
ai-verse-brain init /path/to/your/agent/root
```

This reports detected host mode, Brain-owned state/runtime paths, planned files/directories, warnings/blockers and existing installation state. It writes nothing.

## 3. Apply initialization

```bash
ai-verse-brain init /path/to/your/agent/root --apply
```

Standalone mode creates Brain state under:

```text
.ai-verse-brain/
.ai-verse-brain/runtime/
.ai-verse-brain/installation.json
```

Compatible AI-Verse OS v2 native mode uses Brain-owned paths such as:

```text
operator/brain/
workspaces/<id>/brain/
runtime/ai-verse-brain/
```

The installer does not edit `AI-VERSE.yaml`. Native mode therefore requires the host to already expose the supported Brain extension contract. An incompatible host is a blocker, never a reason to silently create a parallel store.

## 4. Onboard explicit intent

Inspect questions:

```bash
ai-verse-brain onboard /path/to/your/agent/root
```

At minimum Brain needs explicit user authority for a desired state and definition of success. Optional answers can add goals, hard boundaries, constraints and ongoing practices.

Current-state facts remain host/OS-owned rather than being duplicated by onboarding.

Example `brain-onboarding.json`:

```json
{
  "desired_state": "A reliable system that steadily moves important work forward.",
  "success_definition": "Important goals make measurable progress without hidden autonomy or duplicated truth.",
  "goals": ["Reach a reliable public beta"],
  "boundaries": ["Never silently change user goals or permissions"],
  "constraints": ["Prefer local-first inspectable state"],
  "practices": ["Review active initiatives weekly"]
}
```

Dry run:

```bash
ai-verse-brain onboard /path/to/your/agent/root --answers brain-onboarding.json
```

Apply:

```bash
ai-verse-brain onboard /path/to/your/agent/root --answers brain-onboarding.json --apply
```

Identical answers are deduplicated.

## 5. Check a reasoner

```bash
ai-verse-brain vendor-doctor claude /path/to/your/agent/root
ai-verse-brain vendor-doctor codex /path/to/your/agent/root
ai-verse-brain vendor-doctor hermes /path/to/your/agent/root
```

These built-in wrappers are reasoner-only. They do not become action executors.

## 6. Run one bounded cognition tick

```bash
ai-verse-brain run-tick /path/to/your/agent/root --vendor claude --trigger explicit
```

For standalone use, pass a current-context file if desired:

```bash
ai-verse-brain run-tick /path/to/your/agent/root --vendor codex --context-file /path/to/CURRENT.md
```

## 7. Run doctor

```bash
ai-verse-brain doctor /path/to/your/agent/root
```

Doctor is read-only. It checks host compatibility, parallel-store risk, installation/version integrity, scoped Brain state and onboarding readiness.

## Cadence

Brain does not install a scheduler. Generate portable scheduler requests/argv hooks and let the host decide whether/how to install them:

```bash
ai-verse-brain plan-cadence --scope operator --proactivity 2
ai-verse-brain cadence-hooks /path/to/your/agent/root --vendor claude --scope operator --proactivity 2
```

## Upgrades and migration

Inspect migration first:

```bash
ai-verse-brain migrate /path/to/your/agent/root
```

Apply only a registered safe migration or package metadata refresh:

```bash
ai-verse-brain migrate /path/to/your/agent/root --apply
```

Newer state, unsupported marker schemas and unknown older schemas fail closed. User Brain state is never destructively rewritten merely because a package version changed.

See [`VENDOR-REASONERS.md`](VENDOR-REASONERS.md), [`ADAPTERS.md`](ADAPTERS.md), [`RELEASE.md`](RELEASE.md) and [`../SECURITY.md`](../SECURITY.md).
