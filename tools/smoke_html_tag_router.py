#!/usr/bin/env python3
"""
Smoke test for app/server/html_tag_router.py.

Drives the router with a fake stdlib-style handler so we don't need
a real HTTP server. Covers:

  * happy path: full GET of an in-deliverable file
  * Range request: partial GET, validates Content-Range + body slice
  * unsatisfiable Range -> 416
  * unknown agent -> 404
  * unknown artifact -> 404
  * non-file kind (RECORD) -> 403
  * I5 violation: file outside deliverable_dir -> 403
  * URL-valued artifact -> 302 redirect
  * URL builder shape

Run from project root:

    python tools/smoke_html_tag_router.py

Exit codes: 0 pass, 1 fail
"""
from __future__ import annotations

import io
import os
import sys
import tempfile
import traceback
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app.agent_state import (  # noqa: E402
    AgentState, ArtifactKind, ProducedBy,
)
from app.agent_state.mime_registry import info_for_value  # noqa: E402
from app.agent_state.shadow import ShadowRecorder, install_into_agent  # noqa: E402
from app.server import html_tag_router  # noqa: E402
from app.server.html_tag_router import build_artifact_url  # noqa: E402


# ----------------------------------------------------------------------
# fakes
# ----------------------------------------------------------------------
class FakeHeaders:
    def __init__(self, h: dict):
        self._h = {k.lower(): v for k, v in h.items()}

    def get(self, k, default=None):
        return self._h.get(k.lower(), default)


class FakeHandler:
    """Minimal stand-in for BaseHTTPRequestHandler.

    Captures status, headers, body so tests can assert on them.
    """
    def __init__(self, headers: dict | None = None):
        self.status = None
        self.resp_headers = []
        self.body = io.BytesIO()
        self.wfile = self.body
        self.headers = FakeHeaders(headers or {})
        self.path = ""
        self._headers_done = False

    def send_response(self, code):
        self.status = code

    def send_header(self, k, v):
        self.resp_headers.append((k, v))

    def end_headers(self):
        self._headers_done = True

    def header(self, name):
        for k, v in self.resp_headers:
            if k.lower() == name.lower():
                return v
        return None


class FakeAgent:
    def __init__(self, agent_id: str, working_dir: str):
        self.id = agent_id
        self.session_id = uuid.uuid4().hex
        self.working_dir = working_dir
        self.mcp_servers = []


class FakeHub:
    """Replaces hub.get_hub() for the duration of a test."""
    def __init__(self):
        self._agents = {}

    def add(self, agent):
        self._agents[agent.id] = agent

    def get_agent(self, agent_id):
        return self._agents.get(agent_id)


# ----------------------------------------------------------------------
# install fake hub once
# ----------------------------------------------------------------------
import app.hub as _hub_mod  # noqa: E402

_FAKE_HUB = FakeHub()
_hub_mod.get_hub = lambda: _FAKE_HUB  # type: ignore[assignment]


# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------
def make_agent_with_file(content: bytes, kind=ArtifactKind.VIDEO, mime="video/mp4"):
    """Create a fake agent + a real on-disk file under deliverable_dir,
    register an artifact pointing at it, and return (agent, artifact).
    """
    td = tempfile.mkdtemp(prefix="tudou_router_")
    fpath = os.path.join(td, "clip.mp4")
    with open(fpath, "wb") as f:
        f.write(content)
    aid = "agent_" + uuid.uuid4().hex[:8]
    a = FakeAgent(aid, td)
    rec = install_into_agent(a, force=True)
    assert rec is not None
    # ShadowRecorder __init__ already set deliverable_dir = working_dir
    art = rec.state.artifacts.create(
        kind=kind, value=fpath, label="clip",
        mime=mime, size=len(content),
        produced_by=ProducedBy(agent_id=aid, tool_id="test"),
    )
    _FAKE_HUB.add(a)
    return a, art


PASSED = []
FAILED = []


def case(name: str):
    def deco(fn):
        def runner():
            try:
                fn()
            except AssertionError as e:
                FAILED.append((name, f"AssertionError: {e}"))
                traceback.print_exc()
                return
            except Exception as e:
                FAILED.append((name, f"{type(e).__name__}: {e}"))
                traceback.print_exc()
                return
            PASSED.append(name)
        runner.__name__ = fn.__name__
        return runner
    return deco


# ----------------------------------------------------------------------
# tests
# ----------------------------------------------------------------------
@case("URL builder shape")
def t_builder():
    u = build_artifact_url("agent_abc", "art_def")
    assert u == "/api/agent_state/artifact/agent_abc/art_def", u
    assert build_artifact_url("", "art_x") == ""
    assert build_artifact_url("agent_x", "") == ""


@case("happy path: full GET of in-deliverable file")
def t_happy_full():
    payload = b"hello-mp4-bytes" * 100  # 1500 bytes
    a, art = make_agent_with_file(payload)
    h = FakeHandler()
    html_tag_router.handle(h, f"/api/agent_state/artifact/{a.id}/{art.id}")
    assert h.status == 200, h.status
    assert h.header("Content-Type") == "video/mp4"
    assert h.header("Content-Length") == str(len(payload))
    assert h.header("Accept-Ranges") == "bytes"
    assert h.body.getvalue() == payload


@case("Range request: returns 206 + correct slice")
def t_range_partial():
    payload = bytes(range(256)) * 4  # 1024 bytes
    a, art = make_agent_with_file(payload)
    h = FakeHandler(headers={"Range": "bytes=100-199"})
    html_tag_router.handle(h, f"/api/agent_state/artifact/{a.id}/{art.id}")
    assert h.status == 206, h.status
    assert h.header("Content-Length") == "100"
    assert h.header("Content-Range") == f"bytes 100-199/{len(payload)}"
    assert h.body.getvalue() == payload[100:200]


@case("Range request: open-ended (bytes=N-)")
def t_range_open():
    payload = b"x" * 500
    a, art = make_agent_with_file(payload)
    h = FakeHandler(headers={"Range": "bytes=400-"})
    html_tag_router.handle(h, f"/api/agent_state/artifact/{a.id}/{art.id}")
    assert h.status == 206, h.status
    assert h.body.getvalue() == payload[400:]
    assert h.header("Content-Range") == f"bytes 400-499/{len(payload)}"


@case("Range request: suffix (bytes=-N)")
def t_range_suffix():
    payload = b"y" * 1000
    a, art = make_agent_with_file(payload)
    h = FakeHandler(headers={"Range": "bytes=-50"})
    html_tag_router.handle(h, f"/api/agent_state/artifact/{a.id}/{art.id}")
    assert h.status == 206, h.status
    assert h.body.getvalue() == payload[-50:]
    assert h.header("Content-Range") == f"bytes 950-999/{len(payload)}"


@case("Range request: unsatisfiable -> 416")
def t_range_416():
    payload = b"z" * 100
    a, art = make_agent_with_file(payload)
    h = FakeHandler(headers={"Range": "bytes=200-300"})
    html_tag_router.handle(h, f"/api/agent_state/artifact/{a.id}/{art.id}")
    assert h.status == 416, h.status
    assert h.header("Content-Range") == f"bytes */{len(payload)}"


@case("unknown agent -> 404")
def t_unknown_agent():
    h = FakeHandler()
    html_tag_router.handle(h, "/api/agent_state/artifact/agent_ghost/art_ghost")
    assert h.status == 404


@case("unknown artifact -> 404")
def t_unknown_artifact():
    a, _ = make_agent_with_file(b"x")
    h = FakeHandler()
    html_tag_router.handle(h, f"/api/agent_state/artifact/{a.id}/art_ghost")
    assert h.status == 404


@case("non-file kind -> 403")
def t_non_file_kind():
    a, _ = make_agent_with_file(b"x")
    rec = a._shadow
    rec_record = rec.state.artifacts.create(
        kind=ArtifactKind.RECORD, value='{"k":"v"}', label="rec",
    )
    h = FakeHandler()
    html_tag_router.handle(h, f"/api/agent_state/artifact/{a.id}/{rec_record.id}")
    assert h.status == 403, h.status


@case("URL artifact -> 302 redirect")
def t_url_redirect():
    td = tempfile.mkdtemp(prefix="tudou_router_")
    aid = "agent_" + uuid.uuid4().hex[:8]
    a = FakeAgent(aid, td)
    rec = install_into_agent(a, force=True)
    art = rec.state.artifacts.create(
        kind=ArtifactKind.VIDEO,
        value="https://cdn.example.com/v.mp4",
        label="remote",
    )
    _FAKE_HUB.add(a)
    h = FakeHandler()
    html_tag_router.handle(h, f"/api/agent_state/artifact/{a.id}/{art.id}")
    assert h.status == 302
    assert h.header("Location") == "https://cdn.example.com/v.mp4"


@case("I5: file outside deliverable_dir -> 403")
def t_i5_outside():
    # build an agent whose deliverable_dir is one tmpdir...
    td_in = tempfile.mkdtemp(prefix="tudou_in_")
    td_out = tempfile.mkdtemp(prefix="tudou_out_")
    out_path = os.path.join(td_out, "leaked.mp4")
    with open(out_path, "wb") as f:
        f.write(b"escaped")
    aid = "agent_" + uuid.uuid4().hex[:8]
    a = FakeAgent(aid, td_in)
    rec = install_into_agent(a, force=True)
    # bypass commit (which would catch I5) by writing the artifact directly
    art = rec.state.artifacts.create(
        kind=ArtifactKind.VIDEO, value=out_path, label="leak",
        mime="video/mp4",
    )
    _FAKE_HUB.add(a)
    h = FakeHandler()
    html_tag_router.handle(h, f"/api/agent_state/artifact/{a.id}/{art.id}")
    assert h.status == 403, h.status


@case("file missing on disk -> 500")
def t_missing_file():
    a, art = make_agent_with_file(b"x")
    os.remove(art.value)
    h = FakeHandler()
    html_tag_router.handle(h, f"/api/agent_state/artifact/{a.id}/{art.id}")
    assert h.status == 500


@case("get_public_url: file -> route, http -> passthrough")
def t_public_url_helper():
    a, art = make_agent_with_file(b"x")
    rec = a._shadow
    u = rec.get_public_url(art.id)
    assert u == f"/api/agent_state/artifact/{a.id}/{art.id}", u
    # http-valued artifact passes through
    art2 = rec.state.artifacts.create(
        kind=ArtifactKind.VIDEO,
        value="https://cdn.example.com/x.mp4",
        label="remote",
    )
    u2 = rec.get_public_url(art2.id)
    assert u2 == "https://cdn.example.com/x.mp4"
    # unknown id -> ""
    assert rec.get_public_url("art_ghost") == ""


@case("ShadowRecorder + html_tag_router: end-to-end via real shadow flow")
def t_end_to_end():
    """Drive a fake agent through the same hooks chat() does, then
    fetch the resulting artifact via the router."""
    td = tempfile.mkdtemp(prefix="tudou_e2e_")
    aid = "agent_" + uuid.uuid4().hex[:8]
    a = FakeAgent(aid, td)
    rec = install_into_agent(a, force=True)
    _FAKE_HUB.add(a)

    # write a real video file to deliverable_dir as a tool would
    fpath = os.path.join(td, "morning.mp4")
    payload = b"FAKEMP4" * 256
    with open(fpath, "wb") as f:
        f.write(payload)

    rec.record_user("生成视频")
    # tool returns a JSON-style result with a path field
    rec.record_tool_result(
        "video.gen", f'{{"status":"ok","video_path":"{fpath}"}}',
    )
    rec.record_assistant("done")

    # find the video artifact and fetch it via the router
    videos = rec.state.artifacts.list(kind=ArtifactKind.VIDEO)
    assert len(videos) == 1, [a.value for a in rec.state.artifacts.all()]
    v = videos[0]
    h = FakeHandler()
    html_tag_router.handle(h, f"/api/agent_state/artifact/{a.id}/{v.id}")
    assert h.status == 200, h.status
    assert h.body.getvalue() == payload


# ----------------------------------------------------------------------
# Content-Disposition cases — exercise the universal file contract.
# Each case writes a real file with the right extension, uses
# mime_registry to derive the correct kind / mime / render_hint /
# filename (the same way the live extractor does), and asserts that
# the router echoes the right Content-Disposition header.
# ----------------------------------------------------------------------
def make_typed_artifact(filename: str, content: bytes = b"x" * 16):
    """Create an agent + artifact whose metadata matches what the
    real extractor would set, given a file with this extension."""
    td = tempfile.mkdtemp(prefix="tudou_disp_")
    fpath = os.path.join(td, filename)
    with open(fpath, "wb") as f:
        f.write(content)
    aid = "agent_" + uuid.uuid4().hex[:8]
    a = FakeAgent(aid, td)
    rec = install_into_agent(a, force=True)
    info = info_for_value(fpath)
    art = rec.state.artifacts.create(
        kind=info.kind,
        value=fpath,
        label=filename,
        mime=info.mime,
        size=len(content),
        produced_by=ProducedBy(agent_id=aid, tool_id="test"),
        metadata={
            "filename": filename,
            "render_hint": info.render_hint,
            "category": info.category,
        },
    )
    _FAKE_HUB.add(a)
    return a, art


def assert_disposition(filename: str, expected_type: str):
    a, art = make_typed_artifact(filename)
    h = FakeHandler()
    html_tag_router.handle(h, f"/api/agent_state/artifact/{a.id}/{art.id}")
    assert h.status == 200, f"{filename} -> status {h.status}"
    cd = h.header("Content-Disposition")
    assert cd is not None, f"{filename}: no Content-Disposition header"
    assert cd.startswith(expected_type + ";"), (
        f"{filename}: expected {expected_type}, got {cd!r}"
    )
    assert f'filename="{filename}"' in cd, (
        f"{filename}: filename missing in {cd!r}"
    )


@case("Content-Disposition: mp4 -> inline")
def t_disp_mp4():
    assert_disposition("clip.mp4", "inline")


@case("Content-Disposition: png -> inline")
def t_disp_png():
    assert_disposition("photo.png", "inline")


@case("Content-Disposition: jpg -> inline")
def t_disp_jpg():
    assert_disposition("snap.jpg", "inline")


@case("Content-Disposition: pdf -> inline")
def t_disp_pdf():
    assert_disposition("invoice.pdf", "inline")


@case("Content-Disposition: mp3 -> inline")
def t_disp_mp3():
    assert_disposition("song.mp3", "inline")


@case("Content-Disposition: docx -> attachment")
def t_disp_docx():
    assert_disposition("report.docx", "attachment")


@case("Content-Disposition: xlsx -> attachment")
def t_disp_xlsx():
    assert_disposition("data.xlsx", "attachment")


@case("Content-Disposition: pptx -> attachment")
def t_disp_pptx():
    assert_disposition("deck.pptx", "attachment")


@case("Content-Disposition: zip -> attachment")
def t_disp_zip():
    assert_disposition("bundle.zip", "attachment")


@case("Content-Disposition: missing render_hint -> attachment fallback")
def t_disp_fallback():
    """When metadata has no render_hint at all, the safe default is
    attachment so the page never gets blown up by inline render."""
    td = tempfile.mkdtemp(prefix="tudou_disp_fb_")
    fpath = os.path.join(td, "thing.bin")
    with open(fpath, "wb") as f:
        f.write(b"raw")
    aid = "agent_" + uuid.uuid4().hex[:8]
    a = FakeAgent(aid, td)
    rec = install_into_agent(a, force=True)
    art = rec.state.artifacts.create(
        kind=ArtifactKind.FILE,
        value=fpath,
        label="thing",
        mime="application/octet-stream",
        # NOTE: no metadata at all
    )
    _FAKE_HUB.add(a)
    h = FakeHandler()
    html_tag_router.handle(h, f"/api/agent_state/artifact/{a.id}/{art.id}")
    assert h.status == 200
    cd = h.header("Content-Disposition")
    assert cd.startswith("attachment;"), cd
    # filename comes from the basename of artifact.value
    assert 'filename="thing.bin"' in cd, cd


@case("Content-Disposition: non-ASCII filename emits filename* form")
def t_disp_unicode():
    """Chinese filename: must emit both ascii filename= and the
    RFC 5987 filename*= form so browsers decode UTF-8 correctly."""
    a, art = make_typed_artifact("演示视频.mp4", content=b"FAKEMP4" * 8)
    h = FakeHandler()
    html_tag_router.handle(h, f"/api/agent_state/artifact/{a.id}/{art.id}")
    assert h.status == 200
    cd = h.header("Content-Disposition")
    assert cd.startswith("inline;"), cd
    assert "filename*=UTF-8''" in cd, cd
    # the percent-encoded chinese form
    assert "%E6%BC%94%E7%A4%BA" in cd, cd


@case("Content-Disposition: archive kind streams as attachment")
def t_disp_archive_kind():
    """Confirms the new ARCHIVE kind made it into _FILE_KINDS so
    streaming actually happens (not 403)."""
    a, art = make_typed_artifact("backup.tar.gz")
    assert art.kind.value in ("archive", "file"), art.kind  # tar.gz registered
    h = FakeHandler()
    html_tag_router.handle(h, f"/api/agent_state/artifact/{a.id}/{art.id}")
    assert h.status == 200, h.status
    cd = h.header("Content-Disposition")
    assert cd.startswith("attachment;"), cd


@case("Content-Disposition: document kind streams as attachment")
def t_disp_document_kind():
    """Confirms the new DOCUMENT kind made it into _FILE_KINDS."""
    a, art = make_typed_artifact("notes.docx")
    assert art.kind.value == "document", art.kind
    h = FakeHandler()
    html_tag_router.handle(h, f"/api/agent_state/artifact/{a.id}/{art.id}")
    assert h.status == 200, h.status


# ----------------------------------------------------------------------
def main() -> int:
    tests = [
        t_builder,
        t_happy_full,
        t_range_partial, t_range_open, t_range_suffix, t_range_416,
        t_unknown_agent, t_unknown_artifact,
        t_non_file_kind,
        t_url_redirect,
        t_i5_outside, t_missing_file,
        t_public_url_helper,
        t_end_to_end,
        # Content-Disposition / universal file contract
        t_disp_mp4, t_disp_png, t_disp_jpg, t_disp_pdf, t_disp_mp3,
        t_disp_docx, t_disp_xlsx, t_disp_pptx, t_disp_zip,
        t_disp_fallback, t_disp_unicode,
        t_disp_archive_kind, t_disp_document_kind,
    ]
    print(f"running {len(tests)} html_tag_router smoke tests")
    print("-" * 60)
    for t in tests:
        t()
    print("-" * 60)
    for name in PASSED:
        print(f"  OK   {name}")
    for name, err in FAILED:
        print(f"  FAIL {name}")
        print(f"       {err}")
    print("-" * 60)
    print(f"passed: {len(PASSED)}  failed: {len(FAILED)}")
    return 0 if not FAILED else 1


if __name__ == "__main__":
    sys.exit(main())
