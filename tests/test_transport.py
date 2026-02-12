"""Tests for holons.transport — listener factory."""

import socket

from holons.transport import listen, scheme, MemListener, DEFAULT_URI


def test_scheme_extraction():
    assert scheme("tcp://:9090") == "tcp"
    assert scheme("unix:///tmp/x.sock") == "unix"
    assert scheme("stdio://") == "stdio"
    assert scheme("mem://") == "mem"
    assert scheme("ws://host:8080") == "ws"
    assert scheme("wss://host:443") == "wss"


def test_default_uri():
    assert DEFAULT_URI == "tcp://:9090"


def test_tcp_listen():
    sock = listen("tcp://127.0.0.1:0")
    try:
        assert isinstance(sock, socket.socket)
        addr = sock.getsockname()
        assert addr[0] == "127.0.0.1"
        assert addr[1] > 0  # ephemeral port
    finally:
        sock.close()


def test_unix_listen():
    import tempfile, os
    path = os.path.join(tempfile.gettempdir(), "holons_test.sock")
    sock = listen(f"unix://{path}")
    try:
        assert isinstance(sock, socket.socket)
    finally:
        sock.close()


def test_mem_listener_roundtrip():
    mem = MemListener()
    client = mem.dial()
    server = mem.accept(timeout=1.0)

    client.sendall(b"hello")
    data = server.recv(1024)
    assert data == b"hello"

    server.sendall(b"world")
    data = client.recv(1024)
    assert data == b"world"

    client.close()
    server.close()
    mem.close()


def test_mem_listen_via_uri():
    lis = listen("mem://")
    assert isinstance(lis, MemListener)
    lis.close()


def test_unsupported_uri():
    try:
        listen("ftp://host")
        assert False, "should have raised"
    except ValueError as e:
        assert "unsupported" in str(e)
