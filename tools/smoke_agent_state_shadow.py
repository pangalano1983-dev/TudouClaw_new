#!/usr/bin/env python3
"""
Smoke test for app/agent_state/shadow.py.

Drives a fake "Agent" object through the same hook calls that
agent.py now makes from inside chat(), and inspects the resulting
AgentState. No real LLM, no MCP, no portal. Run from project root:

    python tools/smoke_agent_state_shadow.py

Exit codes:
    0  all scenarios passed
    1  any scenario failed
"""
from __future__ import annotations

import os
import sys
import tempfile
import traceback
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app.agent_state.shadow import ShadowRecorder, install_into_agent  # noqa: E402
from app.agent_state import ArtifactKind, TaskStatus  # noqa: E402


# ----------------------------------------------------------------------
class FakeAgent:
    """Bare-minimum stand-in for app.agent.Agent."""
    def __init__(self, working_dir: str):
        self.id = uuid.uuid4().hex[:12]
        self.session_id = uuid.uuid4().hex
        self.working_dir = working_dir
        self.mcp_servers = []


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
@case("install: opt-in via force flag")
def t_install():
    with tempfile.TemporaryDirectory() as td:
        a = FakeAgent(td)
        rec = install_into_agent(a, force=True)
        assert rec is not None
        assert getattr(a, "_shadow", None) is rec
        # idempotent
        rec2 = install_into_agent(a, force=True)
        assert rec2 is rec


@case("install: enabled by default (post grey rollout)")
def t_install_disabled():
    with tempfile.TemporaryDirectory() as td:
        a = FakeAgent(td)
        os.environ.pop("TUDOU_AGENT_STATE_SHADOW", None)
        rec = install_into_agent(a)  # no force, no env flag
        assert rec is not None
        assert getattr(a, "_shadow", None) is rec


@case("install: opt-out via env flag =0")
def t_install_envflag():
    with tempfile.TemporaryDirectory() as td:
        a = FakeAgent(td)
        os.environ["TUDOU_AGENT_STATE_SHADOW"] = "0"
        try:
            rec = install_into_agent(a)
            assert rec is None
            assert getattr(a, "_shadow", None) is None
        finally:
            os.environ.pop("TUDOU_AGENT_STATE_SHADOW", None)


@case("flow: user -> tool with URL -> assistant -> task done")
def t_full_flow():
    with tempfile.TemporaryDirectory() as td:
        a = FakeAgent(td)
        rec = install_into_agent(a, force=True)
        assert rec is not None

        rec.record_user("生成一个打工人周一清晨的视频")
        # tool returns JSON with a video_url field
        rec.record_tool_result(
            "jimeng_video.submit_task",
            '{"status":"ok","video_url":"https://cdn.example.com/morning.mp4","duration":30}',
        )
        rec.record_assistant("视频生成好了，链接见上方")

        s = rec.state
        # one task, marked done
        assert len(s.tasks) == 1
        t = s.tasks.all()[0]
        assert t.status == TaskStatus.DONE, f"task status={t.status}"
        # one VIDEO artifact, attached to the task
        videos = s.artifacts.list(kind=ArtifactKind.VIDEO)
        assert len(videos) == 1, f"expected 1 video artifact, got {len(videos)}"
        v = videos[0]
        assert v.value == "https://cdn.example.com/morning.mp4"
        assert v.id in t.result_refs, \
            f"video {v.id} not attached to task ({t.result_refs})"
        assert v.produced_by.tool_id == "jimeng_video.submit_task"
        # conversation has user + tool + assistant turns
        roles = [t.role.value for t in s.conversation.all()]
        assert roles == ["user", "tool", "assistant"], roles


@case("flow: tool result with URL in free text (no JSON)")
def t_freetext_url():
    with tempfile.TemporaryDirectory() as td:
        a = FakeAgent(td)
        rec = install_into_agent(a, force=True)
        rec.record_user("download something")
        rec.record_tool_result(
            "browser.fetch",
            "OK fetched: https://example.com/report.pdf (size=12345)",
        )
        rec.record_assistant("done")
        pdfs = rec.state.artifacts.list()
        assert any(a.value == "https://example.com/report.pdf" for a in pdfs), \
            [a.value for a in pdfs]


@case("flow: assistant-mentioned URL captured")
def t_assistant_url():
    with tempfile.TemporaryDirectory() as td:
        a = FakeAgent(td)
        rec = install_into_agent(a, force=True)
        rec.record_user("hi")
        rec.record_tool_result("noop", "nothing here")
        rec.record_assistant(
            "I generated this for you: https://example.com/output.png",
        )
        imgs = rec.state.artifacts.list(kind=ArtifactKind.IMAGE)
        assert len(imgs) == 1, [a.value for a in rec.state.artifacts.all()]
        assert imgs[0].produced_by.tool_id == "assistant"


@case("flow: dedup — same URL across two tool calls counted once")
def t_dedup():
    with tempfile.TemporaryDirectory() as td:
        a = FakeAgent(td)
        rec = install_into_agent(a, force=True)
        rec.record_user("do it")
        rec.record_tool_result("t1", '{"url":"https://x.example/v.mp4"}')
        rec.record_tool_result("t2", '{"url":"https://x.example/v.mp4"}')
        rec.record_assistant("done")
        videos = [a for a in rec.state.artifacts.all()
                  if a.value == "https://x.example/v.mp4"]
        assert len(videos) == 1, f"expected dedup, got {len(videos)}"


@case("flow: error path -> task marked failed")
def t_error_path():
    with tempfile.TemporaryDirectory() as td:
        a = FakeAgent(td)
        rec = install_into_agent(a, force=True)
        rec.record_user("do something risky")
        rec.record_error(RuntimeError("boom"))
        t = rec.state.tasks.all()[0]
        assert t.status == TaskStatus.FAILED
        assert "boom" in t.metadata.get("failure_reason", "")


@case("safety: shadow swallows internal errors silently")
def t_safety_swallow():
    with tempfile.TemporaryDirectory() as td:
        a = FakeAgent(td)
        rec = install_into_agent(a, force=True)
        # corrupt internal state to provoke an exception inside the hook
        rec.state = None  # type: ignore
        # this MUST NOT raise — the live agent path depends on it
        rec.record_user("anything")
        rec.record_tool_result("x", "y")
        rec.record_assistant("z")
        rec.record_error(ValueError("nope"))


@case("envelope: build_envelope_refs returns empty before any turn")
def t_envelope_empty():
    with tempfile.TemporaryDirectory() as td:
        a = FakeAgent(td)
        rec = install_into_agent(a, force=True)
        assert rec.build_envelope_refs() == []


@case("envelope: build_envelope_refs after assistant turn carries refs")
def t_envelope_after_turn():
    with tempfile.TemporaryDirectory() as td:
        a = FakeAgent(td)
        rec = install_into_agent(a, force=True)
        rec.record_user("生成视频")
        rec.record_tool_result(
            "video.gen",
            '{"status":"ok","video_url":"https://cdn.example.com/x.mp4"}',
        )
        rec.record_assistant("done")
        refs = rec.build_envelope_refs()
        assert len(refs) == 1, refs
        r = refs[0]
        assert r["url"] == "https://cdn.example.com/x.mp4"
        assert r["kind"] == "video"
        assert r["render_hint"] == "inline_video"
        assert r["filename"] == "x.mp4"
        # required keys present
        for k in ("id", "url", "filename", "label", "kind", "mime",
                  "render_hint", "category", "size"):
            assert k in r, f"missing key {k}"


@case("envelope: file artifact uses build_artifact_url for url")
def t_envelope_file_url():
    with tempfile.TemporaryDirectory() as td:
        a = FakeAgent(td)
        rec = install_into_agent(a, force=True)
        # write a real file under the deliverable_dir (= working_dir)
        fp = os.path.join(td, "report.docx")
        with open(fp, "wb") as f:
            f.write(b"DOCXFAKE")
        rec.record_user("save report")
        rec.record_tool_result(
            "writer.save",
            f'{{"path":"{fp}","ok":true}}',
        )
        rec.record_assistant("saved")
        refs = rec.build_envelope_refs()
        assert len(refs) == 1, refs
        r = refs[0]
        assert r["kind"] == "document"
        assert r["render_hint"] == "card"
        # url should go through the artifact route
        assert r["url"].startswith("/api/agent_state/artifact/"), r["url"]
        assert a.id in r["url"]
        assert r["filename"] == "report.docx"


@case("envelope: build_envelope_refs is safe on broken state")
def t_envelope_safety():
    with tempfile.TemporaryDirectory() as td:
        a = FakeAgent(td)
        rec = install_into_agent(a, force=True)
        rec.state = None  # type: ignore
        # MUST NOT raise — live path depends on it
        out = rec.build_envelope_refs()
        assert out == []


@case("scan: deliverable_dir picks up pre-existing files on attach")
def t_scan_initial():
    with tempfile.TemporaryDirectory() as td:
        # seed the working_dir with a recognised file BEFORE the agent
        # is wired up — simulates a previous run / side-channel drop
        path = os.path.join(td, "jiangbanya_huili_v2.mp4")
        with open(path, "wb") as f:
            f.write(b"\x00" * 16)
        a = FakeAgent(td)
        rec = install_into_agent(a, force=True)
        arts = rec.state.artifacts.all()
        assert len(arts) == 1, f"expected 1 artifact, got {len(arts)}"
        art = arts[0]
        assert art.kind == ArtifactKind.VIDEO
        assert art.value.endswith("jiangbanya_huili_v2.mp4")
        assert art.metadata.get("extracted_from") == "deliverable_scan"
        assert art.metadata.get("render_hint") == "inline_video"
        assert art.size == 16


@case("scan: rescan is idempotent (no duplicate ingest)")
def t_scan_idempotent():
    with tempfile.TemporaryDirectory() as td:
        with open(os.path.join(td, "a.png"), "wb") as f:
            f.write(b"\x89PNG\r\n\x1a\n")
        a = FakeAgent(td)
        rec = install_into_agent(a, force=True)
        n0 = len(rec.state.artifacts.all())
        added = rec.rescan_deliverable_dir()
        assert added == 0
        assert len(rec.state.artifacts.all()) == n0


@case("scan: rescan picks up files added between turns")
def t_scan_incremental():
    with tempfile.TemporaryDirectory() as td:
        a = FakeAgent(td)
        rec = install_into_agent(a, force=True)
        assert len(rec.state.artifacts.all()) == 0
        # tool drops a new file mid-session
        with open(os.path.join(td, "report.pdf"), "wb") as f:
            f.write(b"%PDF-1.4")
        added = rec.rescan_deliverable_dir()
        assert added == 1
        arts = rec.state.artifacts.all()
        assert len(arts) == 1
        assert arts[0].kind == ArtifactKind.DOCUMENT


@case("scan: skips unknown extensions and hidden files")
def t_scan_skips_noise():
    with tempfile.TemporaryDirectory() as td:
        with open(os.path.join(td, "data.bin"), "wb") as f:
            f.write(b"\x00")
        with open(os.path.join(td, ".hidden.mp4"), "wb") as f:
            f.write(b"\x00")
        with open(os.path.join(td, "real.mp4"), "wb") as f:
            f.write(b"\x00")
        a = FakeAgent(td)
        rec = install_into_agent(a, force=True)
        arts = rec.state.artifacts.all()
        assert len(arts) == 1
        assert arts[0].value.endswith("real.mp4")


@case("scan: artifact id is stable across two scans (scheme A)")
def t_scan_stable_id():
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "video.mp4")
        with open(path, "wb") as f:
            f.write(b"\x00" * 8)
        # First "process": fresh agent + scan
        a1 = FakeAgent(td)
        rec1 = install_into_agent(a1, force=True)
        id1 = rec1.state.artifacts.all()[0].id
        # Second "process": brand-new agent, brand-new store, same path
        a2 = FakeAgent(td)
        rec2 = install_into_agent(a2, force=True)
        id2 = rec2.state.artifacts.all()[0].id
        assert id1 == id2, f"stable id broken: {id1} != {id2}"
        assert id1.startswith("art_")
        assert len(id1) == len("art_") + 12


@case("scan: content_hash present in metadata (scheme B)")
def t_scan_content_hash():
    with tempfile.TemporaryDirectory() as td:
        with open(os.path.join(td, "a.png"), "wb") as f:
            f.write(b"\x89PNG\r\n\x1a\nDATA")
        a = FakeAgent(td)
        rec = install_into_agent(a, force=True)
        art = rec.state.artifacts.all()[0]
        ch = art.metadata.get("content_hash")
        assert ch and len(ch) == 32, f"expected 32-hex blake2b, got {ch!r}"
        # Two files with identical bytes get the same content_hash
        with open(os.path.join(td, "b.png"), "wb") as f:
            f.write(b"\x89PNG\r\n\x1a\nDATA")
        rec.rescan_deliverable_dir()
        arts = rec.state.artifacts.all()
        hashes = [a.metadata.get("content_hash") for a in arts]
        assert len(arts) == 2
        assert hashes[0] == hashes[1], f"content_hash should match: {hashes}"
        # ...but their ids differ because path differs (scheme A is path-based)
        assert arts[0].id != arts[1].id


@case("scan: produced_at uses file mtime, not scan time")
def t_scan_mtime_as_produced_at():
    import time as _t
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "old.mp4")
        with open(path, "wb") as f:
            f.write(b"\x00")
        # Set mtime to 1 hour ago
        old = _t.time() - 3600
        os.utime(path, (old, old))
        a = FakeAgent(td)
        rec = install_into_agent(a, force=True)
        art = rec.state.artifacts.all()[0]
        # produced_at should be the mtime, not "now"
        assert abs(art.produced_at - old) < 2, (
            f"produced_at={art.produced_at} expected ~{old}"
        )


@case("file_index: deterministic mapping by event order")
def t_file_index_event_order():
    """Replay events through compute_file_index_from_events and verify
    each file lands on the right assistant turn — no timestamps used."""
    # Build a fake agent whose .events look like a real chat:
    #   user → tool_result(video1) → assistant(turn0)
    #   user → tool_result(video2) → assistant(turn1)
    import time as _t

    class _Ev:
        def __init__(self, kind, data):
            self.timestamp = _t.time()
            self.kind = kind
            self.data = data

    with tempfile.TemporaryDirectory() as td:
        a = FakeAgent(td)
        a.events = [
            _Ev("message", {"role": "user", "content": "make video 1"}),
            _Ev("tool_result", {
                "name": "video.gen",
                "result": '{"video_url":"https://cdn.example.com/v1.mp4"}',
            }),
            _Ev("message", {"role": "assistant", "content": "done v1"}),
            _Ev("message", {"role": "user", "content": "make video 2"}),
            _Ev("tool_result", {
                "name": "video.gen",
                "result": '{"video_url":"https://cdn.example.com/v2.mp4"}',
            }),
            _Ev("message", {"role": "assistant", "content": "done v2"}),
        ]
        rec = install_into_agent(a, force=True)
        idx = rec.compute_file_index_from_events()
        turns = idx.get("turns", [])
        assert len(turns) == 2, f"expected 2 turns, got {turns}"
        assert turns[0]["index"] == 0
        assert turns[1]["index"] == 1
        urls0 = [r["url"] for r in turns[0]["refs"]]
        urls1 = [r["url"] for r in turns[1]["refs"]]
        assert "https://cdn.example.com/v1.mp4" in urls0, urls0
        assert "https://cdn.example.com/v2.mp4" in urls1, urls1
        assert "https://cdn.example.com/v2.mp4" not in urls0
        assert idx.get("total_assistant_turns") == 2


@case("file_index: empty assistant content does NOT consume a turn slot")
def t_file_index_skip_empty_assistant():
    """An intermediate empty assistant turn (just tool_calls, no prose)
    must NOT increment the turn index — this matches the frontend's
    bubble filter exactly, otherwise indexes drift."""
    import time as _t

    class _Ev:
        def __init__(self, kind, data):
            self.timestamp = _t.time()
            self.kind = kind
            self.data = data

    with tempfile.TemporaryDirectory() as td:
        a = FakeAgent(td)
        a.events = [
            _Ev("message", {"role": "user", "content": "go"}),
            _Ev("message", {"role": "assistant", "content": ""}),  # tool-call shell
            _Ev("tool_result", {
                "name": "video.gen",
                "result": '{"video_url":"https://cdn.example.com/x.mp4"}',
            }),
            _Ev("message", {"role": "assistant", "content": "here it is"}),
        ]
        rec = install_into_agent(a, force=True)
        idx = rec.compute_file_index_from_events()
        turns = idx.get("turns", [])
        assert len(turns) == 1
        assert turns[0]["index"] == 0  # NOT 1
        assert idx.get("total_assistant_turns") == 1


@case("file_index: scan-ingested file gets bucketed when re-mentioned in prose")
def t_file_index_scan_then_prose():
    """The original 'jiangbanya' bug. The scanner ingests the .mp4 with
    a stable id BEFORE compute_file_index runs. The assistant prose
    then mentions the same absolute path. Without return_existing=True
    on ingest_into_store, the dedup-by-value silently drops the candidate
    and the file never gets bucketed. With the fix, it lands on the
    correct assistant turn."""
    import time as _t

    class _Ev:
        def __init__(self, kind, data):
            self.timestamp = _t.time()
            self.kind = kind
            self.data = data

    with tempfile.TemporaryDirectory() as td:
        # 1. file already on disk (simulates scanner having run)
        path = os.path.join(td, "jiangbanya_huili_v2.mp4")
        with open(path, "wb") as f:
            f.write(b"\x00" * 16)
        a = FakeAgent(td)
        # 2. assistant prose mentions the absolute path inline
        a.events = [
            _Ev("message", {"role": "user", "content": "where is the video"}),
            _Ev("message", {"role": "assistant",
                            "content": "文件的本地存储路径是: " + path}),
        ]
        rec = install_into_agent(a, force=True)  # scans path → 1 artifact
        assert len(rec.state.artifacts.all()) == 1
        idx = rec.compute_file_index_from_events()
        turns = idx.get("turns", [])
        assert len(turns) == 1, f"expected 1 turn, got {turns}"
        assert turns[0]["index"] == 0
        urls = [r["filename"] for r in turns[0]["refs"]]
        assert "jiangbanya_huili_v2.mp4" in urls, urls
        # the scan-ingested file should NOT also appear in orphans
        assert idx.get("orphans") == [], idx.get("orphans")


@case("file_index: relative + absolute path mentions collapse to one card")
def t_file_index_relative_absolute_dedup():
    """The 'three cards for one file' bug. Assistant prose mentions
    the same file via:
      - absolute path: /tmp/.../v.mp4
      - relative path: ./v.mp4
    Plus another file via relative path only:
      - ./old.mp4
    Both should normalise against deliverable_dir and dedup against
    the scan-ingested artifacts. Final card count: 2 (not 4)."""
    import time as _t

    class _Ev:
        def __init__(self, kind, data):
            self.timestamp = _t.time()
            self.kind = kind
            self.data = data

    with tempfile.TemporaryDirectory() as td:
        v_new = os.path.join(td, "v.mp4")
        v_old = os.path.join(td, "old.mp4")
        with open(v_new, "wb") as f:
            f.write(b"\x00" * 32)
        with open(v_old, "wb") as f:
            f.write(b"\x00" * 16)
        a = FakeAgent(td)
        prose = (
            "完整路径: " + v_new + "\n"
            "相对路径: ./v.mp4\n"
            "之前生成的: ./old.mp4"
        )
        a.events = [
            _Ev("message", {"role": "user", "content": "where"}),
            _Ev("message", {"role": "assistant", "content": prose}),
        ]
        rec = install_into_agent(a, force=True)
        # scan ingested both
        assert len(rec.state.artifacts.all()) == 2
        idx = rec.compute_file_index_from_events()
        turns = idx.get("turns", [])
        assert len(turns) == 1, f"expected 1 turn, got {turns}"
        refs = turns[0]["refs"]
        # The bug used to produce 3+ refs (1 real + 2 fake-rooted-/v.mp4
        # and /old.mp4 with no size and failing the I5 check on click).
        # After the fix: exactly 2 cards, both pointing at REAL absolute
        # paths (so size is set and downloads work).
        assert len(refs) == 2, f"expected 2 unique refs, got {len(refs)}: {refs}"
        names = sorted(r["filename"] for r in refs)
        assert names == ["old.mp4", "v.mp4"], names
        # both must have a real size — i.e. they came from the scan
        # artifacts, not freshly-created phantom artifacts
        for r in refs:
            assert r["size"] and r["size"] > 0, f"phantom artifact: {r}"
        # No orphans either — the relative-path refs were correctly
        # bucketed, so neither file is left over
        assert idx.get("orphans") == [], idx.get("orphans")


@case("normalize_path_candidates: relative -> absolute, URL untouched")
def t_normalize_path_candidates():
    from app.agent_state.extractors import (
        extract_from_text, normalize_path_candidates,
    )
    with tempfile.TemporaryDirectory() as td:
        text = (
            "see ./report.pdf and "
            + "/tmp/x.png and "
            + "https://e.com/v.mp4"
        )
        cands = extract_from_text(text)
        # extract should pick up all 3
        values = [c["value"] for c in cands]
        assert "./report.pdf" in values, values
        assert "/tmp/x.png" in values, values
        assert "https://e.com/v.mp4" in values, values
        normalize_path_candidates(cands, td)
        values = [c["value"] for c in cands]
        # ./report.pdf -> absolute under td
        assert os.path.join(td, "report.pdf") in values, values
        # /tmp/x.png stays absolute
        assert "/tmp/x.png" in values, values
        # URL untouched
        assert "https://e.com/v.mp4" in values, values


@case("extract: free text path is captured by extract_from_text")
def t_extract_path_from_text():
    from app.agent_state.extractors import extract_from_text
    cases = [
        "文件的本地存储路径是: /Users/pang/.tudou_claw/x.mp4",
        "saved to `/tmp/output.png`",
        "see ~/Downloads/report.pdf for details",
    ]
    expected = [
        "/Users/pang/.tudou_claw/x.mp4",
        "/tmp/output.png",
        "~/Downloads/report.pdf",
    ]
    for text, want in zip(cases, expected):
        cands = extract_from_text(text)
        values = [c["value"] for c in cands]
        assert want in values, f"{want!r} not in {values!r} (input={text!r})"


@case("extract: bare word with dot is NOT mistaken for a path")
def t_extract_path_no_false_positives():
    from app.agent_state.extractors import extract_from_text
    junk = [
        "see file.txt for details",          # no leading /
        "version 1.2.3 released",            # numeric, no leading /
        "use foo.bar to do x",               # no leading /
    ]
    for text in junk:
        cands = extract_from_text(text)
        values = [c["value"] for c in cands]
        # none of these should produce a path candidate
        for v in values:
            assert v.startswith(("/", "~")), \
                f"unexpected non-path candidate {v!r} from {text!r}"


@case("file_index: scanned-only files end up in orphans")
def t_file_index_orphans():
    with tempfile.TemporaryDirectory() as td:
        # Pre-existing file on disk; no tool_result event mentions it
        with open(os.path.join(td, "leftover.mp4"), "wb") as f:
            f.write(b"\x00")
        a = FakeAgent(td)
        a.events = []  # no chat at all
        rec = install_into_agent(a, force=True)
        idx = rec.compute_file_index_from_events()
        assert idx["turns"] == []
        assert len(idx["orphans"]) == 1
        assert idx["orphans"][0]["filename"] == "leftover.mp4"


@case("introspection: summary + recent_artifacts")
def t_introspection():
    with tempfile.TemporaryDirectory() as td:
        a = FakeAgent(td)
        rec = install_into_agent(a, force=True)
        rec.record_user("u")
        rec.record_tool_result("tool", '{"video_url":"https://e/x.mp4"}')
        rec.record_assistant("ok")
        s = rec.summary()
        assert s["artifacts_total"] == 1
        assert s["tasks_total"] == 1
        recent = rec.recent_artifacts(5)
        assert len(recent) == 1
        assert recent[0]["value"] == "https://e/x.mp4"


# ----------------------------------------------------------------------
def main() -> int:
    tests = [
        t_install, t_install_disabled, t_install_envflag,
        t_full_flow, t_freetext_url, t_assistant_url, t_dedup,
        t_error_path, t_safety_swallow, t_introspection,
        # phase-2 envelope injection
        t_envelope_empty, t_envelope_after_turn,
        t_envelope_file_url, t_envelope_safety,
        # phase-3 deliverable_dir scanner
        t_scan_initial, t_scan_idempotent,
        t_scan_incremental, t_scan_skips_noise,
        # phase-4 stable id (A) + content hash (B) + mtime as produced_at
        t_scan_stable_id, t_scan_content_hash, t_scan_mtime_as_produced_at,
        # phase-5 deterministic file → assistant-turn-index mapping
        t_file_index_event_order,
        t_file_index_skip_empty_assistant,
        t_file_index_orphans,
        # phase-6 dedup-aware ingest + path-from-prose extraction
        t_file_index_scan_then_prose,
        t_extract_path_from_text,
        t_extract_path_no_false_positives,
        # phase-7 relative-path normalization + cross-form dedup
        t_file_index_relative_absolute_dedup,
        t_normalize_path_candidates,
    ]
    print(f"running {len(tests)} shadow smoke tests")
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
