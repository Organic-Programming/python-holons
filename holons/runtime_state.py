from __future__ import annotations

"""Runtime shared state for in-process transport adapters."""

from threading import Lock

_mem_endpoints: dict[str, str] = {}
_lock = Lock()


def normalize_mem_uri(uri: str | None) -> str:
    if not uri or uri in {"mem", "mem://"}:
        return "mem://"
    if uri.startswith("mem://"):
        return uri
    raise ValueError(f"invalid mem URI: {uri!r}")


def register_mem_endpoint(uri: str | None, target: str) -> str:
    key = normalize_mem_uri(uri)
    with _lock:
        _mem_endpoints[key] = target
    return key


def resolve_mem_endpoint(uri: str | None) -> str | None:
    key = normalize_mem_uri(uri)
    with _lock:
        return _mem_endpoints.get(key)


def unregister_mem_endpoint(uri: str | None) -> None:
    key = normalize_mem_uri(uri)
    with _lock:
        _mem_endpoints.pop(key, None)
