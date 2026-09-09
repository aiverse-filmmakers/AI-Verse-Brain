# Public Beta Release Checklist

This document is the shipment gate for `v0.1.0-beta.1`.

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

The package smoke test must install the built wheel rather than using editable mode, invoke the installed `ai-verse-brain` entry point, initialize an empty root, run doctor/migration flows and verify the installation marker.

## Manual release gate

Before tagging:

1. Confirm the PR head is the exact commit that passed CI.
2. Confirm no unresolved review thread represents a release blocker.
3. Confirm `BRAIN.yaml`, `_version.py`, package metadata and README all say `0.1.0-beta.1` / `0.1.0b1` consistently.
4. Re-check current Claude Code, Codex CLI and Hermes Agent non-interactive flags. Vendor CLIs are external moving dependencies.
5. Confirm `SECURITY.md`, `CHANGELOG.md`, `LICENSE`, installation docs and vendor docs are present.
6. Confirm no credential values, generated local state or runtime artifacts are tracked.
7. Squash-merge the release candidate.
8. Create tag `v0.1.0-beta.1` on the merged commit.
9. Create the GitHub prerelease from that exact tag.
10. Test the documented tag install in a fresh environment where possible.

## User install

```bash
python -m pip install "git+https://github.com/aiverse-filmmakers/AI-Verse-Brain.git@v0.1.0-beta.1"
ai-verse-brain init /path/to/root
ai-verse-brain init /path/to/root --apply
ai-verse-brain onboard /path/to/root
ai-verse-brain doctor /path/to/root
```

`init` and onboarding answer ingestion are dry-run-first where applicable. Users should inspect plans before applying mutations.

## Beta expectation

`0.1.0-beta.1` means the architecture and safety contracts are intended for real external testing, but the API and state schema can still evolve before 1.0. Any state-schema change must ship with an explicit migration path or fail closed.
