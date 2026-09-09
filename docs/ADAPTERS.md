# Connecting an Agent Runtime to AI-Verse Brain

AI-Verse Brain does not require a particular model vendor or agent framework. The preferred integration boundary is the `ai-verse-brain-bridge/1.0` JSON subprocess protocol.

This keeps vendor-specific code outside the deterministic Brain core.

## Architecture

```text
AI-Verse Brain
    |
    | bounded JSON requests
    v
JSON subprocess bridge
    |
    +--> Claude wrapper
    +--> Codex wrapper
    +--> Hermes wrapper
    +--> local model wrapper
    +--> custom agent/runtime
```

The wrapper may call a CLI, SDK, local service or existing agent runtime. Brain does not care, provided the wrapper satisfies the bridge contract.

## Minimal config

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

A successful doctor report confirms protocol version, advertised operations and host idempotency support.

## Credentials

Do not put credentials in the adapter JSON or command arguments.

If a wrapper expects a provider credential from the environment, list only its variable name:

```json
{
  "env_names": ["MY_PROVIDER_API_KEY"]
}
```

The Brain process passes that variable only when explicitly allowlisted. The credential value is not stored by Brain.

The subprocess receives a small base environment required for normal process execution plus the names explicitly listed in `env_names`. Arbitrary parent-process environment variables are not inherited.

## Writing a reasoner wrapper

Every process invocation receives exactly one request on stdin and must return exactly one response on stdout.

Your wrapper must implement `describe` and advertise `reason`.

For `reason`, the payload contains:

```json
{
  "request": {
    "purpose": "gap_analysis",
    "scope": "operator",
    "output_contract": {}
  },
  "context": {
    "current_context": {},
    "brain_state": [],
    "history": [],
    "capabilities": [],
    "connections": []
  }
}
```

Translate this into the prompt/API format expected by your model. Return only proposal data allowed by Brain's cognition contract.

Do not let the model decide Brain scope, lifecycle status, permissions, approvals or policy. The core binds those outside the model response.

## Writing a host wrapper

A single wrapper can also expose host operations such as reading current context or delegating an already-authorized action.

Advertise only operations the wrapper genuinely implements.

A host wrapper does not get permission merely by advertising `request_action`. The Brain ActionExecutor remains in front of it.

## Claude, Codex and Hermes

The Brain-side integration is intentionally identical for all three:

1. create a small wrapper around the runtime's supported CLI/SDK/tool interface;
2. implement `describe` and the operations you need;
3. keep provider authentication in that runtime's normal credential mechanism or explicitly allowlisted environment variables;
4. return model reasoning only through `reason`;
5. let Brain validate and apply proposals deterministically;
6. accept external side-effect requests only through the separate host `request_action` operation.

This design prevents future changes to any vendor CLI from changing Brain's source-of-truth, authority or self-improvement model.

Vendor-specific reference wrappers are a subsequent shipment slice. The universal transport and safety boundary are the stable integration target they will use.

## Recommended operation split

A reasoner-only adapter needs:

```text
describe
reason
```

A read-oriented host usually adds:

```text
read_context
retrieve_history
list_capabilities
list_connections
```

An execution-capable host can additionally expose:

```text
request_action
request_evaluation
schedule_trigger
cancel_trigger
notify_user
write_route
```

Only expose what is required.

## Failure semantics

Brain fails closed if a wrapper:

- times out;
- exceeds input/output bounds;
- crashes or exits nonzero;
- returns non-JSON stdout;
- returns the wrong protocol version or request ID;
- lies about result shape;
- tries to use an operation it did not advertise.

Do not write fallback code that bypasses these failures by directly mutating Brain state.

See [`../protocol/ADAPTER-BRIDGE.md`](../protocol/ADAPTER-BRIDGE.md) for the normative protocol.
