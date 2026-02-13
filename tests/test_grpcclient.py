"""Tests for holons.grpcclient."""

import grpc

from holons.grpcclient import dial, dial_mem, dial_stdio, dial_uri, dial_websocket
from holons.runtime_state import register_mem_endpoint, unregister_mem_endpoint


def test_dial_tcp_address():
    ch = dial("127.0.0.1:9090")
    try:
        assert isinstance(ch, grpc.Channel)
    finally:
        ch.close()


def test_dial_uri_tcp():
    ch = dial_uri("tcp://127.0.0.1:9090")
    try:
        assert isinstance(ch, grpc.Channel)
    finally:
        ch.close()


def test_dial_mem_registered_endpoint():
    key = register_mem_endpoint("mem://test", "127.0.0.1:19090")
    try:
        ch = dial_mem(key)
        assert isinstance(ch, grpc.Channel)
        ch.close()
    finally:
        unregister_mem_endpoint(key)


def test_dial_mem_missing_endpoint():
    try:
        dial_mem("mem://missing")
        assert False, "should have raised"
    except ValueError as e:
        assert "no mem endpoint" in str(e)


def test_dial_uri_unsupported_scheme():
    try:
        dial_uri("ftp://127.0.0.1:21")
        assert False, "should have raised"
    except ValueError as e:
        assert "unsupported transport URI" in str(e)


def test_dial_websocket_requires_ws_scheme():
    try:
        dial_websocket("tcp://127.0.0.1:9090")
        assert False, "should have raised"
    except ValueError as e:
        assert "expects ws:// or wss://" in str(e)


def test_dial_stdio_not_implemented():
    try:
        dial_stdio("python", "fake-holon.py")
        assert False, "should have raised"
    except NotImplementedError as e:
        assert "no public stdio transport adapter" in str(e)
