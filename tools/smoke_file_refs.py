#!/usr/bin/env python3
"""
Smoke test for app/agent_state/file_refs.py + project_artifact route
in app/server/html_tag_router.py.

Covers the project/meeting chat use case where messages reference
files in a project workspace and need to be rendered as FileCards
without going through any agent shadow store.

Run from project root:

    python tools/smoke_file_refs.py

Exit codes: 0 pass, 1 fail
"""
from __future__ import annotations

import io
import os
import sys
import tempfile
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app.agent_state.file_refs import build_refs_from_text  # noqa: E402
from app.agent_state.extractors import stable_artifact_id  # noqa: E402
from app.server import html_tag_router  # noqa: E402
from app.server.html_tag_router import build_project_artifact_url  # noqa: E402


# ----------------------------------------------------------------------
# fakes
# ----------------------------------------------------------------------
class FakeHeaders:
    def __init__(self, h: dict | None = None):
        self._h = {k.lower(): v for k, v in (h or {}).items()}

    def get(self, k, default=None):
        return self._h.get(k.lower(), default)


class FakeHandler:
    def __init__(self, headers: dict | None = None):
        self.status = None
        self.resp_headers: list = []
        self.body = io.BytesIO()
        self.wfile = self.body
        self.headers = FakeHeaders(headers)
        self.path = ""

    def send_response(self, code):
        self.status = code

    def send_header(self, k, v):
        self.resp_headers.append((k, v))

    def end_headers(self):
        pass

    def header(self, name):
        for k, v in self.resp_headers:
            if k.lower() == name.lower():
                return v
        return None


class FakeProject:
    def __init__(self, pid: str, working_directory: str):
        self.id = pid
        self.working_directory = working_directory


class FakeHub:
    def __init__(self):
        self._projects: dict = {}
        self._agents: dict = {}

    def add_project(self, p):
        self._projects[p.id] = p

    def get_project(self, pid):
        return self._projects.get(pid)

    def get_agent(self, aid):
        return self._agents.get(aid)


import app.hub as _hub_mod  # noqa: E402

_FAKE_HUB = FakeHub()
_hub_mod.get_hub = lambda: _FAKE_HUB  # type: ignore[assignment]


# ----------------------------------------------------------------------
# scaffolding
# ----------------------------------------------------------------------
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


def make_project_with_files(files: dict[str, bytes]) -> FakeProject:
    """Create a temp project workspace populated with the given files
    (relative path -> content). Returns a FakeProject already registered
    with the fake hub.
    """
    td = tempfile.mkdtemp(prefix="tudou_filerefs_")
    for rel, content in files.items():
        full = os.path.join(td, rel)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "wb") as f:
            f.write(content)
    p = FakeProject("proj_" + os.path.basename(td)[-8:], td)
    _FAKE_HUB.add_project(p)
    return p


def _url_for_project(pid: str):
    return lambda _abs, art_id: build_project_artifact_url(pid, art_id)


# ----------------------------------------------------------------------
# tests
# ----------------------------------------------------------------------
@case("build_refs: relative path resolves to project file")
def t_relative_path():
    p = make_project_with_files({"hello.mp4": b"x" * 32})
    text = "保存到了 ./hello.mp4，可以在这个目录访问"
    refs = build_refs_from_text(text, p.working_directory, url_for_path=_url_for_project(p.id))
    assert len(refs) == 1, refs
    r = refs[0]
    assert r["filename"] == "hello.mp4", r
    assert r["kind"] == "video", r
    assert r["size"] == 32, r
    assert r["url"].startswith("/api/agent_state/project_artifact/" + p.id + "/"), r["url"]
    assert r["id"].startswith("art_"), r["id"]


@case("build_refs: absolute + relative collapse to one card")
def t_relative_absolute_dedup():
    p = make_project_with_files({"out.mp4": b"y" * 16})
    abs_path = os.path.join(p.working_directory, "out.mp4")
    text = f"完整路径: {abs_path}\n相对路径: ./out.mp4"
    refs = build_refs_from_text(text, p.working_directory, url_for_path=_url_for_project(p.id))
    assert len(refs) == 1, [r["filename"] for r in refs]


@case("build_refs: nonexistent file is dropped")
def t_nonexistent_dropped():
    p = make_project_with_files({"real.mp4": b"r" * 8})
    text = "结果在 ./ghost.mp4 和 ./real.mp4"
    refs = build_refs_from_text(text, p.working_directory, url_for_path=_url_for_project(p.id))
    assert len(refs) == 1, [r["filename"] for r in refs]
    assert refs[0]["filename"] == "real.mp4", refs


@case("build_refs: path outside base_dir dropped when require_inside_base=True")
def t_outside_base_dropped():
    p = make_project_with_files({"inside.mp4": b"i" * 8})
    # Create a sibling file outside the project workspace
    other = tempfile.mkdtemp(prefix="tudou_other_")
    other_file = os.path.join(other, "outside.mp4")
    with open(other_file, "wb") as f:
        f.write(b"o" * 8)
    text = f"在外面: {other_file}\n在里面: ./inside.mp4"
    refs = build_refs_from_text(text, p.working_directory, url_for_path=_url_for_project(p.id))
    assert len(refs) == 1, [r["filename"] for r in refs]
    assert refs[0]["filename"] == "inside.mp4", refs


@case("build_refs: outside base allowed when require_inside_base=False")
def t_outside_base_allowed():
    p = make_project_with_files({"inside.mp4": b"i" * 8})
    other = tempfile.mkdtemp(prefix="tudou_other_")
    other_file = os.path.join(other, "outside.mp4")
    with open(other_file, "wb") as f:
        f.write(b"o" * 8)
    text = f"在外面: {other_file}"
    refs = build_refs_from_text(
        text, p.working_directory,
        url_for_path=_url_for_project(p.id),
        require_inside_base=False,
    )
    assert len(refs) == 1, refs
    assert refs[0]["filename"] == "outside.mp4", refs


@case("build_refs: URL passes through unchanged")
def t_url_passthrough():
    p = make_project_with_files({"x.txt": b"x"})
    text = "see https://example.com/video.mp4"
    refs = build_refs_from_text(text, p.working_directory, url_for_path=_url_for_project(p.id))
    assert any(r["url"] == "https://example.com/video.mp4" for r in refs), refs


@case("build_refs: empty text returns []")
def t_empty_text():
    p = make_project_with_files({"x.mp4": b"x"})
    assert build_refs_from_text("", p.working_directory, url_for_path=_url_for_project(p.id)) == []
    assert build_refs_from_text(None, p.working_directory, url_for_path=_url_for_project(p.id)) == []


@case("build_refs: ref id is stable across calls")
def t_stable_id():
    p = make_project_with_files({"stable.png": b"p" * 4})
    text = "./stable.png"
    refs1 = build_refs_from_text(text, p.working_directory, url_for_path=_url_for_project(p.id))
    refs2 = build_refs_from_text(text, p.working_directory, url_for_path=_url_for_project(p.id))
    assert refs1[0]["id"] == refs2[0]["id"], (refs1, refs2)


@case("build_refs: bare-word with dot is NOT picked up")
def t_no_false_positive():
    p = make_project_with_files({"x.mp4": b"x" * 4})
    text = "this version 1.2 is fine, see file.mp4 mentioned without path"
    # "file.mp4" with no leading ./ ../ ~/ / should not match _PATH_RE
    refs = build_refs_from_text(text, p.working_directory, url_for_path=_url_for_project(p.id))
    assert len(refs) == 0, [r["filename"] for r in refs]


# ----------------------------------------------------------------------
# project_artifact route tests
# ----------------------------------------------------------------------
@case("project_artifact route: full GET resolves stable id")
def t_project_route_full():
    payload = b"hello-png-bytes" * 50
    p = make_project_with_files({"sub/img.png": payload})
    abs_path = os.path.join(p.working_directory, "sub", "img.png")
    art_id = stable_artifact_id(abs_path)
    h = FakeHandler()
    html_tag_router.handle(h, f"/api/agent_state/project_artifact/{p.id}/{art_id}")
    assert h.status == 200, h.status
    assert h.body.getvalue() == payload, len(h.body.getvalue())
    assert h.header("Content-Type") == "image/png", h.header("Content-Type")
    cd = h.header("Content-Disposition") or ""
    assert "img.png" in cd, cd


@case("project_artifact route: range request returns 206")
def t_project_route_range():
    payload = bytes(range(256)) * 4
    p = make_project_with_files({"clip.mp4": payload})
    abs_path = os.path.join(p.working_directory, "clip.mp4")
    art_id = stable_artifact_id(abs_path)
    h = FakeHandler(headers={"Range": "bytes=10-19"})
    html_tag_router.handle(h, f"/api/agent_state/project_artifact/{p.id}/{art_id}")
    assert h.status == 206, h.status
    assert h.header("Content-Length") == "10", h.header("Content-Length")
    assert h.body.getvalue() == payload[10:20]


@case("project_artifact route: unknown project -> 404")
def t_project_route_unknown_project():
    h = FakeHandler()
    html_tag_router.handle(h, "/api/agent_state/project_artifact/nope_proj/art_doesnotexist")
    assert h.status == 404, h.status


@case("project_artifact route: unknown artifact id -> 404")
def t_project_route_unknown_id():
    p = make_project_with_files({"a.mp4": b"x" * 8})
    h = FakeHandler()
    html_tag_router.handle(h, f"/api/agent_state/project_artifact/{p.id}/art_ffffffffffff")
    assert h.status == 404, h.status


@case("project_artifact route: extension classifier rejects unknown")
def t_project_route_unknown_ext():
    # File exists but extension not in mime_registry → must NOT resolve
    # because the resolver only walks files whose path matches an id;
    # any path in the dir is candidate. The extension check happens after.
    p = make_project_with_files({"weird.qzx": b"x" * 8})
    abs_path = os.path.join(p.working_directory, "weird.qzx")
    art_id = stable_artifact_id(abs_path)
    h = FakeHandler()
    html_tag_router.handle(h, f"/api/agent_state/project_artifact/{p.id}/{art_id}")
    # Either 403 (kind rejected) or 404 (resolver skipped) is acceptable;
    # what we MUST NOT see is 200.
    assert h.status in (403, 404), h.status


@case("project_artifact route: build_project_artifact_url shape")
def t_project_url_builder():
    u = build_project_artifact_url("proj_abc", "art_def")
    assert u == "/api/agent_state/project_artifact/proj_abc/art_def", u
    assert build_project_artifact_url("", "x") == ""
    assert build_project_artifact_url("p", "") == ""


@case("matches: both prefixes are claimed by router")
def t_matches_both_prefixes():
    assert html_tag_router.matches("/api/agent_state/artifact/a/b") is True
    assert html_tag_router.matches("/api/agent_state/project_artifact/p/a") is True
    assert html_tag_router.matches("/api/portal/state") is False


# ----------------------------------------------------------------------
def main() -> int:
    tests = [
        t_relative_path,
        t_relative_absolute_dedup,
        t_nonexistent_dropped,
        t_outside_base_dropped,
        t_outside_base_allowed,
        t_url_passthrough,
        t_empty_text,
        t_stable_id,
        t_no_false_positive,
        t_project_route_full,
        t_project_route_range,
        t_project_route_unknown_project,
        t_project_route_unknown_id,
        t_project_route_unknown_ext,
        t_project_url_builder,
        t_matches_both_prefixes,
    ]
    print(f"running {len(tests)} file_refs + project_artifact smoke tests")
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
