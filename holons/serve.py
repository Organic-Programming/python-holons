from __future__ import annotations

"""Standard gRPC server runner for Python holons."""

import logging
import os
import shutil
import signal
import socket
import sys
import tempfile
import threading
from concurrent import futures
from typing import Callable

import grpc
from grpc_reflection.v1alpha import reflection

from holons.transport import DEFAULT_URI, scheme
from holons.runtime_state import register_mem_endpoint, unregister_mem_endpoint, normalize_mem_uri

logger = logging.getLogger("holons.serve")

RegisterFunc = Callable[[grpc.Server], None]
_MAX_GRPC_MESSAGE_BYTES = 1 << 20


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
    on_listen: Callable[[str], None] | None = None,
) -> None:
    """Start a gRPC server on the given transport URI.

    Native gRPC python transports: tcp://, unix://
    Bridged transports: stdio://, mem://
    """
    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=max_workers),
        options=[
            ("grpc.max_receive_message_length", _MAX_GRPC_MESSAGE_BYTES),
            ("grpc.max_send_message_length", _MAX_GRPC_MESSAGE_BYTES),
        ],
    )
    register_fn(server)

    reflection_enabled = False
    if reflect:
        reflection.enable_server_reflection((reflection.SERVICE_NAME,), server)
        reflection_enabled = True

    transport = scheme(listen_uri)
    mem_key = None
    stdio_bridge = None

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
    elif transport == "stdio":
        # Bridge stdin/stdout to a temp Unix socket that grpcio can listen on
        stdio_bridge = _StdioServeBridge()
        sock_path = stdio_bridge.start()
        server.add_insecure_port(f"unix:{sock_path}")
        actual_uri = "stdio://"
    else:
        raise ValueError(
            "gRPC Python server supports tcp://, unix://, mem://, and stdio:// "
            f"in run_with_options(). For {transport}://, use holons.transport.listen() "
            "with a custom server loop."
        )

    mode = "reflection ON" if reflection_enabled else "reflection OFF"
    if on_listen is not None:
        on_listen(actual_uri)
    logger.info("gRPC server listening on %s (%s)", actual_uri, mode)

    server.start()

    # For stdio, start bridging after the server is ready
    if stdio_bridge is not None:
        stdio_bridge.connect_to_server()

    def _shutdown(*_args):
        logger.info("shutting down gRPC server")
        server.stop(10)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    print(f"gRPC server listening on {actual_uri} ({mode})", file=sys.stderr)

    try:
        server.wait_for_termination()
    finally:
        if mem_key:
            unregister_mem_endpoint(mem_key)
        if stdio_bridge is not None:
            stdio_bridge.close()


class _StdioServeBridge:
    """Bridge stdin/stdout to a Unix socket for grpcio server-side stdio.

    grpcio's Python binding cannot accept raw file descriptors, so we
    create a temporary Unix socket, make grpcio listen on it, then
    forward bytes between stdin/stdout and the socket.
    """

    def __init__(self) -> None:
        self._sock_dir: str | None = None
        self._sock_path: str | None = None
        self._conn: socket.socket | None = None
        self._closed = threading.Event()
        self._stdin_fd = os.dup(0)
        self._stdout_fd = os.dup(1)
        # Redirect stdout to stderr so print() doesn't corrupt the data channel
        os.dup2(2, 1)

    def start(self) -> str:
        """Create the Unix socket path (does not connect yet)."""
        self._sock_dir = tempfile.mkdtemp(prefix="holons-stdio-serve-")
        self._sock_path = os.path.join(self._sock_dir, "bridge.sock")
        return self._sock_path

    def connect_to_server(self) -> None:
        """Connect to the grpcio Unix socket and start bridging threads."""
        assert self._sock_path is not None

        # Retry connecting — grpcio may not be listening yet
        conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        for attempt in range(20):
            try:
                conn.connect(self._sock_path)
                break
            except (ConnectionRefusedError, FileNotFoundError):
                import time
                time.sleep(0.05)
        else:
            raise RuntimeError("failed to connect to grpcio Unix socket")
        self._conn = conn

        # stdin → socket (client data arriving on stdin goes to grpc server)
        t1 = threading.Thread(target=self._stdin_to_socket, daemon=True)
        t1.start()

        # socket → stdout (grpc server responses go out on stdout)
        t2 = threading.Thread(target=self._socket_to_stdout, daemon=True)
        t2.start()

    def close(self) -> None:
        if self._closed.is_set():
            return
        self._closed.set()

        conn = self._conn
        self._conn = None
        if conn is not None:
            try:
                conn.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                conn.close()
            except OSError:
                pass

        for fd in (self._stdin_fd, self._stdout_fd):
            try:
                os.close(fd)
            except OSError:
                pass

        if self._sock_path:
            try:
                os.unlink(self._sock_path)
            except OSError:
                pass
        if self._sock_dir:
            shutil.rmtree(self._sock_dir, ignore_errors=True)

    def _stdin_to_socket(self) -> None:
        """Forward bytes from stdin to the Unix socket."""
        conn = self._conn
        assert conn is not None

        while not self._closed.is_set():
            try:
                data = os.read(self._stdin_fd, 64 * 1024)
            except OSError:
                break
            if not data:
                break
            try:
                conn.sendall(data)
            except OSError:
                break

        # EOF on stdin — shut down the write side of the socket
        try:
            conn.shutdown(socket.SHUT_WR)
        except OSError:
            pass

        # Stdin closed means the parent process disconnected; trigger shutdown
        os.kill(os.getpid(), signal.SIGTERM)

    def _socket_to_stdout(self) -> None:
        """Forward bytes from the Unix socket to stdout."""
        conn = self._conn
        assert conn is not None

        while not self._closed.is_set():
            try:
                data = conn.recv(64 * 1024)
            except OSError:
                break
            if not data:
                break
            try:
                os.write(self._stdout_fd, data)
            except OSError:
                break
