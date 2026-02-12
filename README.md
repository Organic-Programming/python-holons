---
# Cartouche v1
title: "python-holons — Python SDK for Organic Programming"
author:
  name: "B. ALTER"
  copyright: "© 2026 Benoit Pereira da Silva"
created: 2026-02-12
revised: 2026-02-12
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
| `holons.grpcclient` | `dial`, `dial_uri`, `dial_mem` |

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

## Test

```bash
python -m pytest tests/ -v
```
