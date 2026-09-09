# Installing AI-Verse Brain

AI-Verse Brain is still an alpha during Phase 5. The installation flow is designed to be safe before it is made convenient.

## 1. Install the Python package from a checkout

From the repository root:

```bash
python -m pip install -e .
```

The package currently targets Python 3.9+ and has no runtime third-party dependencies.

## 2. Inspect the target before writing anything

```bash
ai-verse-brain init /path/to/your/agent/root
```

This is a dry run. It reports:

- detected host mode;
- state and runtime paths Brain would own;
- files/directories it would create;
- blockers and warnings;
- whether the target is already initialized.

## 3. Apply initialization

After reviewing the plan:

```bash
ai-verse-brain init /path/to/your/agent/root --apply
```

Standalone mode creates only:

```text
.ai-verse-brain/
.ai-verse-brain/runtime/
.ai-verse-brain/installation.json
```

Compatible AI-Verse OS v2 native mode uses:

```text
operator/brain/
runtime/ai-verse-brain/
operator/brain/installation.json
```

The installer does not edit `AI-VERSE.yaml`. Native mode therefore requires the host to already expose an `extensions.brain` slot.

## 4. Inspect onboarding questions

```bash
ai-verse-brain onboard /path/to/your/agent/root
```

The onboarding plan is adaptive. At minimum the Brain needs explicit user authority for:

- a desired state;
- a definition of success.

It may also ask for current goals, hard boundaries, constraints, and ongoing practices.

Current-state facts are deliberately not stored by Brain onboarding. They remain in the host or AI-Verse OS canonical context.

## 5. Prepare answers

Example `brain-onboarding.json`:

```json
{
  "desired_state": "A calm, reliable operating system that steadily moves my important projects forward.",
  "success_definition": "Important projects make measurable progress without hidden autonomy, duplicated truth, or constant interruptions.",
  "goals": [
    "Ship the first production-ready version of my primary project"
  ],
  "boundaries": [
    "Never send, publish, spend, delete, deploy, or change permissions without the required approval policy"
  ],
  "constraints": [
    "Prefer local-first and inspectable state"
  ],
  "practices": [
    "Review active initiatives weekly"
  ]
}
```

Review without writing:

```bash
ai-verse-brain onboard /path/to/your/agent/root --answers brain-onboarding.json
```

Apply explicit answers:

```bash
ai-verse-brain onboard /path/to/your/agent/root --answers brain-onboarding.json --apply
```

Identical answers are deduplicated rather than written twice.

## 6. Run doctor

```bash
ai-verse-brain doctor /path/to/your/agent/root
```

Doctor is read-only. It checks host compatibility, parallel-store risk, installation/version integrity, state scope/kind integrity, and minimum onboarding readiness.

## Upgrade behavior

The installation marker stores the Brain state schema version. A package that encounters newer state refuses to initialize over it. Older state also requires an explicit migration rather than being silently rewritten.

This is intentional. User Brain state must never be destructively upgraded just because a package version changed.

## Not yet included in this Phase 5 slice

- one-line remote installer;
- PyPI stable release;
- production Claude/Codex/Hermes adapters;
- scheduler hooks;
- migration implementations beyond the current state schema;
- stable public release guarantees.

Those are subsequent shipment slices, not reasons to weaken the installation boundary now.
