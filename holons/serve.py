from __future__ import annotations

"""Standard gRPC server runner for Python holons."""

import logging
import signal
import sys
from concurrent import futures
from typing import Callable

import grpc
from grpc_reflection.v1alpha import reflection

from holons.transport import DEFAULT_URI, scheme
from holons.runtime_state import register_mem_endpoint, unregister_mem_endpoint, normalize_mem_uri

logger = logging.getLogger("holons.serve")

RegisterFunc = Callable[[grpc.Server], None]


def parse_flags(args: list[str]) -> str:
    """Extract --listen or --port from command-line args."""
    for i, arg in enumerate(args):
        if arg == "--listen" and i + 1 < len(args):
            return args[i + 1]
        if arg == "--port" and i + 1 < len(args):
            return f"tcp://:{args[i + 1]}"
    return DEFAULT_URI


def run(listen_uri: str, register_fn: RegisterFunc) -> None:
    """Start a gRPC server with reflection enabled."""
    run_with_options(listen_uri, register_fn, reflect=True)


def run_with_options(
    listen_uri: str,
    register_fn: RegisterFunc,
    reflect: bool = True,
    max_workers: int = 10,
) -> None:
    """Start a gRPC server on the given transport URI.

    Native gRPC python transports: tcp://, unix://
    In-process adapter: mem://
    """
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=max_workers))
    register_fn(server)

    reflection_enabled = False
    if reflect:
        # We cannot inspect exact service names without service descriptors,
        # so we expose reflection service only unless caller registered more
        # via reflection APIs.
        reflection.enable_server_reflection((reflection.SERVICE_NAME,), server)
        reflection_enabled = True

    transport = scheme(listen_uri)
    mem_key = None

    if transport == "tcp":
        addr = listen_uri[6:]
        port = server.add_insecure_port(addr)
        host = addr.rpartition(":")[0] or "0.0.0.0"
        actual_uri = f"tcp://{host}:{port}"
    elif transport == "unix":
        path = listen_uri[7:]
        server.add_insecure_port(f"unix:{path}")
        actual_uri = listen_uri
    elif transport == "mem":
        port = server.add_insecure_port("127.0.0.1:0")
        actual_uri = normalize_mem_uri(listen_uri)
        mem_key = register_mem_endpoint(actual_uri, f"127.0.0.1:{port}")
    else:
        raise ValueError(
            "gRPC Python server supports tcp://, unix://, and mem:// adapter in run_with_options(). "
            f"For {transport}://, use holons.transport.listen() with a custom server loop."
        )

    mode = "reflection ON" if reflection_enabled else "reflection OFF"
    logger.info("gRPC server listening on %s (%s)", actual_uri, mode)

    server.start()

    def _shutdown(*_args):
        logger.info("shutting down gRPC server")
        server.stop(5)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    print(f"gRPC server listening on {actual_uri} ({mode})", file=sys.stderr)

    try:
        server.wait_for_termination()
    finally:
        if mem_key:
            unregister_mem_endpoint(mem_key)
