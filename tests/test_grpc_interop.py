"""Cross-language gRPC interop tests against a Go server."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import shutil
import subprocess
import tempfile
import textwrap
from typing import Iterator

import pytest
from grpc_reflection.v1alpha import reflection_pb2, reflection_pb2_grpc

from holons.grpcclient import dial_uri


GO_GRPC_REFLECTION_SERVER = r'''
package main

import (
	"context"
	"fmt"
	"net"
	"os"
	"os/signal"
	"syscall"
	"time"

	"google.golang.org/grpc"
	"google.golang.org/grpc/reflection"
)

func main() {
	lis, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		panic(err)
	}
	defer lis.Close()

	srv := grpc.NewServer()
	reflection.Register(srv)

	go func() {
		_ = srv.Serve(lis)
	}()

	fmt.Printf("tcp://%s\n", lis.Addr().String())

	sigCh := make(chan os.Signal, 1)
	signal.Notify(sigCh, syscall.SIGTERM, syscall.SIGINT)
	<-sigCh

	done := make(chan struct{})
	go func() {
		srv.GracefulStop()
		close(done)
	}()

	select {
	case <-done:
	case <-time.After(2 * time.Second):
		srv.Stop()
	}

	ctx, cancel := context.WithTimeout(context.Background(), time.Second)
	defer cancel()
	_ = ctx
}
'''


GO_GRPC_REFLECTION_WS_SERVER = r'''
package main

import (
	"context"
	"fmt"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/organic-programming/go-holons/pkg/transport"
	"google.golang.org/grpc"
	"google.golang.org/grpc/reflection"
)

func main() {
	lis, err := transport.Listen("ws://127.0.0.1:0/grpc")
	if err != nil {
		panic(err)
	}
	defer lis.Close()

	srv := grpc.NewServer()
	reflection.Register(srv)

	go func() {
		_ = srv.Serve(lis)
	}()

	fmt.Printf("%s\n", lis.Addr().String())

	sigCh := make(chan os.Signal, 1)
	signal.Notify(sigCh, syscall.SIGTERM, syscall.SIGINT)
	<-sigCh

	done := make(chan struct{})
	go func() {
		srv.GracefulStop()
		close(done)
	}()

	select {
	case <-done:
	case <-time.After(2 * time.Second):
		srv.Stop()
	}

	ctx, cancel := context.WithTimeout(context.Background(), time.Second)
	defer cancel()
	_ = ctx
}
'''


def _resolve_go_binary() -> str:
    preferred = Path("/Users/bpds/go/go1.25.1/bin/go")
    if preferred.exists():
        return str(preferred)
    found = shutil.which("go")
    if not found:
        raise RuntimeError("go binary not found")
    return found


def _is_bind_denied(stderr: str) -> bool:
    text = stderr.lower()
    return "bind" in text and "operation not permitted" in text


@contextmanager
def _run_go_grpc_server() -> Iterator[str]:
    go_bin = _resolve_go_binary()
    sdk_dir = Path(__file__).resolve().parents[2]
    go_holons_dir = sdk_dir / "go-holons"

    with tempfile.NamedTemporaryFile("w", suffix=".go", dir=go_holons_dir, delete=False) as f:
        f.write(textwrap.dedent(GO_GRPC_REFLECTION_SERVER))
        helper_path = Path(f.name)

    proc = subprocess.Popen(
        [go_bin, "run", str(helper_path)],
        cwd=go_holons_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        assert proc.stdout is not None
        uri = proc.stdout.readline().strip()
        if not uri:
            stderr = ""
            if proc.stderr is not None:
                stderr = proc.stderr.read()
            if _is_bind_denied(stderr):
                pytest.skip("local bind denied in this environment")
            raise RuntimeError(f"failed to start Go gRPC helper: {stderr}")
        yield uri
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
        helper_path.unlink(missing_ok=True)


@contextmanager
def _run_go_grpc_ws_server() -> Iterator[str]:
    go_bin = _resolve_go_binary()
    sdk_dir = Path(__file__).resolve().parents[2]
    go_holons_dir = sdk_dir / "go-holons"

    with tempfile.NamedTemporaryFile("w", suffix=".go", dir=go_holons_dir, delete=False) as f:
        f.write(textwrap.dedent(GO_GRPC_REFLECTION_WS_SERVER))
        helper_path = Path(f.name)

    proc = subprocess.Popen(
        [go_bin, "run", str(helper_path)],
        cwd=go_holons_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        assert proc.stdout is not None
        uri = proc.stdout.readline().strip()
        if not uri:
            stderr = ""
            if proc.stderr is not None:
                stderr = proc.stderr.read()
            if _is_bind_denied(stderr):
                pytest.skip("local bind denied in this environment")
            raise RuntimeError(f"failed to start Go gRPC ws helper: {stderr}")
        yield uri
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
        helper_path.unlink(missing_ok=True)


def test_grpc_cross_language_reflection_roundtrip():
    with _run_go_grpc_server() as uri:
        ch = dial_uri(uri)
        try:
            stub = reflection_pb2_grpc.ServerReflectionStub(ch)
            req = reflection_pb2.ServerReflectionRequest(
                list_services="",
            )
            stream = stub.ServerReflectionInfo(iter([req]))
            resp = next(stream)
            services = [svc.name for svc in resp.list_services_response.service]
            assert "grpc.reflection.v1alpha.ServerReflection" in services
        finally:
            ch.close()


def test_grpc_cross_language_reflection_roundtrip_ws():
    with _run_go_grpc_ws_server() as uri:
        ch = dial_uri(uri)
        try:
            stub = reflection_pb2_grpc.ServerReflectionStub(ch)
            req = reflection_pb2.ServerReflectionRequest(
                list_services="",
            )
            stream = stub.ServerReflectionInfo(iter([req]))
            resp = next(stream)
            services = [svc.name for svc in resp.list_services_response.service]
            assert "grpc.reflection.v1alpha.ServerReflection" in services
        finally:
            ch.close()
