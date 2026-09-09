# Vendor Reasoner Wrappers

AI-Verse Brain beta ships built-in **reasoner-only** wrappers for Claude Code, Codex CLI and Hermes Agent.

These wrappers exist for one purpose: convert a bounded Brain cognition request plus context into proposal-shaped JSON. They do not become the Brain host/action executor and do not receive authority merely because the vendor CLI supports tools.

## Shared contract

Every wrapper is launched behind `ai-verse-brain-bridge/1.0` and advertises only:

```json
{"operations":["reason"]}
```

The wrapper prompt requires:

```json
{
  "proposals": [
    {
      "proposal_kind": "...",
      "payload": {},
      "confidence": 0.0,
      "rationale": "..."
    }
  ]
}
```

Brain then parses and validates the proposal under the original cognition request. The vendor cannot set Brain scope, authority, policy, lifecycle status, permissions or action execution.

## Claude Code

Conceptual invocation used by the wrapper:

```text
claude -p \
  --output-format stream-json \
  --verbose \
  --permission-mode plan \
  --no-session-persistence
```

An optional `--model` is added when the user supplies one.

The wrapper parses stream-json and accepts a non-empty final result. It also supports the last assistant text as a compatibility fallback for CLI versions that emit usable assistant content but an empty final-result field.

Brain does not use `--dangerously-skip-permissions`.

## Codex CLI

Conceptual invocation:

```text
codex exec \
  --ephemeral \
  --ignore-user-config \
  --ignore-rules \
  --sandbox read-only \
  --skip-git-repo-check \
  -
```

The trailing `-` explicitly selects prompt input from stdin. An optional `--model` is added when supplied.

Brain intentionally validates the model's returned JSON itself rather than delegating authority to a vendor-side schema or trusting vendor prose.

Brain does not use dangerous approval/sandbox bypass flags.

## Hermes Agent

Conceptual invocation:

```text
hermes chat \
  --oneshot \
  --quiet \
  --safe-mode \
  --toolsets safe \
  --query-file - \
  --max-turns 1 \
  --source tool
```

Optional `--provider` and `--model` are added when supplied.

The `safe` toolset is used so the Brain reasoning wrapper does not grant terminal execution. `--safe-mode` also reduces ambient customization/plugin/rule influence for the bounded one-shot reasoning call.

## Authentication

The wrappers assume the vendor CLI is already installed and authenticated by the user.

Brain does not store credentials. A normal vendor CLI login/session can use its own local credential mechanism. If a provider requires an environment key, forward only the environment variable name:

```bash
ai-verse-brain vendor-doctor claude . --env-name ANTHROPIC_API_KEY
```

The hardened bridge supplies only allowlisted environment variables plus a small baseline required for subprocess execution.

## Verify before use

```bash
ai-verse-brain vendor-doctor claude .
ai-verse-brain vendor-doctor codex .
ai-verse-brain vendor-doctor hermes .
```

A successful handshake proves the wrapper and vendor executable are reachable. It does not grant action authority.

## Run cognition

```bash
ai-verse-brain run-tick . --vendor claude --trigger explicit
ai-verse-brain run-tick . --vendor codex --trigger explicit
ai-verse-brain run-tick . --vendor hermes --trigger explicit
```

The public-beta `ReadOnlyContextHost` supplies current context. External actions remain outside this automatic reasoning path.

## Compatibility policy

Claude Code, Codex CLI and Hermes Agent are external projects and their command-line interfaces can change independently of Brain. Every Brain release should re-check these flags before tagging. If a vendor changes its CLI contract, the wrapper should fail clearly rather than weakening Brain's deterministic authority boundary.
