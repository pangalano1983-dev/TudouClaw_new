"""Block 0 Inbox — data layer tests.

Covers:
- send / fetch_unread / mark_read / mark_acked / get_thread / get_by_id
- Priority ordering (urgent > normal > low)
- Created_at ordering within priority (oldest first)
- TTL expiry behavior
- Unread count
- Cross-agent isolation (A's messages don't leak to B)
- mark_read only affects recipient's own messages
- Concurrent send from multiple threads stays consistent
- Persistence across store recreation (SQLite on disk)
- Invalid input rejected
- Priority normalization (bad values → normal)
- Thread continuation (reply_to + thread_id)
"""
from __future__ import annotations

import os
import threading
import time
import pytest

from app.inbox import (
    InboxMessage, InboxStore, get_store, reset_store_for_test,
)


@pytest.fixture
def store(tmp_path):
    """Fresh InboxStore in tmp dir, reset between tests."""
    reset_store_for_test()
    db = tmp_path / "inbox.db"
    s = InboxStore(str(db))
    yield s
    s.close()


# ─── send / fetch roundtrip ────────────────────────────────────────

def test_send_and_fetch_single_message(store):
    mid = store.send(to_agent="bob", from_agent="alice",
                      content="hi bob")
    msgs = store.fetch_unread("bob")
    assert len(msgs) == 1
    m = msgs[0]
    assert m.id == mid
    assert m.to_agent == "bob"
    assert m.from_agent == "alice"
    assert m.content == "hi bob"
    assert m.state == "new"
    assert m.thread_id == mid  # self-rooted by default
    assert m.priority == "normal"


def test_send_requires_fields(store):
    with pytest.raises(ValueError):
        store.send(to_agent="", from_agent="a", content="x")
    with pytest.raises(ValueError):
        store.send(to_agent="b", from_agent="", content="x")
    with pytest.raises(ValueError):
        store.send(to_agent="b", from_agent="a", content="")


def test_unknown_priority_normalized(store):
    mid = store.send(to_agent="bob", from_agent="alice",
                      content="hi", priority="SUPER_IMPORTANT")
    m = store.get_by_id(mid)
    assert m.priority == "normal"


# ─── ordering ──────────────────────────────────────────────────────

def test_priority_orders_unread(store):
    n = store.send(to_agent="bob", from_agent="a", content="normal 1",
                    priority="normal")
    u = store.send(to_agent="bob", from_agent="a", content="urgent!",
                    priority="urgent")
    l = store.send(to_agent="bob", from_agent="a", content="low",
                    priority="low")
    msgs = store.fetch_unread("bob")
    # urgent first, then normal, then low
    assert [m.id for m in msgs] == [u, n, l]


def test_same_priority_oldest_first(store):
    m1 = store.send(to_agent="bob", from_agent="a", content="first")
    time.sleep(0.01)  # ensure different timestamps
    m2 = store.send(to_agent="bob", from_agent="a", content="second")
    time.sleep(0.01)
    m3 = store.send(to_agent="bob", from_agent="a", content="third")
    msgs = store.fetch_unread("bob")
    assert [m.id for m in msgs] == [m1, m2, m3]


# ─── agent isolation ───────────────────────────────────────────────

def test_agents_only_see_own_messages(store):
    store.send(to_agent="alice", from_agent="sys", content="for alice")
    store.send(to_agent="bob",   from_agent="sys", content="for bob")
    alice_msgs = store.fetch_unread("alice")
    bob_msgs = store.fetch_unread("bob")
    assert len(alice_msgs) == 1
    assert alice_msgs[0].content == "for alice"
    assert len(bob_msgs) == 1
    assert bob_msgs[0].content == "for bob"


def test_unread_count_per_agent(store):
    store.send(to_agent="alice", from_agent="x", content="1")
    store.send(to_agent="alice", from_agent="x", content="2")
    store.send(to_agent="bob",   from_agent="x", content="1")
    assert store.unread_count("alice") == 2
    assert store.unread_count("bob") == 1
    assert store.unread_count("charlie") == 0


# ─── mark_read / mark_acked ────────────────────────────────────────

def test_mark_read_moves_from_new_to_read(store):
    m1 = store.send(to_agent="bob", from_agent="a", content="a")
    m2 = store.send(to_agent="bob", from_agent="a", content="b")
    updated = store.mark_read([m1, m2], "bob")
    assert updated == 2
    # Unread fetch no longer returns these
    assert store.fetch_unread("bob") == []
    # But get_by_id still finds them, state=read, read_at set
    m1_loaded = store.get_by_id(m1)
    assert m1_loaded.state == "read"
    assert m1_loaded.read_at > 0


def test_mark_read_only_affects_recipient(store):
    m = store.send(to_agent="alice", from_agent="x", content="msg")
    # Bob can't mark Alice's messages read
    updated = store.mark_read([m], "bob")
    assert updated == 0
    m_loaded = store.get_by_id(m)
    assert m_loaded.state == "new"


def test_mark_acked_from_new_skips_read_step(store):
    m = store.send(to_agent="bob", from_agent="a", content="hi")
    updated = store.mark_acked([m], "bob")
    assert updated == 1
    m_loaded = store.get_by_id(m)
    assert m_loaded.state == "acked"
    assert m_loaded.read_at > 0  # read_at back-filled
    assert m_loaded.acked_at > 0


def test_mark_acked_preserves_earlier_read_at(store):
    m = store.send(to_agent="bob", from_agent="a", content="hi")
    store.mark_read([m], "bob")
    earlier_read_at = store.get_by_id(m).read_at
    time.sleep(0.01)
    store.mark_acked([m], "bob")
    m_loaded = store.get_by_id(m)
    assert m_loaded.state == "acked"
    # read_at should NOT be overwritten — we want the ORIGINAL read time
    assert m_loaded.read_at == earlier_read_at


def test_mark_empty_list_is_noop(store):
    assert store.mark_read([], "anyone") == 0
    assert store.mark_acked([], "anyone") == 0


# ─── thread ────────────────────────────────────────────────────────

def test_get_thread_returns_all_in_order(store):
    root = store.send(to_agent="bob", from_agent="alice", content="root")
    r1 = store.send(to_agent="alice", from_agent="bob",
                     content="reply 1", thread_id=root, reply_to=root)
    time.sleep(0.01)
    r2 = store.send(to_agent="bob", from_agent="alice",
                     content="reply 2", thread_id=root, reply_to=r1)
    msgs = store.get_thread(root)
    assert [m.id for m in msgs] == [root, r1, r2]


def test_thread_defaults_to_self_if_not_specified(store):
    mid = store.send(to_agent="bob", from_agent="a", content="standalone")
    m = store.get_by_id(mid)
    # When the sender doesn't specify thread_id, msg becomes its own thread root
    assert m.thread_id == mid


def test_reply_points_to_original(store):
    root = store.send(to_agent="bob", from_agent="alice", content="q?")
    reply = store.send(to_agent="alice", from_agent="bob",
                        content="a.", thread_id=root, reply_to=root)
    m = store.get_by_id(reply)
    assert m.reply_to == root
    assert m.thread_id == root


# ─── TTL expiry ────────────────────────────────────────────────────

def test_ttl_expired_message_not_in_unread(store):
    # Create a message with a very short ttl that will already have expired
    mid = store.send(to_agent="bob", from_agent="a", content="stale",
                      ttl_s=0.01)
    time.sleep(0.05)
    # fetch_unread filters out expired even without explicit cleanup
    assert store.fetch_unread("bob") == []
    # But the row still exists (state=new until cleanup)
    m = store.get_by_id(mid)
    assert m is not None
    assert m.is_expired is True


def test_cleanup_expired_transitions_state(store):
    store.send(to_agent="bob", from_agent="a", content="stale",
                ttl_s=0.01)
    store.send(to_agent="bob", from_agent="a", content="fresh",
                ttl_s=0.0)  # no expiry
    time.sleep(0.05)
    n = store.cleanup_expired()
    assert n == 1
    stats = store.stats()
    assert stats["by_state"].get("expired", 0) == 1
    # fresh one unchanged
    assert stats["by_state"].get("new", 0) == 1


def test_ttl_zero_means_never_expires(store):
    mid = store.send(to_agent="bob", from_agent="a", content="永久",
                      ttl_s=0.0)
    time.sleep(0.02)
    msgs = store.fetch_unread("bob")
    assert len(msgs) == 1
    assert msgs[0].id == mid


# ─── since_id pagination ───────────────────────────────────────────

def test_fetch_unread_since_id(store):
    m1 = store.send(to_agent="bob", from_agent="a", content="1")
    time.sleep(0.01)
    m2 = store.send(to_agent="bob", from_agent="a", content="2")
    time.sleep(0.01)
    m3 = store.send(to_agent="bob", from_agent="a", content="3")
    msgs_after_m1 = store.fetch_unread("bob", since_id=m1)
    assert [m.id for m in msgs_after_m1] == [m2, m3]


def test_limit_caps_fetch_count(store):
    for i in range(10):
        store.send(to_agent="bob", from_agent="a", content=f"{i}")
    msgs = store.fetch_unread("bob", limit=3)
    assert len(msgs) == 3


# ─── metadata ──────────────────────────────────────────────────────

def test_metadata_roundtrips(store):
    mid = store.send(to_agent="bob", from_agent="a", content="hi",
                      metadata={"plan_id": "p1", "step_id": "s2",
                                "tags": ["urgent", "report"]})
    m = store.get_by_id(mid)
    assert m.metadata["plan_id"] == "p1"
    assert m.metadata["step_id"] == "s2"
    assert m.metadata["tags"] == ["urgent", "report"]


def test_metadata_defaults_empty(store):
    mid = store.send(to_agent="bob", from_agent="a", content="hi")
    m = store.get_by_id(mid)
    assert m.metadata == {}


# ─── persistence ───────────────────────────────────────────────────

def test_messages_persist_across_store_recreation(tmp_path):
    """Crash / restart: open a fresh InboxStore on the same file — should
    see prior messages."""
    reset_store_for_test()
    db = str(tmp_path / "persist.db")
    s1 = InboxStore(db)
    mid = s1.send(to_agent="bob", from_agent="alice", content="hello after restart")
    s1.close()

    s2 = InboxStore(db)
    m = s2.get_by_id(mid)
    assert m is not None
    assert m.content == "hello after restart"
    unread = s2.fetch_unread("bob")
    assert len(unread) == 1
    s2.close()


# ─── concurrency ───────────────────────────────────────────────────

def test_concurrent_sends_all_persist(store):
    """Many threads sending in parallel — no lost messages, no duplicates."""
    n_threads = 8
    per_thread = 15

    def sender(tid):
        for i in range(per_thread):
            store.send(to_agent="bob", from_agent=f"t{tid}",
                        content=f"msg-{tid}-{i}")

    threads = [threading.Thread(target=sender, args=(t,))
               for t in range(n_threads)]
    for t in threads: t.start()
    for t in threads: t.join()

    # Unread should have all of them
    msgs = store.fetch_unread("bob", limit=500)
    assert len(msgs) == n_threads * per_thread
    # All have unique ids
    assert len({m.id for m in msgs}) == n_threads * per_thread


def test_mark_read_and_send_concurrent_consistency(store):
    """Reader thread marks read while sender inserts — final state
    should be deterministic (no lost messages)."""
    def sender():
        for i in range(20):
            store.send(to_agent="bob", from_agent="alice",
                        content=f"msg {i}")

    read_count = [0]
    def reader():
        for _ in range(30):
            msgs = store.fetch_unread("bob", limit=10)
            if msgs:
                n = store.mark_read([m.id for m in msgs], "bob")
                read_count[0] += n
            time.sleep(0.002)

    ts = [threading.Thread(target=sender), threading.Thread(target=reader)]
    for t in ts: t.start()
    for t in ts: t.join()

    # Final state: either some messages are still new, or all were read.
    # Total new + read should equal 20.
    new = store.unread_count("bob")
    stats = store.stats()
    read = stats["by_state"].get("read", 0)
    assert new + read == 20


# ─── cleanup / stats ───────────────────────────────────────────────

def test_stats_reflects_current_state(store):
    store.send(to_agent="a", from_agent="x", content="1")
    m2 = store.send(to_agent="a", from_agent="x", content="2")
    store.send(to_agent="a", from_agent="x", content="3")
    store.mark_read([m2], "a")
    stats = store.stats()
    assert stats["total"] == 3
    assert stats["by_state"]["new"] == 2
    assert stats["by_state"]["read"] == 1


def test_delete_older_than(store):
    m1 = store.send(to_agent="a", from_agent="x", content="old")
    # Force m1 to be older
    store._conn.execute(
        "UPDATE inbox_messages SET created_at = ? WHERE id = ?",
        (time.time() - 3600, m1),
    )
    store.send(to_agent="a", from_agent="x", content="fresh")
    n = store.delete_older_than(cutoff_s=1800)  # delete anything >30m old
    assert n == 1
    assert store.get_by_id(m1) is None


# ─── singleton accessor ────────────────────────────────────────────

def test_get_store_returns_same_instance(tmp_path):
    reset_store_for_test()
    db = str(tmp_path / "sig.db")
    s1 = get_store(db)
    s2 = get_store()  # no path — should return same
    assert s1 is s2
    reset_store_for_test()


def test_reset_store_for_test_gives_fresh_instance(tmp_path):
    reset_store_for_test()
    db = str(tmp_path / "rst.db")
    s1 = get_store(db)
    reset_store_for_test()
    db2 = str(tmp_path / "rst2.db")
    s2 = get_store(db2)
    assert s1 is not s2
    reset_store_for_test()
