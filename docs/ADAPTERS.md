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

Recommended read-oriented operations:

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

For users who only need safe cognition, the built-in `ReadOnlyContextHost` is intentionally smaller: current context only, no history ownership, no scheduler, no notifications and no write/action path.

## Failure semantics

Brain fails closed if an adapter:

- times out;
- exceeds I/O limits;
- crashes or exits nonzero;
- returns invalid JSON;
- duplicates JSON object keys;
- returns the wrong protocol/request ID;
- returns an invalid result shape;
- uses an operation it did not advertise.

Do not create fallback code that bypasses these errors by directly mutating Brain state.

See [`../protocol/ADAPTER-BRIDGE.md`](../protocol/ADAPTER-BRIDGE.md) for the normative transport contract.
