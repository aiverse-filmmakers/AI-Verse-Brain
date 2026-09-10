# Adapter Bridge Contract

Status: Phase 5 alpha.7.

AI-Verse Brain must be able to use many runtimes without giving any runtime direct authority over Brain state. The universal adapter boundary is therefore a small JSON-over-stdin/stdout subprocess protocol.

## Why a subprocess bridge

The Brain core should not depend on Claude, Codex, Hermes, OpenAI, Anthropic, or any one SDK. A host-specific wrapper can translate between its runtime and this bridge contract while the Brain keeps one deterministic authority model.

The bridge is an **execution transport**, not a source of authority.

## Security properties

The built-in JSON subprocess transport:

- executes an argument array with `shell=False`;
- rejects shell-string configuration;
- uses bounded stdin, stdout and stderr sizes;
- enforces a bounded timeout and kills an over-budget adapter;
- correlates every response to a Brain-generated request ID;
- requires the exact bridge protocol identifier;
- rejects unknown response control fields;
- exposes only a small base environment plus explicitly named environment variables;
- stores environment variable **names**, never credential values;
- does not persist adapter responses as canonical Brain state merely because they were returned;
- cannot bypass Brain action permissions, approvals, idempotency or verification gates.

A user may deliberately grant a wrapper access to an environment variable by listing its name in `env_names`. The secret value remains outside the adapter configuration file.

## Protocol

Protocol identifier:

```text
ai-verse-brain-bridge/1.0
```

Every request is one JSON object written to stdin:

```json
{
  "protocol": "ai-verse-brain-bridge/1.0",
  "request_id": "brain-generated-uuid",
  "operation": "describe",
  "payload": {}
}
```

The adapter must write exactly one JSON response object to stdout:

```json
{
  "protocol": "ai-verse-brain-bridge/1.0",
  "request_id": "same-uuid",
  "ok": true,
  "result": {}
}
```

Errors use `ok: false` and an `error` string or object. Human/debug logs belong on stderr, not stdout.

## Handshake

Every adapter must implement `describe` and return:

```json
{
  "adapter_id": "example-host",
  "protocol_version": "1.0",
  "operations": ["reason", "read_context"],
  "idempotency_supported": false,
  "metadata": {}
}
```

Brain refuses incompatible protocol versions. Host operations must be advertised before the Brain adapter delegates them.

## Reasoner operation

`reason` receives:

```json
{
  "request": {"...": "bounded CognitionRequest"},
  "context": {"...": "bounded ContextBundle"}
}
```

Its result is still untrusted model output. It goes through the strict proposal parser and deterministic ProposalApplier before any canonical Brain write.

The wrapper must not return policy, permissions, scope authority, lifecycle status or an external side effect as if those were model proposals.

## Host operations

A host bridge may advertise any subset of:

- `read_context`
- `retrieve_history`
- `list_capabilities`
- `list_connections`
- `request_action`
- `request_evaluation`
- `schedule_trigger`
- `cancel_trigger`
- `notify_user`
- `write_route`

An advertised operation means only that the adapter can perform it. It does **not** mean Brain policy authorizes it.

For example, `request_action` is reached only through the explicit `ActionExecutor` path after Brain's action-class policy, scope, budget, approval and replay-safety gates have passed.

### `retrieve_history`

Brain sends:

```json
{
  "query": "bounded semantic recall text derived from the actual cognition task",
  "scope": "operator"
}
```

The query is not an internal purpose token. Host adapters should execute semantic/history retrieval against that text in the requested scope. An AI-Verse Memory-backed adapter should use the query as Memory recall/search text and return the ranked result objects. The result must be an array of objects.

### `list_capabilities`

Brain sends:

```json
{
  "scope": "operator"
}
```

The host should return the complete **bounded** candidate set visible to that scope. Provider order is not considered task relevance. Brain constructs its own task-specific capability query, scores provider-style fields such as `id`, `name`, `description`, `operators`, `dependencies`, `tags`, and `keywords`, ranks the candidates, and only then applies the reasoning-context limit.

This keeps the bridge protocol backward compatible while preventing the previous first-N truncation failure. Brain's default candidate ceiling is 1000 entries; an over-budget candidate stream fails closed instead of being silently truncated.

The generated semantic history/capability queries may be included in the ephemeral `ContextBundle.retrieval_queries` for observability. They are data/query metadata only and never grant authority.

## Idempotency

`describe.idempotency_supported` tells Brain whether the host provides an idempotent external action boundary.

This flag cannot make a forbidden action permissible. It only affects whether an otherwise authorized side effect may safely use automatic replay behavior. Uncertain external outcomes remain blocked from blind retries.

## Configuration

Example:

```json
{
  "schema_version": "1.0",
  "name": "my-agent-bridge",
  "transport": "json-subprocess",
  "command": ["python", "/absolute/path/to/bridge_wrapper.py"],
  "timeout_seconds": 60,
  "env_names": ["MY_PROVIDER_API_KEY"],
  "model_id": "my-model"
}
```

`command` is always an argument array. The core does not invoke a shell.

Do not place credentials, bearer tokens or passwords in the config or command arguments. Use the host credential system or explicitly passed environment-variable names.

## Vendor wrappers

Claude Code, Codex, Hermes and other runtime integrations belong in small wrappers behind this contract. Those wrappers may evolve with vendor CLIs/APIs without changing Brain's canonical intelligence/state model.

A vendor wrapper must never gain direct access to Brain policy mutation or canonical write APIs merely because it runs a model.

## Failure behavior

The bridge fails closed on:

- process start failure;
- timeout;
- output-size overflow;
- nonzero exit;
- malformed JSON;
- protocol mismatch;
- request ID mismatch;
- malformed handshake;
- undeclared host operation;
- unexpected result type;
- an over-budget capability candidate stream presented to Brain context assembly.

Adapter failure becomes an execution error, not permission to switch to a different authority path.
