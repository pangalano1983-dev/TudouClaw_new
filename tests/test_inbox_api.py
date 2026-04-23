"""REST tests for the /api/portal/inbox/* router.

Builds a minimal FastAPI app hosting only the inbox router, with
``get_current_user`` overridden to a stub admin. The inbox store is
pointed at a per-test tmpdir via ``TUDOU_CLAW_DATA_DIR`` so tests are
fully isolated.
"""
from __future__ import annotations

import os
import tempfile

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="inbox_api_test_")
    db_path = os.path.join(tmpdir, "inbox.db")
    monkeypatch.setenv("TUDOU_CLAW_DATA_DIR", tmpdir)

    from app import inbox as inbox_mod
    inbox_mod.reset_store_for_test()
    # Prime with explicit path so the router sees an initialized store.
    store = inbox_mod.get_store(db_path=db_path)

    # Build isolated app.
    from app.api.deps.auth import get_current_user, CurrentUser

    async def _fake_user():
        return CurrentUser(user_id="u1", role="superAdmin")

    from app.api.routers import inbox as inbox_router
    app = FastAPI()
    app.dependency_overrides[get_current_user] = _fake_user
    app.include_router(inbox_router.router)

    with TestClient(app) as tc:
        # Patch hub.get_hub globally so /count aggregate has an agent set.
        class _FakeAgent:
            def __init__(self, aid): self.id = aid

        class _FakeHub:
            def __init__(self):
                self.agents = {"a-alice": _FakeAgent("a-alice"),
                               "a-bob": _FakeAgent("a-bob")}
                self.routed = []

            def route_message(self, frm, to, content, msg_type="task",
                              source="api", metadata=None):
                self.routed.append((frm, to, content, msg_type, source))

        from app import hub as hub_pkg
        fake = _FakeHub()
        monkeypatch.setattr(hub_pkg, "get_hub", lambda: fake)
        tc.store = store
        tc.hub = fake
        yield tc

    inbox_mod.reset_store_for_test()


# ── /count ──────────────────────────────────────────────────────────


def test_count_specific_agent(client):
    client.store.send(to_agent="a-alice", from_agent="a-bob", content="hi")
    r = client.get("/api/portal/inbox/count", params={"agent_id": "a-alice"})
    assert r.status_code == 200
    assert r.json() == {"agent_id": "a-alice", "unread": 1}


def test_count_aggregate(client):
    client.store.send(to_agent="a-alice", from_agent="x", content="1")
    client.store.send(to_agent="a-alice", from_agent="x", content="2")
    client.store.send(to_agent="a-bob", from_agent="x", content="3")
    r = client.get("/api/portal/inbox/count")
    assert r.status_code == 200
    d = r.json()
    assert d["unread"] == 3
    assert d["per_agent"]["a-alice"] == 2
    assert d["per_agent"]["a-bob"] == 1


# ── /list ───────────────────────────────────────────────────────────


def test_list_returns_unread_first(client):
    m1 = client.store.send(to_agent="a-alice", from_agent="x",
                           content="normal", priority="normal")
    m2 = client.store.send(to_agent="a-alice", from_agent="x",
                           content="urgent!!", priority="urgent")
    r = client.get("/api/portal/inbox/list",
                   params={"agent_id": "a-alice"})
    assert r.status_code == 200
    d = r.json()
    assert d["unread_count"] == 2
    ids = [m["id"] for m in d["messages"]]
    # urgent should come before normal.
    assert ids.index(m2) < ids.index(m1)


def test_list_includes_read_messages_when_requested(client):
    m1 = client.store.send(to_agent="a-alice", from_agent="x", content="a")
    client.store.mark_read([m1], "a-alice")
    # Without include_read
    r = client.get("/api/portal/inbox/list",
                   params={"agent_id": "a-alice",
                           "include_read": "false"})
    assert r.json()["count"] == 0
    # With include_read (default)
    r2 = client.get("/api/portal/inbox/list",
                    params={"agent_id": "a-alice"})
    msgs = r2.json()["messages"]
    assert len(msgs) == 1
    assert msgs[0]["state"] == "read"


def test_list_acked_excluded_by_default(client):
    m1 = client.store.send(to_agent="a-alice", from_agent="x", content="a")
    client.store.mark_acked([m1], "a-alice")
    r = client.get("/api/portal/inbox/list",
                   params={"agent_id": "a-alice"})
    assert r.json()["count"] == 0
    # include_acked surfaces them
    r2 = client.get("/api/portal/inbox/list",
                    params={"agent_id": "a-alice",
                            "include_acked": "true"})
    assert r2.json()["count"] == 1
    assert r2.json()["messages"][0]["state"] == "acked"


def test_list_requires_agent_id(client):
    r = client.get("/api/portal/inbox/list")
    assert r.status_code == 422  # missing required query param


# ── /thread/{id} ────────────────────────────────────────────────────


def test_thread_returns_ordered_messages(client):
    root = client.store.send(to_agent="a-alice", from_agent="a-bob",
                             content="q?", thread_id="t-9")
    client.store.send(to_agent="a-bob", from_agent="a-alice",
                      content="a!", thread_id="t-9", reply_to=root)
    r = client.get("/api/portal/inbox/thread/t-9")
    d = r.json()
    assert d["count"] == 2
    assert d["messages"][0]["content"] == "q?"
    assert d["messages"][1]["content"] == "a!"


# ── /ack ────────────────────────────────────────────────────────────


def test_ack_transitions_state(client):
    mid = client.store.send(to_agent="a-alice", from_agent="x",
                            content="to ack")
    r = client.post("/api/portal/inbox/ack",
                    json={"agent_id": "a-alice", "message_ids": [mid]})
    assert r.status_code == 200
    assert r.json()["acked"] == 1
    assert client.store.get_by_id(mid).state == "acked"


def test_ack_skips_foreign(client):
    mine = client.store.send(to_agent="a-alice", from_agent="x",
                             content="mine")
    theirs = client.store.send(to_agent="a-bob", from_agent="x",
                               content="theirs")
    r = client.post("/api/portal/inbox/ack",
                    json={"agent_id": "a-alice",
                          "message_ids": [mine, theirs]})
    d = r.json()
    assert d["acked"] == 1
    assert d["skipped"] == 1


def test_ack_empty_ids_rejected(client):
    r = client.post("/api/portal/inbox/ack",
                    json={"agent_id": "a-alice", "message_ids": []})
    assert r.status_code == 400


# ── /mark_read ──────────────────────────────────────────────────────


def test_mark_read(client):
    mid = client.store.send(to_agent="a-alice", from_agent="x",
                            content="m")
    r = client.post("/api/portal/inbox/mark_read",
                    json={"agent_id": "a-alice", "message_ids": [mid]})
    assert r.status_code == 200
    assert r.json()["marked_read"] == 1
    assert client.store.get_by_id(mid).state == "read"


# ── /reply ──────────────────────────────────────────────────────────


def test_reply_persists_and_mirrors_to_hub(client):
    orig = client.store.send(to_agent="a-alice", from_agent="a-bob",
                             content="status?", thread_id="t-1")
    r = client.post("/api/portal/inbox/reply",
                    json={"agent_id": "a-alice",
                          "message_id": orig,
                          "content": "done",
                          "priority": "urgent"})
    assert r.status_code == 200
    d = r.json()
    assert d["to_agent"] == "a-bob"
    assert d["thread_id"] == "t-1"
    # Thread now has original + reply.
    thread = client.store.get_thread("t-1")
    assert len(thread) == 2
    assert thread[1].content == "done"
    assert thread[1].priority == "urgent"
    # Hub-mirror fired.
    assert len(client.hub.routed) == 1
    frm, to, content, msg_type, source = client.hub.routed[0]
    assert frm == "a-alice" and to == "a-bob"
    assert msg_type == "reply"
    assert source == "portal_inbox_ui"


def test_reply_refused_when_not_addressed_to_caller(client):
    orig = client.store.send(to_agent="a-bob", from_agent="a-alice",
                             content="for bob")
    r = client.post("/api/portal/inbox/reply",
                    json={"agent_id": "a-alice",
                          "message_id": orig,
                          "content": "sneaky"})
    assert r.status_code == 403


def test_reply_404_on_unknown_message(client):
    r = client.post("/api/portal/inbox/reply",
                    json={"agent_id": "a-alice",
                          "message_id": "msg_does_not_exist",
                          "content": "x"})
    assert r.status_code == 404


def test_reply_400_on_missing_content(client):
    orig = client.store.send(to_agent="a-alice", from_agent="x", content="q")
    r = client.post("/api/portal/inbox/reply",
                    json={"agent_id": "a-alice",
                          "message_id": orig,
                          "content": ""})
    assert r.status_code == 400


# ── /stats ──────────────────────────────────────────────────────────


def test_stats_reflects_store(client):
    client.store.send(to_agent="a-alice", from_agent="x", content="a")
    r = client.get("/api/portal/inbox/stats")
    assert r.status_code == 200
    d = r.json()
    assert d["total"] == 1
    assert d["by_state"]["new"] == 1
