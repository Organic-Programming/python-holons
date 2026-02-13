from __future__ import annotations

"""Client-side gRPC helpers for Python holons."""

import grpc

from holons.transport import parse_uri
from holons.runtime_state import resolve_mem_endpoint, normalize_mem_uri


def dial(address: str) -> grpc.Channel:
    """Dial a gRPC server at address.

    Accepted forms:
    - host:port
    - unix:///path.sock
    """
    return grpc.insecure_channel(address)


def dial_mem(uri: str = "mem://") -> grpc.Channel:
    """Dial an in-process mem endpoint registered by serve.run_with_options."""
    key = normalize_mem_uri(uri)
    target = resolve_mem_endpoint(key)
    if not target:
        raise ValueError(f"no mem endpoint is registered for {key}")
    return grpc.insecure_channel(target)


def dial_stdio(*_args, **_kwargs) -> grpc.Channel:
    """Dial gRPC over stdio pipes.

    grpcio does not expose a public transport hook to bind client channels
    directly to stdin/stdout byte streams (unlike Go's custom dialer path).
    """
    raise NotImplementedError(
        "dial_stdio is not available in python-holons: grpcio has no public stdio transport "
        "adapter for HTTP/2 framing"
    )


def dial_uri(uri: str) -> grpc.Channel:
    """Dial using a transport URI.

    Supports:
    - tcp://
    - unix://
    - mem:// (when registered in-process)
    """
    parsed = parse_uri(uri)

    if parsed.scheme == "tcp":
        host = parsed.host or "127.0.0.1"
        if host == "0.0.0.0":
            host = "127.0.0.1"
        return grpc.insecure_channel(f"{host}:{parsed.port}")

    if parsed.scheme == "unix":
        return grpc.insecure_channel(f"unix://{parsed.path}")

    if parsed.scheme == "mem":
        return dial_mem(parsed.raw)

    raise ValueError(
        f"dial_uri() supports tcp://, unix://, and mem://. "
        f"Use transport-specific clients for {parsed.scheme}://"
    )
