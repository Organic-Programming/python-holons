"""Tests for holons.serve — flag parsing."""

from holons.serve import parse_flags
from holons.transport import DEFAULT_URI


def test_parse_listen():
    assert parse_flags(["--listen", "tcp://:8080"]) == "tcp://:8080"


def test_parse_port():
    assert parse_flags(["--port", "3000"]) == "tcp://:3000"


def test_parse_default():
    assert parse_flags([]) == DEFAULT_URI
    assert parse_flags(["--verbose"]) == DEFAULT_URI


def test_parse_listen_mem():
    assert parse_flags(["--listen", "mem://"]) == "mem://"
