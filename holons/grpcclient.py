from __future__ import annotations

"""Client-side gRPC helpers for Python holons."""

import asyncio
import socket
import threading
from typing import Any, Callable

import grpc
import websockets
from websockets.exceptions import ConnectionClosed

from holons.transport import parse_uri
from holons.runtime_state import resolve_mem_endpoint, normalize_mem_uri


class _ManagedChannel(grpc.Channel):
    """grpc.Channel wrapper that can run transport cleanup on close()."""

    def __init__(self, inner: grpc.Channel, on_close: Callable[[], None] | None = None):
        self._inner = inner
        self._on_close = on_close
        self._closed = False

    def subscribe(self, callback: Any, try_to_connect: bool = False) -> None:
        self._inner.subscribe(callback, try_to_connect=try_to_connect)

    def unsubscribe(self, callback: Any) -> None:
        self._inner.unsubscribe(callback)

    def unary_unary(self, *args: Any, **kwargs: Any):
        return self._inner.unary_unary(*args, **kwargs)

    def unary_stream(self, *args: Any, **kwargs: Any):
        return self._inner.unary_stream(*args, **kwargs)

    def stream_unary(self, *args: Any, **kwargs: Any):
        return self._inner.stream_unary(*args, **kwargs)

    def stream_stream(self, *args: Any, **kwargs: Any):
        return self._inner.stream_stream(*args, **kwargs)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self._inner.close()
        finally:
            if self._on_close is not None:
                self._on_close()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


class _WSDialProxy:
    """Local TCP proxy that tunnels bytes to a grpc-subprotocol WebSocket."""

    def __init__(self, uri: str):
        self._uri = uri
        self._listen_socket: socket.socket | None = None
        self._accept_thread: threading.Thread | None = None
        self._closed = threading.Event()
        self._connections: set[socket.socket] = set()
        self._lock = threading.Lock()
        self.target: str | None = None

    def start(self) -> str:
        if self.target:
            return self.target

        listen = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listen.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listen.bind(("127.0.0.1", 0))
        listen.listen(16)
        listen.settimeout(0.2)

        self._listen_socket = listen
        host, port = listen.getsockname()
        self.target = f"{host}:{port}"

        self._accept_thread = threading.Thread(target=self._accept_loop, daemon=True)
        self._accept_thread.start()
        return self.target

    def close(self) -> None:
        if self._closed.is_set():
            return
        self._closed.set()

        if self._listen_socket is not None:
            try:
                self._listen_socket.close()
            except OSError:
                pass
            self._listen_socket = None

        with self._lock:
            conns = list(self._connections)
            self._connections.clear()

        for conn in conns:
            try:
                conn.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                conn.close()
            except OSError:
                pass

    def _accept_loop(self) -> None:
        assert self._listen_socket is not None

        while not self._closed.is_set():
            try:
                conn, _ = self._listen_socket.accept()
            except socket.timeout:
                continue
            except OSError:
                break

            with self._lock:
                self._connections.add(conn)

            worker = threading.Thread(target=self._bridge_worker, args=(conn,), daemon=True)
            worker.start()

    def _bridge_worker(self, conn: socket.socket) -> None:
        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self._bridge_connection(conn))
        except Exception:
            pass
        finally:
            try:
                conn.close()
            except OSError:
                pass
            with self._lock:
                self._connections.discard(conn)
            try:
                loop.close()
            except Exception:
                pass

    async def _bridge_connection(self, conn: socket.socket) -> None:
        conn.setblocking(False)
        loop = asyncio.get_running_loop()

        async with websockets.connect(
            self._uri,
            subprotocols=["grpc"],
            ping_interval=None,
            ping_timeout=None,
            max_size=None,
        ) as ws:

            async def tcp_to_ws() -> None:
                while not self._closed.is_set():
                    data = await loop.sock_recv(conn, 64 * 1024)
                    if not data:
                        await ws.close(code=1000, reason="tcp closed")
                        return
                    await ws.send(data)

            async def ws_to_tcp() -> None:
                try:
                    async for msg in ws:
                        if isinstance(msg, str):
                            data = msg.encode("utf-8")
                        else:
                            data = bytes(msg)
                        if data:
                            await loop.sock_sendall(conn, data)
                except ConnectionClosed:
                    return

            tasks = [
                asyncio.create_task(tcp_to_ws()),
                asyncio.create_task(ws_to_tcp()),
            ]

            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in pending:
                task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
            for task in done:
                _ = task.exception() if not task.cancelled() else None


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


def dial_websocket(uri: str) -> grpc.Channel:
    """Dial gRPC over ws:// or wss:// using a local TCP bridge."""
    parsed = parse_uri(uri)
    if parsed.scheme not in {"ws", "wss"}:
        raise ValueError(f"dial_websocket expects ws:// or wss:// URI, got {uri!r}")

    proxy = _WSDialProxy(parsed.raw)
    target = proxy.start()
    channel = grpc.insecure_channel(target)
    return _ManagedChannel(channel, on_close=proxy.close)


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

    if parsed.scheme in {"ws", "wss"}:
        return dial_websocket(parsed.raw)

    raise ValueError(
        f"dial_uri() supports tcp://, unix://, mem://, ws://, and wss://. "
        f"Use transport-specific clients for {parsed.scheme}://"
    )
