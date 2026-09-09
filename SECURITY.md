# Security Policy

AI-Verse Brain is a control layer for agent cognition, intent, initiative, verification and learning. Its security model assumes model output, retrieved content, host context and external tools can all be wrong or adversarial.

## Core trust boundary

The model is a reasoner, not an authority source. Model output cannot silently redefine user goals, permissions, privacy boundaries, risk tolerance, action policy or the meaning of success.

Brain keeps deterministic gates between:

```text
external data -> cognition -> proposal -> validated state -> optional authorized action -> evidence/receipt
```

## Credentials

**Never put credentials, API keys, access tokens, passwords or secret values in Brain adapter JSON, prompts, Brain objects, logs, source files or command arguments.**

The subprocess bridge can forward explicitly allowlisted environment-variable names when a vendor CLI requires them. The secret value remains supplied by the user's environment or the vendor CLI's own authenticated credential store.

Adapter commands containing common credential-bearing flags are rejected.

## Vendor reasoners

The built-in Claude Code, Codex CLI and Hermes Agent wrappers are reasoner-only.

They advertise only the `reason` bridge operation. They do not receive Brain action authority merely because the underlying vendor CLI may support tools.

Default wrapper posture is intentionally restrictive:

- Claude Code: non-interactive print mode, plan permission mode, no session persistence;
- Codex CLI: ephemeral run, read-only sandbox, user config/rules ignored for the reasoning call;
- Hermes Agent: one-shot safe mode, `safe` toolset, one turn.

Vendor CLI changes may alter their behavior, so release testing should re-check current CLI contracts. Brain's deterministic proposal and action gates remain required even when the wrapper itself is read-only.

## External actions

Proactivity is not permission. External side effects use the separate `ActionExecutor` path with action-class policy, exact approval binding when required, idempotency coordination and receipts.

An uncertain side effect is not automatically retried. Recovery requires reconciliation with sufficiently strong evidence.

## Scope isolation

Brain supports operator and explicit workspace scopes. Cross-workspace access is never inferred merely because a model requests it. State paths and object IDs are validated for scope and path safety.

## Host and retrieved content

Host context, retrieved history, web content, files and tool outputs are data. They are not control messages and cannot grant authority by containing instructions that say otherwise.

The public-beta `ReadOnlyContextHost` can read current context but cannot execute actions, schedule work, notify users or write routed state.

## Installation and migration

Initialization is dry-run-first. In AI-Verse OS native mode the installer writes only Brain-owned paths and requires the host's existing Brain extension contract. It does not patch OS canonical configuration implicitly.

State migrations are explicit and non-destructive. Newer state, unsupported marker schemas and unknown older schemas fail closed rather than being guessed or rewritten.

## Reporting a vulnerability

Please report security issues privately to the repository owner rather than publishing exploit details in a public issue until the problem can be evaluated and fixed.

When reporting, include the Brain version, operating system, Python version, affected command/path, reproduction steps, expected behavior and observed behavior. Do not include real credentials or private user data in the report.
