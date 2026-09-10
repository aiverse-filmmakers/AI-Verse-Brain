# Connecting an Agent Runtime to AI-Verse Brain

AI-Verse Brain does not require a particular model vendor or agent framework. The stable integration boundary is the `ai-verse-brain-bridge/1.0` JSON subprocess protocol.

```text
AI-Verse Brain
    |
    | bounded JSON requests
    v
JSON subprocess bridge
    |
    +--> built-in Claude reasoner wrapper
    +--> built-in Codex reasoner wrapper
    +--> built-in Hermes reasoner wrapper
    +--> local/custom reasoner
    +--> separately authorized host/runtime
```

Vendor-specific code stays outside the deterministic Brain core.

## Built-in vendor wrappers

Public beta includes reasoner-only wrappers:

```bash
ai-verse-brain vendor-doctor claude .
ai-verse-brain vendor-doctor codex .
ai-verse-brain vendor-doctor hermes .
```

They advertise only `reason`. They do not advertise host/action operations.

See [`VENDOR-REASONERS.md`](VENDOR-REASONERS.md) for the current CLI invocation profiles and compatibility policy.

## Custom adapter config

```json
{
  "schema_version": "1.0",
  "name": "my-agent",
  "transport": "json-subprocess",
  "command": ["python", "/path/to/my_bridge.py"],
  "model_id": "my-model"
}
```

Validate it and perform a live handshake:

```bash
ai-verse-brain adapter-doctor /path/to/adapter.json
```

## Explicit runtime host selection

`run-tick` never guesses a host and never silently downgrades a requested real host to the built-in read-only stub.

For a real runtime/agent host, pass its bridge config explicitly:

```bash
ai-verse-brain run-tick . \
  --vendor codex \
  --host-adapter /absolute/path/to/host-adapter.json
```

Before the reasoner starts, Brain loads the config, starts the adapter, validates the bridge handshake, and requires the host to advertise all runtime read operations:

```text
read_context
retrieve_history
list_capabilities
list_connections
```

If the config is unreadable, the process cannot start, the bridge handshake fails, or any required read operation is missing, the tick fails closed. Brain does not replace that host with another adapter.

The tick result reports the selected host mode, adapter ID, advertised operations, config name/path, and idempotency support. It does not persist credential values.

The limited current-context-only host remains available only through an explicit opt-in:

```bash
ai-verse-brain run-tick . \
  --vendor codex \
  --read-only-context
```

`--context-file` is valid only with `--read-only-context`; it cannot override data supplied by a real host adapter.

`cadence-hooks` follows the same rule. Every generated scheduler argv preserves either `--host-adapter ...` or `--read-only-context`, so scheduled ticks cannot acquire a different implicit host later.

Programmatic callers can use `select_host(...)` and receive a `HostSelection` carrying both the selected `HostAdapter` and non-secret selection metadata.

## Credentials

Do not put credential values in adapter JSON or command arguments.

If a wrapper expects a provider credential from the environment, list only its variable name:

```json
{
  "env_names": ["MY_PROVIDER_API_KEY"]
}
```

The credential value is not persisted by Brain. The bridge supplies a small baseline process environment plus explicitly allowlisted variable names.

## Writing a reasoner wrapper

Every invocation receives exactly one bridge request on stdin and must return exactly one bridge response on stdout.

Implement `describe` and advertise `reason`.

For `reason`, the payload contains a bounded cognition request plus ephemeral context. Translate it into the vendor/model format and return only proposal data allowed by Brain's cognition contract.

Do not let the model decide Brain scope, lifecycle status, permissions, approvals or policy. Those are bound outside model output.

## Writing a host wrapper

A host can expose read operations and, where necessary, separately authorized execution operations.

Required read operations for a host selected by `run-tick`:

```text
read_context
retrieve_history
list_capabilities
list_connections
```

Execution-capable hosts may additionally expose:

```text
request_action
request_evaluation
schedule_trigger
cancel_trigger
notify_user
write_route
```

Advertising an operation never grants authority. `ActionExecutor` and Brain policy remain in front of external effects.

For users who only need safe cognition, the built-in `ReadOnlyContextHost` is intentionally smaller: current context only, no history ownership, no scheduler, no notifications and no write/action path. Runtime use of it must be selected explicitly.

## Retrieval semantics

Brain owns the retrieval intent. Host adapters own access to their data sources.

For history, Brain now constructs a bounded semantic query from the cognition purpose, current host context, and the relevant canonical Brain objects. A `reflection` or `gap_analysis` enum value is never used as the query itself. `retrieve_history(query, scope)` should treat `query` as semantic recall text. An adapter backed by AI-Verse Memory should pass that text into Memory recall/search for the same scope and return the ranked result objects.

For capabilities, `list_capabilities(scope)` should return the complete bounded candidate set visible in that scope, using provider metadata such as:

```text
id
name
description
operators
dependencies
tags / keywords when available
```

Brain ranks those candidates deterministically against a task-specific capability query **before** applying its reasoning-context limit. Provider order is not task relevance. A relevant capability at the end of a valid bounded provider result must be able to outrank irrelevant entries at the beginning.

Brain's default candidate ceiling is 1000 entries. If a host would exceed that ceiling it should scope/filter the provider result explicitly. Brain fails closed on overflow rather than silently truncating the candidate set and pretending the tail was considered.

The semantic queries used for the current context assembly are exposed in `ContextBundle.retrieval_queries` for auditability. They remain query metadata, not authority and not canonical Brain state.

## Failure semantics

Brain fails closed if an adapter:

- times out;
- exceeds I/O limits;
- crashes or exits nonzero;
- returns invalid JSON;
- duplicates JSON object keys;
- returns the wrong protocol/request ID;
- returns an invalid result shape;
- uses an operation it did not advertise;
- is selected as a runtime host but does not advertise the complete required read surface;
- returns a capability candidate stream beyond Brain's explicit bounded candidate budget.

Do not create fallback code that bypasses these errors by directly mutating Brain state or silently choosing another host.

See [`../protocol/ADAPTER-BRIDGE.md`](../protocol/ADAPTER-BRIDGE.md) for the normative transport contract.
