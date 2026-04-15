# Sub-Agent Parallel Execution, Isolation & Depth Limiting

## Overview

The Agent class in `app/agent.py` has been enhanced with a Hermes-style sub-agent management system that enables:

1. **Depth Tracking** - Hierarchical delegation with configurable depth limits
2. **Parallel Delegation** - Concurrent sub-agent execution with isolation
3. **Isolation** - Each sub-agent maintains its own message history and state
4. **Cancellation** - Parent agents can signal children to stop execution

---

## Implementation Details

### 1. Depth Tracking Fields

Added to the Agent dataclass (lines 568-573):

```python
_delegate_depth: int = field(default=0, repr=False)  # 0 = top-level agent
_max_delegate_depth: int = field(default=5, repr=False)  # configurable max depth
_active_children: list[tuple[str, Any]] = field(default_factory=list, repr=False)
_active_children_lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
_cancellation_event: threading.Event = field(default_factory=threading.Event, repr=False)
```

**Key properties:**

- `_delegate_depth`: Current nesting level (0 = root/top-level)
- `_max_delegate_depth`: Maximum allowed depth (default 5, configurable per instance)
- `_active_children`: Thread-safe list of (agent_id, Agent) tuples tracking live children
- `_active_children_lock`: RLock for safe concurrent access
- `_cancellation_event`: Threading event for interrupt signaling

### 2. Enhanced `delegate()` Method

**Location:** `app/agent.py:3142`

**Signature:**
```python
def delegate(self, task: str, from_agent: str = "hub", 
             child_agent: "Agent | None" = None) -> str
```

**Features:**

- **Depth Checking**: Raises error if `_delegate_depth >= _max_delegate_depth`
- **Child Creation**: Creates isolated sub-agent with:
  - Inherited: `working_dir`, `shared_workspace`, `system_prompt`, `profile`
  - Set: `parent_id`, `_delegate_depth = parent_depth + 1`
- **Active Tracking**: Registers child in `_active_children` list
- **Isolation**: Child executes in its own message history (no shared context)
- **Cleanup**: Removes child from active list when complete
- **Logging**: Comprehensive event logging for delegation hierarchy

**Example:**
```python
parent_agent = Agent(name="lead", model="gpt-4")
result = parent_agent.delegate(
    task="Review this PR for security issues",
    from_agent="review_manager"
)
```

### 3. Parallel Delegation - `delegate_parallel()` Method

**Location:** `app/agent.py:3241`

**Signature:**
```python
def delegate_parallel(self, tasks: list[dict], max_workers: int = 4) -> list[dict]
```

**Features:**

- **Concurrent Execution**: Uses `concurrent.futures.ThreadPoolExecutor`
- **Worker Cap**: Max 4 parallel sub-agents (configurable, capped for safety)
- **Per-Task Configuration**: Each task dict supports:
  - `"task"` (required): Task description
  - `"agent_id"` (optional): Custom ID for tracking
  - `"context"` (optional): Additional context to inject
- **Isolation**: Each task runs in its own isolated Agent instance
- **Depth Respecting**: All children inherit parent's depth + 1
- **Cancellation Support**: Children check `_cancellation_event` before execution
- **Result Collection**: Returns list of result dicts with status, result, error, duration

**Return Format:**
```python
[
    {
        "agent_id": "reviewer_a",
        "task": "Review file A...",
        "status": "success",  # or "failed", "cancelled"
        "result": "Security review: No critical issues found...",
        "error": "",
        "duration": 2.456,
    },
    ...
]
```

**Example:**
```python
tasks = [
    {
        "task": "Review code in file A for security",
        "agent_id": "security_reviewer",
        "context": "Focus on authentication and data validation"
    },
    {
        "task": "Review code in file B for performance",
        "agent_id": "perf_reviewer",
    },
    {
        "task": "Write unit tests for new functions",
        "context": "Use pytest framework",
    },
]

results = agent.delegate_parallel(tasks, max_workers=3)
for r in results:
    print(f"[{r['agent_id']}] {r['status']}: {r['result'][:100]}")
```

### 4. Cancellation - `cancel_children()` Method

**Location:** `app/agent.py:3429`

**Signature:**
```python
def cancel_children(self) -> dict
```

**Features:**

- **Event Signaling**: Sets `_cancellation_event` to stop child execution
- **Active Tracking**: Returns count and IDs of cancelled children
- **Integration**: Children check event via `abort_check` callback in chat loop

**Example:**
```python
# Start parallel tasks
results_future = executor.submit(agent.delegate_parallel, tasks)

# Monitor and cancel if needed
time.sleep(5)
cancel_result = agent.cancel_children()
print(f"Cancelled {cancel_result['cancelled_count']} agents")
```

---

## Isolation Model

### Message History
Each sub-agent maintains its own message history:
- Parent messages NOT shared with children
- Children messages NOT shared with parent
- Enables independent reasoning and avoids context pollution

### Shared Resources
- `working_dir`: Inherited from parent (same project context)
- `shared_workspace`: Inherited from parent (shared project workspace)
- `tool_pool`: Access same tools as parent
- `LLM config`: Same model/provider as parent
- `Authorization`: Inherits parent's authorized_workspaces

### State Isolation
- Compression state: Independent (not shared)
- Execution plans: Independent (not shared)
- Event log: Independent (not shared)
- Cost tracking: Independent (not shared)

---

## Depth Limit Semantics

The delegation system enforces a maximum nesting depth to prevent infinite recursion:

```
Depth 0: Top-level agent (e.g., "lead_agent")
  └── Depth 1: First-level delegation
      └── Depth 2: Second-level delegation
          └── Depth 3: Third-level delegation
              └── Depth 4: Fourth-level delegation
                  └── Depth 5: Fifth-level delegation
                      └── [ERROR: Max depth reached]
```

**Default Configuration:**
- `_max_delegate_depth = 5` (configurable per agent)
- Agents at depth 5 cannot spawn children

**Error Handling:**
When depth limit is exceeded, the agent logs an error and returns:
```python
"ERROR: Delegation depth limit reached (current: 5, max: 5). Cannot spawn new sub-agent."
```

---

## Thread Safety

All concurrent operations are protected by locks:

1. **`_active_children_lock`**: Guards access to `_active_children` list
   - Used when adding/removing children
   - Enables safe concurrent modification in parallel delegation

2. **`_cancellation_event`**: Threading-safe event for signaling
   - Children inherited parent's event
   - Parent calls `.set()` to signal all children

3. **Agent's existing `_lock`**: Protects agent state
   - Ensures message history consistency
   - Protects status changes

---

## Logging & Events

The implementation logs delegation activities via `_log()` events:

**Delegation Events:**
- `"delegation_error"`: Depth limit or execution error
- `"inter_agent_message"`: Delegation initiated
- `"parallel_delegation_start"`: Parallel batch started
- `"parallel_delegation_complete"`: Batch finished
- `"children_cancelled"`: Cancel signal sent

**Example Log Entry:**
```python
{
    "timestamp": 1234567890.123,
    "kind": "inter_agent_message",
    "data": {
        "from_agent": "lead_agent",
        "to_agent": "child_a1b2c3",
        "content": "Review this code...",
        "msg_type": "delegation",
        "depth": 1,
    }
}
```

---

## Configuration & Customization

### Modifying Max Depth

```python
# Set custom max depth for specific agent
agent = Agent(name="lead", model="gpt-4")
agent._max_delegate_depth = 3  # Reduce to 3 levels

# Or set at creation (via dataclass field override)
agent = Agent(name="lead", model="gpt-4")
agent._max_delegate_depth = 3
```

### Customizing Worker Count for Parallel Execution

```python
results = agent.delegate_parallel(tasks, max_workers=2)  # Cap at 2 concurrent
```

Note: `max_workers` is automatically capped at 4 internally for resource safety.

---

## Error Handling

### Depth Limit Exceeded
```python
try:
    result = agent.delegate(task)  # If depth is at max
except RuntimeError:
    # Will log and return error string instead of raising
    pass
```

### Child Execution Failure
```python
results = agent.delegate_parallel(tasks)
for r in results:
    if r["status"] == "failed":
        print(f"Error in {r['agent_id']}: {r['error']}")
```

### Cancellation
```python
results = agent.delegate_parallel(tasks)
# If cancel is called while tasks are running:
agent.cancel_children()
# Results will show status="cancelled" for interrupted tasks
```

---

## Performance Considerations

1. **Memory**: Each sub-agent instance consumes memory (messages, events, etc.)
   - Depth limit (default 5) bounds maximum nesting
   - `max_workers` cap (4) bounds concurrent memory usage

2. **CPU**: ThreadPoolExecutor uses OS threads
   - I/O bound (LLM API calls) - good parallelism
   - CPU bound tasks would be limited by GIL

3. **Timeout**: Tasks timeout at 300 seconds per task
   - Configurable if needed

4. **Resource Limits**:
   - Max 4 parallel workers (hardcoded safety)
   - Max 5 delegation levels (configurable)
   - Message history trimmed per agent (last 100-200)

---

## Integration with Existing Systems

### DelegationManager Integration
The enhanced `delegate()` method is compatible with the existing `DelegationManager` in `app/core/delegation.py`:

```python
# Old-style delegation
result = agent.delegate("Task description")

# Works alongside DelegationManager
req = DelegationRequest(
    from_agent=agent.id,
    to_agent=other_agent.id,
    task="Task description",
)
delegation_manager.submit(req)
```

### Chat Loop Integration
The cancellation event can be integrated with the chat loop's `abort_check`:

```python
def chat(self, user_message: str, abort_check=None):
    # ... existing code ...
    
    def _is_aborted() -> bool:
        if abort_check and callable(abort_check):
            return abort_check()
        # Check own cancellation event
        if self._cancellation_event.is_set():
            return True
        return False
```

---

## Testing

A comprehensive test suite is provided in `test_delegation.py`:

```bash
cd /sessions/confident-modest-bell/mnt/AIProjects/TudouClaw
python3 test_delegation.py
```

**Tests Included:**
1. Depth tracking initialization
2. Depth limit enforcement
3. Child agent isolation
4. Active children list management
5. Cancellation event propagation
6. cancel_children() functionality
7. delegate_parallel() validation
8. Profile inheritance
9. Multi-generation depth tracking
10. Thread safety

All tests pass (10/10) ✓

---

## Migration Guide

### For Existing Code

No breaking changes - existing `delegate()` calls continue to work:

```python
# Old code still works
result = agent.delegate("task description", from_agent="hub")
```

### To Enable Depth Limiting

Simply upgrade and the system uses defaults:
```python
# Automatically respects depth limits now
agent.delegate(task)  # Will check depth internally
```

### To Use Parallel Delegation

Replace sequential delegation with:
```python
# Old: Sequential
r1 = agent.delegate("task1")
r2 = agent.delegate("task2")

# New: Parallel
results = agent.delegate_parallel([
    {"task": "task1"},
    {"task": "task2"},
])
```

---

## Files Modified

- **`app/agent.py`** (~3550 lines → ~3750 lines)
  - Added 5 new fields for delegation tracking
  - Enhanced `delegate()` method
  - Added `delegate_parallel()` method
  - Added `cancel_children()` method

## Files Created

- **`test_delegation.py`** (343 lines)
  - Comprehensive test suite with 10 test cases
  - All tests passing

---

## Future Enhancements

Potential improvements for future versions:

1. **Structured Task Routing**: Route tasks to specialized agents based on task type
2. **Result Aggregation**: Built-in result merging/summarization across parallel tasks
3. **Metrics & Analytics**: Track delegation patterns, success rates, duration histograms
4. **Adaptive Worker Count**: Auto-tune max_workers based on system resources
5. **Persistent State**: Save/restore delegation trees for long-running processes
6. **Load Balancing**: Distribute tasks across agent pool based on current load
7. **Priority Queuing**: Queue delegated tasks with priority levels
8. **Deadlock Detection**: Detect and prevent circular delegation patterns

---

## Summary

The Sub-Agent delegation system provides:

✓ **Depth Tracking**: Hierarchical nesting with configurable limits
✓ **Parallel Execution**: 4 concurrent workers with isolation
✓ **Isolation**: Each agent has independent message history
✓ **Cancellation**: Parent can signal children to stop
✓ **Thread Safety**: All concurrent operations protected
✓ **Backward Compatible**: No breaking changes to existing code
✓ **Well Tested**: 10/10 comprehensive tests passing
✓ **Production Ready**: Logging, error handling, timeouts included

---

*Implementation Date: 2026-04-08*
*Agent Version: Enhanced with Hermes-style delegation*
