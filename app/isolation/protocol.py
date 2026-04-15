"""
app.isolation.protocol — Length-prefixed JSON frame protocol.

Wire format::

    +----------------+----------------+--------------------------+
    | 4-byte tot_len | 4-byte chan_id |  UTF-8 JSON payload      |
    +----------------+----------------+--------------------------+

- ``tot_len`` is an unsigned 32-bit big-endian integer giving the
  number of bytes that follow (= 4 + len(json_body)). A single
  ``read(tot_len)`` brings the chan_id and body into memory
  together.
- ``chan_id`` is an unsigned 32-bit big-endian integer. It
  identifies which logical worker on a shared transport this frame
  belongs to. For the single-worker stdio case it is always 0. For
  multiplexed TCP connections between main and a remote NodeAgent
  it routes a frame to one of several worker subprocesses behind
  that connection. The worker subprocess itself always uses
  chan_id=0 in its outbound frames — stamping the real id is the
  NodeAgent's job when it relays bytes up to main.
- ``JSON payload`` is a UTF-8 encoded JSON object. The ``kind``
  field decides the shape of the rest of the object. See
  FrameKind below.

Max frame size (json body only) is capped at MAX_FRAME_BYTES to
stop runaway memory use on a wedged worker.

Frame kinds
-----------

REQUEST   (main -> worker):  {kind:"req",  id, method, params}
                            Ask the worker to perform something
                            (usually `tool_call`). Worker replies with
                            exactly one `resp` frame carrying the same
                            `id`.

RESPONSE  (worker -> main):  {kind:"resp", id, ok, result?, error?}
                            Terminal reply to a request.

NOTIFY    (main -> worker):  {kind:"notify", kind2, payload}
                            Fire-and-forget push from main process to
                            worker. Used for capability updates
                            (new MCP binding, granted skill, policy
                            change, reload config...). Worker must
                            not reply.

EVENT     (worker -> main):  {kind:"event", kind2, payload}
                            Worker-initiated message that is NOT a
                            reply to a request. Used for log lines,
                            heartbeats, telemetry. Main process can
                            consume them without blocking.

GATEKEEPER (worker -> main): {kind:"gate", id, action, params}
                            Special request from worker to main asking
                            permission for a cross-boundary action
                            (unknown bash command, mcp call, shared
                            dir access, pip install...). Main replies
                            with a `gate_resp` frame carrying the same
                            id. Separating this from `req` lets the
                            protocol handle the two flow directions
                            without id collisions.

GATE_RESP (main -> worker):  {kind:"gate_resp", id, ok, result?, error?}
                            Main's decision on a gatekeeper request.

Design notes
------------

- `id` is an opaque string chosen by the sender. Main-process requests
  use monotonically increasing integers as strings. Worker gatekeeper
  requests use `g-<n>`. IDs from different directions live in separate
  namespaces to avoid collision.
- Encoding errors and oversized frames raise ProtocolError. The caller
  is expected to treat a ProtocolError from read_frame as a
  non-recoverable worker crash and tear the worker down.
- This module must stay dependency-free (stdlib only) so agent_worker
  can import it in a fresh interpreter.
"""
from __future__ import annotations

import io
import json
import struct
from dataclasses import dataclass, field
from typing import Any, BinaryIO, Dict, Optional

FRAME_VERSION = 1
MAX_FRAME_BYTES = 64 * 1024 * 1024   # 64 MiB hard cap on JSON body
_HEADER = struct.Struct(">I")        # tot_len prefix
_CHAN = struct.Struct(">I")          # chan_id

# Default channel id used on exclusive-per-worker transports (local
# stdio, or one-TCP-per-worker). Multiplexed network transports
# override this with their own per-worker ids.
DEFAULT_CHAN_ID = 0


class FrameKind:
    REQUEST = "req"
    RESPONSE = "resp"
    NOTIFY = "notify"
    EVENT = "event"
    GATE = "gate"
    GATE_RESP = "gate_resp"


class ProtocolError(Exception):
    """Raised when the wire-level framing is corrupt or truncated."""


@dataclass
class Frame:
    """In-memory representation of one protocol frame."""

    kind: str
    id: Optional[str] = None
    method: Optional[str] = None        # used by REQUEST / GATE
    params: Dict[str, Any] = field(default_factory=dict)
    ok: Optional[bool] = None           # used by RESPONSE / GATE_RESP
    result: Any = None                  # used by RESPONSE / GATE_RESP
    error: Optional[Dict[str, Any]] = None  # used by RESPONSE / GATE_RESP
    kind2: Optional[str] = None         # subtype used by NOTIFY / EVENT
    payload: Dict[str, Any] = field(default_factory=dict)

    # ------------- factory helpers -------------

    @classmethod
    def request(cls, id: str, method: str, params: Optional[Dict[str, Any]] = None) -> "Frame":
        return cls(kind=FrameKind.REQUEST, id=id, method=method, params=dict(params or {}))

    @classmethod
    def response_ok(cls, id: str, result: Any) -> "Frame":
        return cls(kind=FrameKind.RESPONSE, id=id, ok=True, result=result)

    @classmethod
    def response_err(cls, id: str, error_type: str, message: str,
                     details: Optional[Dict[str, Any]] = None) -> "Frame":
        err = {"type": error_type, "message": message}
        if details:
            err["details"] = details
        return cls(kind=FrameKind.RESPONSE, id=id, ok=False, error=err)

    @classmethod
    def notify(cls, kind2: str, payload: Optional[Dict[str, Any]] = None) -> "Frame":
        return cls(kind=FrameKind.NOTIFY, kind2=kind2, payload=dict(payload or {}))

    @classmethod
    def event(cls, kind2: str, payload: Optional[Dict[str, Any]] = None) -> "Frame":
        return cls(kind=FrameKind.EVENT, kind2=kind2, payload=dict(payload or {}))

    @classmethod
    def gate(cls, id: str, action: str, params: Optional[Dict[str, Any]] = None) -> "Frame":
        return cls(kind=FrameKind.GATE, id=id, method=action, params=dict(params or {}))

    @classmethod
    def gate_resp_ok(cls, id: str, result: Any = None) -> "Frame":
        return cls(kind=FrameKind.GATE_RESP, id=id, ok=True, result=result)

    @classmethod
    def gate_resp_err(cls, id: str, error_type: str, message: str,
                      details: Optional[Dict[str, Any]] = None) -> "Frame":
        err = {"type": error_type, "message": message}
        if details:
            err["details"] = details
        return cls(kind=FrameKind.GATE_RESP, id=id, ok=False, error=err)

    # ------------- serialization -------------

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {"kind": self.kind, "v": FRAME_VERSION}
        if self.id is not None:
            d["id"] = self.id
        if self.kind in (FrameKind.REQUEST, FrameKind.GATE):
            d["method"] = self.method
            d["params"] = self.params
        elif self.kind in (FrameKind.RESPONSE, FrameKind.GATE_RESP):
            d["ok"] = bool(self.ok)
            if self.ok:
                d["result"] = self.result
            else:
                d["error"] = self.error or {"type": "unknown", "message": ""}
        elif self.kind in (FrameKind.NOTIFY, FrameKind.EVENT):
            d["kind2"] = self.kind2
            d["payload"] = self.payload
        else:
            raise ProtocolError(f"Unknown frame kind: {self.kind!r}")
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Frame":
        if not isinstance(d, dict):
            raise ProtocolError(f"Frame payload must be object, got {type(d).__name__}")
        kind = d.get("kind")
        if kind not in (FrameKind.REQUEST, FrameKind.RESPONSE, FrameKind.NOTIFY,
                        FrameKind.EVENT, FrameKind.GATE, FrameKind.GATE_RESP):
            raise ProtocolError(f"Unknown frame kind: {kind!r}")
        f = cls(kind=kind)
        f.id = d.get("id")
        if kind in (FrameKind.REQUEST, FrameKind.GATE):
            f.method = d.get("method")
            f.params = d.get("params") or {}
            if not isinstance(f.method, str):
                raise ProtocolError("request/gate frame missing 'method'")
            if not isinstance(f.params, dict):
                raise ProtocolError("request/gate frame 'params' must be object")
        elif kind in (FrameKind.RESPONSE, FrameKind.GATE_RESP):
            f.ok = bool(d.get("ok"))
            if f.ok:
                f.result = d.get("result")
            else:
                err = d.get("error") or {}
                if not isinstance(err, dict):
                    err = {"type": "unknown", "message": str(err)}
                f.error = err
        elif kind in (FrameKind.NOTIFY, FrameKind.EVENT):
            f.kind2 = d.get("kind2")
            f.payload = d.get("payload") or {}
            if not isinstance(f.kind2, str):
                raise ProtocolError("notify/event frame missing 'kind2'")
            if not isinstance(f.payload, dict):
                raise ProtocolError("notify/event frame 'payload' must be object")
        return f


# ---------------------------------------------------------------------------
# encode / decode
# ---------------------------------------------------------------------------

def encode_frame(frame: Frame, chan_id: int = DEFAULT_CHAN_ID) -> bytes:
    """Serialize a Frame to bytes with the tot_len + chan_id header."""
    try:
        body = json.dumps(frame.to_dict(), ensure_ascii=False,
                          separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError) as e:
        raise ProtocolError(f"Frame encode failed: {e}") from e
    if len(body) > MAX_FRAME_BYTES:
        raise ProtocolError(
            f"Frame too large: {len(body)} bytes > {MAX_FRAME_BYTES}")
    if chan_id < 0 or chan_id > 0xFFFFFFFF:
        raise ProtocolError(f"chan_id out of range: {chan_id}")
    tot_len = 4 + len(body)
    return _HEADER.pack(tot_len) + _CHAN.pack(chan_id) + body


def decode_frame(data: bytes) -> Frame:
    """Parse a JSON body (no length/chan header) back into a Frame."""
    try:
        obj = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise ProtocolError(f"Frame decode failed: {e}") from e
    return Frame.from_dict(obj)


def _read_exact(stream: BinaryIO, n: int) -> bytes:
    """Read exactly n bytes from stream, raising on short read."""
    buf = bytearray()
    while len(buf) < n:
        chunk = stream.read(n - len(buf))
        if not chunk:
            raise ProtocolError(
                f"Short read: wanted {n} bytes, got {len(buf)} before EOF")
        buf.extend(chunk)
    return bytes(buf)


def read_frame(stream: BinaryIO) -> tuple[int, Frame]:
    """Read one (chan_id, Frame) tuple from a binary stream.

    Blocks until a full frame has arrived. Raises ProtocolError on
    EOF / truncation / oversized frame / malformed JSON.
    """
    header = _read_exact(stream, 4)
    (tot_len,) = _HEADER.unpack(header)
    if tot_len < 4:
        raise ProtocolError(
            f"Frame too small: tot_len={tot_len} < 4 (missing chan_id)")
    body_len = tot_len - 4
    if body_len > MAX_FRAME_BYTES:
        raise ProtocolError(
            f"Oversized frame: body {body_len} bytes > max {MAX_FRAME_BYTES}")
    rest = _read_exact(stream, tot_len)
    (chan_id,) = _CHAN.unpack(rest[:4])
    frame = decode_frame(rest[4:])
    return chan_id, frame


def write_frame(stream: BinaryIO, frame: Frame,
                chan_id: int = DEFAULT_CHAN_ID) -> None:
    """Serialize and write one Frame on the given chan_id. Flushes the
    stream after writing so the peer sees the frame immediately."""
    stream.write(encode_frame(frame, chan_id))
    try:
        stream.flush()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# convenience helpers exposed for tests / debugging
# ---------------------------------------------------------------------------

def roundtrip(frame: Frame, chan_id: int = DEFAULT_CHAN_ID) -> tuple[int, Frame]:
    """Encode and decode a frame via a BytesIO buffer. Purely for tests."""
    buf = io.BytesIO()
    write_frame(buf, frame, chan_id)
    buf.seek(0)
    return read_frame(buf)
