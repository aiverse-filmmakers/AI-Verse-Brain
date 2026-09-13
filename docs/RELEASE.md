# Public Beta Release Checklist

This document is the shipment gate for `0.1.0-beta.2`.

## Release invariants

A beta release must preserve all of the following:

- Brain remains a separate repository from AI-Verse OS and AI-Verse Memory.
- Installer writes only Brain-owned paths.
- Native AI-Verse integration fails closed if the host contract is missing/incompatible.
- Explicit user intent outranks inference.
- Vendor CLIs remain reasoner-only by default.
- Proactivity does not grant side-effect permission.
- Brain does not own or install a scheduler.
- Unknown state migrations fail closed.
- Standalone-to-native adoption retires competing writable authority only after verified migration.
- `setup` never silently transfers strategic direction.
- Persistent Goal mutation is version checked and idempotent.
- Goal completion requires declared evidence/verification gates where applicable.
- Brain emits self-learning candidates but does not mutate sibling-owned Skill/Memory/Data stores directly.
- Side effects remain separately authorized and receipt-backed.

## Automated gate

CI must pass:

- Ubuntu, Python 3.9
- Ubuntu, Python 3.12
- macOS, Python 3.9
- macOS, Python 3.12
- Windows, Python 3.9
- Windows, Python 3.12
- wheel build + clean-machine-style virtual-environment install smoke test

The package smoke test must install the built wheel rather than using editable mode, invoke the installed `ai-verse-brain` entry point, run `install -> setup -> status -> doctor -> update`, verify the installation marker, and prove the public lifecycle works from the artifact.

## Manual release gate

Before tagging:

1. Confirm the PR head is the exact commit that passed CI.
2. Confirm no unresolved review thread represents a release blocker.
3. Confirm `BRAIN.yaml`, `_version.py`, package metadata and README all say `0.1.0-beta.2` / `0.1.0b2` consistently.
4. Re-check current Claude Code, Codex CLI and Hermes Agent non-interactive flags. Vendor CLIs are external moving dependencies.
5. Confirm `SECURITY.md`, `CHANGELOG.md`, `LICENSE`, installation docs and vendor docs are present.
6. Confirm no credential values, generated local state or runtime artifacts are tracked.
7. Merge the release candidate only when CI, OS Direction Ownership Contract and Skills Receipt Contract are green on the exact PR head.
8. Record the exact 40-character merged Git revision as the immutable beta.2 source artifact.
9. If publishing a GitHub tag/prerelease, point `v0.1.0-beta.2` at that exact immutable revision.
10. Test the exact-revision install in a fresh environment where possible.

## User install

```bash
python -m pip install "git+https://github.com/aiverse-filmmakers/AI-Verse-Brain.git@<exact-beta-2-revision>"
ai-verse-brain install /path/to/root --json
ai-verse-brain setup /path/to/root --json
ai-verse-brain setup /path/to/root --apply --json
ai-verse-brain status /path/to/root --json
ai-verse-brain doctor /path/to/root --json
```

`setup` and onboarding answer ingestion are dry-run-first where applicable. Users should inspect plans before applying mutations.

## Beta expectation

`0.1.0-beta.2` means the architecture and safety contracts are intended for real external testing, but the API and state schema can still evolve before 1.0. Any state-schema change must ship with an explicit migration path or fail closed.
