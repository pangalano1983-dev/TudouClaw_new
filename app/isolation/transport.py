"""
app.isolation.transport — Byte-level transport abstraction.

A ``Transport`` is the minimum byte-level channel WorkerChannel needs
in order to talk to a worker. It hides whether the other side is a
local subprocess reached via stdio pipes (``StdioTransport``) or a
remote worker reached via a TLS TCP socket going through a NodeAgent
(``SocketTransport``, added in Layer 1b).

Contract
--------

- ``send(frame, chan_id)``: thread-safe. Serializes and writes one
  frame. Raises TransportError on write failure (broken pipe,
  socket reset, etc.).
- ``recv() -> (chan_id, frame)``: blocking. Only called from the
  single reader thread inside WorkerChannel. Raises
  ProtocolError on framing corruption, TransportError on EOF /
  connection loss.
- ``close()``: idempotent shutdown.
- ``describe()``: short human-readable string for logs.

Transports are 1:1 with a logical "wire" between main and worker(s):

- LOCAL / single-worker: one Transport per WorkerChannel, chan_id
  is always 0. ``StdioTransport``.
- REMOTE / multiplexed: one Transport per TCP connection to a
  NodeAgent, many WorkerChannels sharing it via chan_id. A
  ``MultiplexedChannelRouter`` (Layer 1b) sits between a shared
  Transport and N WorkerChannels.

Keeping this module dependency-light so it can be imported anywhere
in the isolation package without pulling in threading-level code.
"""
from __future__ import annotations

import threading
from typing import BinaryIO, Optional, Tuple

from .protocol import (
    DEFAULT_CHAN_ID,
    Frame,
    ProtocolError,
    read_frame,
    write_frame,
)


class TransportError(Exception):
    """Raised when the underlying byte channel is broken (EOF, reset,
    broken pipe). Distinct from ProtocolError which signals that the
    bytes themselves were malformed."""


class Transport:
    """Abstract byte-channel between main and one-or-more workers."""

    def send(self, frame: Frame, chan_id: int = DEFAULT_CHAN_ID) -> None:
        raise NotImplementedError

    def recv(self) -> Tuple[int, Frame]:
        raise NotImplementedError

    def close(self) -> None:
        raise NotImplementedError

    def describe(self) -> str:
        return self.__class__.__name__


# ---------------------------------------------------------------------------
# StdioTransport — local subprocess via two half-duplex pipes
# ---------------------------------------------------------------------------

class StdioTransport(Transport):
    """Transport backed by a subprocess's stdin (write) and stdout
    (read) pipes. Exclusively single-worker; chan_id is always 0 on
    the wire.

    The read side is called from the WorkerChannel reader thread
    only; write side acquires a lock so it stays safe from the
    main-thread ``call`` path and the reader thread's in-flight
    shutdowns.
    """

    def __init__(
        self,
        stdin_w: BinaryIO,
        stdout_r: BinaryIO,
        *,
        label: str = "",
    ) -> None:
        self._stdin_w = stdin_w
        self._stdout_r = stdout_r
        self._write_lock = threading.Lock()
        self._closed = False
        self._label = label or "stdio"

    def send(self, frame: Frame, chan_id: int = DEFAULT_CHAN_ID) -> None:
        if self._closed:
            raise TransportError(f"{self._label}: send on closed transport")
        with self._write_lock:
            try:
                write_frame(self._stdin_w, frame, chan_id)
            except (BrokenPipeError, OSError) as e:
                raise TransportError(
                    f"{self._label}: write failed: {e}") from e

    def recv(self) -> Tuple[int, Frame]:
        if self._closed:
            raise TransportError(f"{self._label}: recv on closed transport")
        try:
            return read_frame(self._stdout_r)
        except ProtocolError:
            raise
        except (BrokenPipeError, OSError) as e:
            raise TransportError(
                f"{self._label}: read failed: {e}") from e

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        for stream in (self._stdin_w, self._stdout_r):
            try:
                stream.close()
            except Exception:
                pass

    def describe(self) -> str:
        return f"StdioTransport({self._label})"


# ---------------------------------------------------------------------------
# SocketTransport — placeholder for Layer 1b
# ---------------------------------------------------------------------------

class SocketTransport(Transport):
    """TLS TCP transport between main process and a remote NodeAgent.

    Layer 1a ships the skeleton so ``WorkerChannel`` never has to
    special-case local vs remote. Layer 1b fills in ``send`` /
    ``recv`` / ``close`` with a real socket + TLS handshake.
    """

    def __init__(self, *, host: str, port: int, tls_context=None,
                 label: str = "") -> None:
        self.host = host
        self.port = port
        self.tls_context = tls_context
        self._label = label or f"{host}:{port}"
        self._sock = None  # populated in connect()

    def connect(self, *, timeout: float = 10.0) -> None:
        raise NotImplementedError("Layer 1b will implement SocketTransport.connect")

    def send(self, frame: Frame, chan_id: int = DEFAULT_CHAN_ID) -> None:
        raise NotImplementedError("Layer 1b will implement SocketTransport.send")

    def recv(self) -> Tuple[int, Frame]:
        raise NotImplementedError("Layer 1b will implement SocketTransport.recv")

    def close(self) -> None:
        self._sock = None

    def describe(self) -> str:
        return f"SocketTransport({self._label})"
