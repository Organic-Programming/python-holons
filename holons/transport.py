from __future__ import annotations

"""URI-based listener factory for gRPC servers.

Supported transport URIs:
    tcp://<host>:<port>   — TCP socket (default: tcp://:9090)
    unix://<path>         — Unix domain socket
    stdio://              — stdin/stdout pipe (single connection)
    mem://                — in-process pipe (testing, composite holons)
    ws://<host>:<port>    — WebSocket
    wss://<host>:<port>   — WebSocket over TLS
"""

import os
import queue
import socket
import threading
from typing import Tuple

DEFAULT_URI = "tcp://:9090"


def listen(uri: str) -> socket.socket:
    """Parse a transport URI and return a bound server socket.

    For non-socket transports (stdio, mem, ws), returns a wrapper
    that behaves like a socket for gRPC's add_insecure_port or
    custom server loops.
    """
    if uri.startswith("tcp://"):
        return _listen_tcp(uri[6:])
    elif uri.startswith("unix://"):
        return _listen_unix(uri[7:])
    elif uri in ("stdio://", "stdio"):
        return _StdioListener()
    elif uri.startswith("mem://"):
        return MemListener()
    elif uri.startswith("ws://") or uri.startswith("wss://"):
        return _listen_ws(uri)
    else:
        raise ValueError(
            f"unsupported transport URI: {uri!r} "
            "(expected tcp://, unix://, stdio://, mem://, or ws://)"
        )


def scheme(uri: str) -> str:
    """Extract the transport scheme from a URI."""
    idx = uri.find("://")
    return uri[:idx] if idx >= 0 else uri


# --- TCP ---

def _listen_tcp(addr: str) -> socket.socket:
    host, _, port = addr.rpartition(":")
    if not host:
        host = "0.0.0.0"
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((host, int(port)))
    sock.listen(128)
    return sock


# --- Unix ---

def _listen_unix(path: str) -> socket.socket:
    # Clean stale socket
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.bind(path)
    sock.listen(128)
    return sock


# --- Stdio ---

class _StdioListener:
    """Wraps stdin/stdout as a single-connection listener.

    gRPC Python doesn't support custom listeners directly, so this
    exposes the file descriptors for use with a custom server loop.
    """

    def __init__(self):
        self.stdin_fd = os.dup(0)
        self.stdout_fd = os.dup(1)
        self._consumed = False

    def accept(self) -> Tuple[int, int]:
        """Return (read_fd, write_fd) for the single connection."""
        if self._consumed:
            raise StopIteration("stdio listener is single-use")
        self._consumed = True
        return self.stdin_fd, self.stdout_fd

    def close(self):
        os.close(self.stdin_fd)
        os.close(self.stdout_fd)

    def fileno(self):
        return self.stdin_fd

    @property
    def address(self) -> str:
        return "stdio://"


# --- Mem (in-process) ---

class MemListener:
    """In-process listener using socket pairs for testing.

    Creates connected socket pairs on demand — both server and client
    live in the same process.
    """

    def __init__(self):
        self._server_sockets = queue.Queue()
        self._closed = False

    def dial(self) -> socket.socket:
        """Client side: create a connection to the in-process server."""
        if self._closed:
            raise ConnectionError("mem listener is closed")
        client, server = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
        self._server_sockets.put(server)
        return client

    def accept(self, timeout: float = None) -> socket.socket:
        """Server side: accept the next in-process connection."""
        try:
            return self._server_sockets.get(timeout=timeout)
        except queue.Empty:
            raise TimeoutError("no connection available")

    def close(self):
        self._closed = True

    @property
    def address(self) -> str:
        return "mem://"


# --- WebSocket ---

def _listen_ws(uri: str):
    """Start a WebSocket listener using the websockets library.

    Returns a WSListener that wraps accepted WebSocket connections
    as bidirectional byte streams compatible with gRPC.
    """
    return WSListener(uri)


class WSListener:
    """WebSocket listener that adapts WS connections for gRPC."""

    def __init__(self, uri: str):
        self.uri = uri
        self.is_tls = uri.startswith("wss://")
        trimmed = uri.replace("wss://", "").replace("ws://", "")

        # Split host:port from path
        if "/" in trimmed:
            addr, self.path = trimmed.split("/", 1)
            self.path = "/" + self.path
        else:
            addr = trimmed
            self.path = "/grpc"

        host, _, port = addr.rpartition(":")
        self.host = host or "0.0.0.0"
        self.port = int(port)
        self._connections = queue.Queue()
        self._server = None
        self._thread = None

    def start(self):
        """Start the WebSocket server in a background thread."""
        import asyncio
        import websockets.server

        async def _handler(websocket):
            """Accept a WS connection, wrap it, put it in the queue."""
            self._connections.put(websocket)
            # Keep connection alive until closed
            try:
                await websocket.wait_closed()
            except Exception:
                pass

        async def _serve():
            self._server = await websockets.server.serve(
                _handler,
                self.host,
                self.port,
                subprotocols=["grpc"],
            )
            # Update port if ephemeral
            for s in self._server.sockets:
                addr = s.getsockname()
                self.port = addr[1]
                break
            await self._server.wait_closed()

        def _run():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(_serve())

        self._thread = threading.Thread(target=_run, daemon=True)
        self._thread.start()

    def accept(self, timeout: float = 5.0):
        """Accept the next WebSocket connection."""
        return self._connections.get(timeout=timeout)

    def close(self):
        if self._server:
            self._server.close()

    @property
    def address(self) -> str:
        scheme = "wss" if self.is_tls else "ws"
        return f"{scheme}://{self.host}:{self.port}{self.path}"
