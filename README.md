---
# Cartouche v1
title: "python-holons — Python SDK for Organic Programming"
author:
  name: "B. ALTER"
  copyright: "© 2026 Benoit Pereira da Silva"
created: 2026-02-12
revised: 2026-02-13
lang: en-US
origin_lang: en-US
translation_of: null
translator: null
access:
  humans: true
  agents: false
status: draft
---
# python-holons

**Python SDK for Organic Programming** — transport, serve, identity,
and grpc client utilities.

## Install

```bash
pip install holons
# or from source
pip install -e .
```

## API surface

| Module | Description |
|--------|-------------|
| `holons.transport` | `listen(uri)`, `parse_uri(uri)`, `scheme(uri)` |
| `holons.serve` | `parse_flags(args)`, `run_with_options(uri, register_fn, ...)` |
| `holons.identity` | `parse_holon(path)` |
| `holons.grpcclient` | `dial`, `dial_uri`, `dial_mem`, `dial_websocket` |
| `holons.holonrpc` | `HolonRPCClient` + `HolonRPCServer` |

## Transport URI support

Recognized URI schemes:

- `tcp://`
- `unix://`
- `stdio://`
- `mem://`
- `ws://`
- `wss://`

`serve.run_with_options(...)` supports:

- native gRPC: `tcp://`, `unix://`
- in-process adapter: `mem://`

For `stdio://` and `ws://`/`wss://` server loops, use `holons.transport.listen()`
with a custom runner.

## Holon-RPC (JSON-RPC 2.0 over WebSocket)

`HolonRPCClient` implements the protocol in `PROTOCOL.md` §4:

- subprotocol: `holon-rpc`
- wire format: JSON-RPC `{\"jsonrpc\":\"2.0\", ...}`
- bidirectional requests with handler registration
- server-originated request ID validation (`s` prefix)
- heartbeat: `rpc.heartbeat`
- reconnect: exponential backoff

`HolonRPCServer` provides server-side promotion for Phase 3:

- accepts WebSocket connections (configurable `ws://` / `wss://` URL)
- negotiates `holon-rpc` subprotocol (`holon-web` accepted for js-web compatibility)
- dispatches incoming method calls via `register(...)`
- supports server-initiated calls to connected clients via `invoke(...)`

## Parity Notes vs Go Reference

Implemented:

- Holon-RPC client (connect/invoke/register/close, heartbeat, reconnect)
- Holon-RPC server (bidirectional JSON-RPC 2.0 over WebSocket)
- gRPC listen/dial on `tcp://` and `unix://`
- in-process `mem://` adapter for tests/composition
- gRPC `ws://` / `wss://` dial via local TCP↔WebSocket tunnel bridge

Not currently achievable in pure `grpcio` (justified gap):

- `Dial(\"stdio://\")` for gRPC channels:
  - `grpcio` does not expose a public API to bind HTTP/2 transport directly to arbitrary stdin/stdout byte streams.
  - `holons.grpcclient.dial_stdio()` is intentionally `NotImplementedError` with explicit guidance.

## Test

```bash
python -m pytest tests/ -v
```
