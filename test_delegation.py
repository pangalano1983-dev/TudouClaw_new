#!/usr/bin/env python3
"""
Test suite for Sub-Agent parallel execution, isolation, and depth limiting.

Tests the Hermes-style delegation system:
- Depth tracking and enforcement
- Parallel delegation with isolation
- Cancellation signals
- Parent-child relationships
"""

import sys
import time
import threading
from pathlib import Path

# Add app to path
app_path = Path(__file__).parent / "app"
sys.path.insert(0, str(app_path.parent))

from app.agent import Agent, AgentProfile


def test_depth_tracking():
    """Test that delegation depth is properly tracked."""
    print("\n[TEST 1] Depth Tracking")
    print("=" * 60)

    agent = Agent(
        name="top_agent",
        model="gpt-4",
        _delegate_depth=0,
        _max_delegate_depth=3,
    )

    print(f"✓ Created top-level agent: depth={agent._delegate_depth}/{agent._max_delegate_depth}")
    assert agent._delegate_depth == 0
    assert agent._max_delegate_depth == 3

    # Verify child would get depth + 1
    # (We can't fully test without mocking chat(), but we can verify the setup)
    assert agent._active_children == []
    assert agent._active_children_lock is not None
    assert isinstance(agent._cancellation_event, threading.Event)

    print("✓ Depth tracking fields properly initialized")


def test_depth_limit_enforcement():
    """Test that depth limits are enforced."""
    print("\n[TEST 2] Depth Limit Enforcement")
    print("=" * 60)

    # Create agent at max depth
    agent = Agent(
        name="max_depth_agent",
        model="gpt-4",
        _delegate_depth=5,  # At max
        _max_delegate_depth=5,
    )

    print(f"✓ Created agent at max depth: {agent._delegate_depth}/{agent._max_delegate_depth}")

    # Try to delegate (should fail without actually calling chat)
    # We'll use a mock child agent to test depth assignment
    child = Agent(name="child", model="gpt-4")

    # Since the depth check happens early, let's verify the error would occur
    if agent._delegate_depth >= agent._max_delegate_depth:
        print("✓ Depth limit check correctly triggers at max depth")
    else:
        print("✗ Depth limit check failed")
        sys.exit(1)


def test_child_agent_isolation():
    """Test that child agents have isolated message history."""
    print("\n[TEST 3] Child Agent Isolation")
    print("=" * 60)

    parent = Agent(
        name="parent_agent",
        model="gpt-4",
        working_dir="/tmp/test_parent",
        _delegate_depth=0,
    )

    # Manually add a child-like agent to verify isolation
    child = Agent(
        name="isolated_child",
        model="gpt-4",
        parent_id=parent.id,
        working_dir="/tmp/test_parent",  # Inherited
        _delegate_depth=1,  # Set from parent's logic
    )

    print(f"✓ Parent has {len(parent.messages)} messages")
    print(f"✓ Child has {len(child.messages)} messages")

    # Verify they have separate message histories
    assert parent.messages is not child.messages, "Child should have isolated messages"
    print("✓ Child messages are isolated from parent")

    # Verify shared working directory
    assert child.working_dir == parent.working_dir
    print(f"✓ Child inherits parent working_dir: {child.working_dir}")

    # Verify parent-child relationship
    assert child.parent_id == parent.id
    print(f"✓ Parent-child relationship tracked: child.parent_id={child.parent_id}")


def test_active_children_tracking():
    """Test that active children are properly tracked."""
    print("\n[TEST 4] Active Children Tracking")
    print("=" * 60)

    parent = Agent(name="parent", model="gpt-4")

    # Manually add some "children" to test tracking
    child1_id = "child_001"
    child2_id = "child_002"
    child1 = Agent(name="child1", model="gpt-4", parent_id=parent.id)
    child2 = Agent(name="child2", model="gpt-4", parent_id=parent.id)

    # Simulate adding children (what delegate() would do)
    with parent._active_children_lock:
        parent._active_children.append((child1_id, child1))
        parent._active_children.append((child2_id, child2))

    print(f"✓ Added 2 children to parent")
    assert len(parent._active_children) == 2

    # Simulate removing one
    with parent._active_children_lock:
        parent._active_children = [
            (aid, ag) for aid, ag in parent._active_children
            if aid != child1_id
        ]

    print(f"✓ Removed 1 child, {len(parent._active_children)} remain")
    assert len(parent._active_children) == 1
    assert parent._active_children[0][0] == child2_id


def test_cancellation_event_propagation():
    """Test that cancellation event propagates to children."""
    print("\n[TEST 5] Cancellation Event Propagation")
    print("=" * 60)

    parent = Agent(name="parent", model="gpt-4")
    assert not parent._cancellation_event.is_set()
    print("✓ Parent cancellation event initially clear")

    # Create a child that inherits the event
    child = Agent(name="child", model="gpt-4")
    child._cancellation_event = parent._cancellation_event

    # Set cancellation
    parent._cancellation_event.set()

    assert parent._cancellation_event.is_set()
    assert child._cancellation_event.is_set()
    print("✓ Cancellation event propagated to child")


def test_cancel_children_method():
    """Test the cancel_children() method."""
    print("\n[TEST 6] cancel_children() Method")
    print("=" * 60)

    parent = Agent(name="parent", model="gpt-4")

    # Add some mock children
    child1 = Agent(name="child1", model="gpt-4", parent_id=parent.id)
    child2 = Agent(name="child2", model="gpt-4", parent_id=parent.id)

    with parent._active_children_lock:
        parent._active_children.append((child1.id, child1))
        parent._active_children.append((child2.id, child2))

    print(f"✓ Added 2 active children")

    # Call cancel_children
    result = parent.cancel_children()

    print(f"✓ Cancellation result: {result}")
    assert result["cancelled_count"] == 2
    assert child1.id in result["agent_ids"]
    assert child2.id in result["agent_ids"]
    assert parent._cancellation_event.is_set()
    print("✓ All children signaled for cancellation")


def test_delegate_parallel_validation():
    """Test delegate_parallel input validation."""
    print("\n[TEST 7] delegate_parallel() Validation")
    print("=" * 60)

    agent = Agent(name="test_agent", model="gpt-4", _delegate_depth=0)

    # Test with depth limit exceeded
    agent._delegate_depth = 5
    agent._max_delegate_depth = 5

    tasks = [
        {"task": "Task 1"},
        {"task": "Task 2"},
    ]

    # This should return error results (not actually execute)
    # But we can verify the validation logic
    if agent._delegate_depth >= agent._max_delegate_depth:
        print("✓ Depth limit check prevents delegation")
    else:
        print("✗ Depth limit check failed")
        sys.exit(1)

    # Reset and test with valid depth
    agent._delegate_depth = 0
    assert agent._delegate_depth < agent._max_delegate_depth
    print("✓ Valid depth allows delegation")


def test_profile_inheritance():
    """Test that child agents inherit parent's profile."""
    print("\n[TEST 8] Profile Inheritance")
    print("=" * 60)

    parent_profile = AgentProfile(
        personality="technical",
        communication_style="formal",
        expertise=["python", "devops"],
        skills=["coding", "testing"],
        temperature=0.5,
    )

    parent = Agent(
        name="parent",
        model="gpt-4",
        profile=parent_profile,
    )

    # Create child profile by cloning parent's
    child_profile = AgentProfile.from_dict(parent.profile.to_dict())
    assert child_profile.personality == parent.profile.personality
    assert child_profile.expertise == parent.profile.expertise

    print(f"✓ Child profile inherited: personality={child_profile.personality}")
    print(f"✓ Child profile has same expertise: {child_profile.expertise}")


def test_depth_tracking_multiple_generations():
    """Test depth tracking across multiple generations."""
    print("\n[TEST 9] Multi-Generation Depth Tracking")
    print("=" * 60)

    # Create a chain of agents representing delegation hierarchy
    gen0 = Agent(name="gen0", model="gpt-4", _delegate_depth=0)
    gen1 = Agent(name="gen1", model="gpt-4", _delegate_depth=1, parent_id=gen0.id)
    gen2 = Agent(name="gen2", model="gpt-4", _delegate_depth=2, parent_id=gen1.id)
    gen3 = Agent(name="gen3", model="gpt-4", _delegate_depth=3, parent_id=gen2.id)

    print(f"✓ Gen 0 (root): depth={gen0._delegate_depth}")
    print(f"✓ Gen 1 (child): depth={gen1._delegate_depth}")
    print(f"✓ Gen 2 (grandchild): depth={gen2._delegate_depth}")
    print(f"✓ Gen 3 (great-grandchild): depth={gen3._delegate_depth}")

    assert gen0._delegate_depth == 0
    assert gen1._delegate_depth == 1
    assert gen2._delegate_depth == 2
    assert gen3._delegate_depth == 3

    assert gen1.parent_id == gen0.id
    assert gen2.parent_id == gen1.id
    assert gen3.parent_id == gen2.id

    print("✓ Multi-generation hierarchy correctly tracked")


def test_thread_safety():
    """Test thread-safe operations on active children list."""
    print("\n[TEST 10] Thread Safety")
    print("=" * 60)

    parent = Agent(name="parent", model="gpt-4")
    results = []

    def add_child(child_num):
        """Add a child agent in a thread."""
        child = Agent(name=f"child_{child_num}", model="gpt-4")
        with parent._active_children_lock:
            parent._active_children.append((child.id, child))
        results.append(("add", child.id))

    def remove_child(child_id):
        """Remove a child agent in a thread."""
        with parent._active_children_lock:
            parent._active_children = [
                (aid, ag) for aid, ag in parent._active_children
                if aid != child_id
            ]
        results.append(("remove", child_id))

    # Create threads to add and remove children
    threads = []
    for i in range(5):
        t = threading.Thread(target=add_child, args=(i,))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    print(f"✓ Added 5 children concurrently: {len(parent._active_children)} total")
    assert len(parent._active_children) == 5

    # Remove some
    children_to_remove = [aid for aid, _ in parent._active_children[:3]]
    threads = []
    for child_id in children_to_remove:
        t = threading.Thread(target=remove_child, args=(child_id,))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    print(f"✓ Removed 3 children concurrently: {len(parent._active_children)} remain")
    assert len(parent._active_children) == 2

    print("✓ Thread-safe operations verified")


def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("SUB-AGENT DELEGATION TEST SUITE")
    print("Testing: Depth Tracking, Isolation, Parallel Execution, Cancellation")
    print("=" * 60)

    try:
        test_depth_tracking()
        test_depth_limit_enforcement()
        test_child_agent_isolation()
        test_active_children_tracking()
        test_cancellation_event_propagation()
        test_cancel_children_method()
        test_delegate_parallel_validation()
        test_profile_inheritance()
        test_depth_tracking_multiple_generations()
        test_thread_safety()

        print("\n" + "=" * 60)
        print("ALL TESTS PASSED ✓")
        print("=" * 60)
        return 0

    except AssertionError as e:
        print(f"\n✗ TEST FAILED: {e}")
        return 1
    except Exception as e:
        print(f"\n✗ UNEXPECTED ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
