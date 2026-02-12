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

**Python SDK for Organic Programming** — transport, serve, and identity
utilities for building holons in Python.

> *"Organic Programming SDK for Python."*

## Install

```bash
pip install holons
# or from source
pip install -e .
```

## Quick start

```python
from holons.serve import run
from holons.transport import listen

# Start a gRPC server on any transport
run("tcp://:9090", register_services)
run("unix:///tmp/my.sock", register_services)
run("ws://0.0.0.0:8080", register_services)
run("stdio://", register_services)
```

## API surface

| Module | Description |
|--------|-------------|
| `holons.transport` | `listen(uri)` — URI-based listener factory (tcp, unix, stdio, mem, ws) |
| `holons.serve` | `run(uri, register_fn)` — start gRPC server with graceful shutdown |
| `holons.identity` | `parse_holon(path)` — parse HOLON.md identity files |

## Test

```bash
python -m pytest tests/ -v
```
