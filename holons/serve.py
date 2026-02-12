from __future__ import annotations

"""Standard gRPC server runner for Python holons.

Usage:
    from holons.serve import run

    def register(server):
        my_pb2_grpc.add_MyServiceServicer_to_server(MyServicer(), server)

    run("tcp://:9090", register)
"""

import logging
import signal
import sys
from concurrent import futures
from typing import Callable

import grpc
from grpc_reflection.v1alpha import reflection

from holons.transport import DEFAULT_URI, listen, scheme

logger = logging.getLogger("holons.serve")

# RegisterFunc is called to register gRPC services on the server.
RegisterFunc = Callable[[grpc.Server], None]


def parse_flags(args: list[str]) -> str:
    """Extract --listen or --port from command-line args.

    Returns a transport URI. Falls back to DEFAULT_URI.
    """
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

    Blocks until SIGTERM or SIGINT, then shuts down gracefully.
    """
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=max_workers))
    register_fn(server)

    if reflect:
        # Enable server reflection for introspection
        service_names = [
            sn for sn in server._state.generic_handlers[0].service_name()
        ] if server._state.generic_handlers else []
        service_names.append(reflection.SERVICE_NAME)
        reflection.enable_server_reflection(service_names, server)

    # Bind transport
    transport = scheme(listen_uri)
    if transport == "tcp":
        addr = listen_uri[6:]  # strip tcp://
        port = server.add_insecure_port(addr)
        actual_uri = f"tcp://:{port}"
    elif transport == "unix":
        path = listen_uri[7:]  # strip unix://
        server.add_insecure_port(f"unix:{path}")
        actual_uri = listen_uri
    else:
        # For stdio, mem, ws — gRPC Python doesn't natively support these
        # as server ports. In these cases, the caller should use the
        # transport module's listen() directly with a custom server loop.
        # Standard gRPC server supports tcp:// and unix:// natively.
        raise ValueError(
            f"gRPC Python server natively supports tcp:// and unix://. "
            f"For {transport}://, use holons.transport.listen() directly."
        )

    mode = "reflection ON" if reflect else "reflection OFF"
    logger.info("gRPC server listening on %s (%s)", actual_uri, mode)

    server.start()

    # Graceful shutdown on SIGTERM/SIGINT
    shutdown_event = signal.signal(signal.SIGTERM, lambda *_: server.stop(5))
    signal.signal(signal.SIGINT, lambda *_: server.stop(5))

    print(f"gRPC server listening on {actual_uri} ({mode})", file=sys.stderr)
    server.wait_for_termination()
