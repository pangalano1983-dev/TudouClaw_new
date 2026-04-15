# Sub-Agent Delegation - Usage Examples

This document provides practical examples of using the enhanced delegation system in TudouClaw.

---

## Example 1: Basic Sequential Delegation

**Scenario:** A manager agent delegates a task to a specialist.

```python
from app.agent import Agent

# Create manager agent (top-level)
manager = Agent(name="Project Manager", model="gpt-4")

# Delegate a specific task
code_review = manager.delegate(
    task="Review the authentication module for security vulnerabilities",
    from_agent="project_manager"
)

print("Code Review Result:")
print(code_review)
```

**Key Points:**
- Manager is at depth 0 (top-level)
- Child agent is created automatically at depth 1
- Child inherits parent's working directory and tools
- Result is returned as a string

---

## Example 2: Multi-Level Delegation (Hermes-style)

**Scenario:** Hierarchical delegation with depth tracking.

```python
from app.agent import Agent

# Level 0: Top-level coordinator
coordinator = Agent(name="Coordinator", model="gpt-4", _delegate_depth=0)
coordinator._max_delegate_depth = 3  # Allow up to 3 levels

# Level 1: Coordinate through team leads
analysis = coordinator.delegate(
    task="""
    Analyze the performance bottlenecks in our Python microservice.
    Break down the task and delegate to sub-teams as needed.
    """,
    from_agent="coordinator"
)

print(f"Analysis from depth-1 agent:\n{analysis}")
```

**Key Points:**
- Coordinator can create children (depth 1)
- Those children can delegate to depth 2
- Those can delegate to depth 3
- Depth 4 would be blocked with error message

---

## Example 3: Parallel Delegation with Multiple Tasks

**Scenario:** A team lead delegates multiple review tasks in parallel.

```python
from app.agent import Agent

# Create lead agent
lead = Agent(
    name="Code Review Lead",
    model="gpt-4",
    working_dir="/projects/my_service",
)

# Define multiple review tasks
review_tasks = [
    {
        "task": "Review security aspects of user authentication",
        "agent_id": "security_reviewer",
        "context": "Focus on: password hashing, token validation, rate limiting"
    },
    {
        "task": "Review performance aspects of database queries",
        "agent_id": "perf_reviewer",
        "context": "Check for N+1 queries, missing indexes, inefficient joins"
    },
    {
        "task": "Review code style and architectural patterns",
        "agent_id": "style_reviewer",
        "context": "Ensure compliance with team's design guidelines"
    },
]

# Execute all reviews in parallel
results = lead.delegate_parallel(review_tasks, max_workers=3)

# Process results
print("Code Review Results:\n")
for result in results:
    status = "✓" if result["status"] == "success" else "✗"
    print(f"{status} [{result['agent_id']}] ({result['duration']:.2f}s)")
    print(f"  Status: {result['status']}")
    if result['status'] == 'success':
        print(f"  Summary: {result['result'][:200]}...")
    else:
        print(f"  Error: {result['error']}")
    print()
```

**Expected Output:**
```
Code Review Results:

✓ [security_reviewer] (3.45s)
  Status: success
  Summary: Security Analysis:
- Password hashing using bcrypt with proper salt...

✓ [perf_reviewer] (2.87s)
  Status: success
  Summary: Performance Analysis:
- Found 2 N+1 query patterns in user service...

✓ [style_reviewer] (4.12s)
  Status: success
  Summary: Style Analysis:
- Code structure aligns with team patterns...
```

**Key Points:**
- Runs 3 reviews concurrently (up to max_workers)
- Each gets its own isolated agent instance
- All three complete in parallel (~4.12s instead of 10.44s sequential)
- Results include timing and status

---

## Example 4: Handling Failed and Cancelled Tasks

**Scenario:** Monitor parallel tasks and handle failures/cancellations.

```python
from app.agent import Agent
import time
import threading

def process_task_results(lead, results):
    """Analyze delegation results."""
    success_count = sum(1 for r in results if r['status'] == 'success')
    failed_count = sum(1 for r in results if r['status'] == 'failed')
    cancelled_count = sum(1 for r in results if r['status'] == 'cancelled')
    
    print(f"\nResults Summary:")
    print(f"  Success:   {success_count}")
    print(f"  Failed:    {failed_count}")
    print(f"  Cancelled: {cancelled_count}")
    print()
    
    for result in results:
        if result['status'] == 'failed':
            print(f"⚠️  [{result['agent_id']}] FAILED")
            print(f"    Task: {result['task'][:60]}...")
            print(f"    Error: {result['error']}")
            print()

# Create lead with tasks
lead = Agent(name="Lead", model="gpt-4")

tasks = [
    {"task": "Task 1", "agent_id": "worker_1"},
    {"task": "Task 2", "agent_id": "worker_2"},
    {"task": "Task 3 (may timeout)", "agent_id": "worker_3"},
]

# Run in background thread to monitor
def run_delegation():
    return lead.delegate_parallel(tasks, max_workers=2)

thread = threading.Thread(target=run_delegation)
thread.start()

# Monitor progress
time.sleep(2)  # Let tasks run for 2 seconds

# Cancel remaining tasks if needed
cancellation = lead.cancel_children()
print(f"Cancelled {cancellation['cancelled_count']} agents")

thread.join()

# Could retrieve results here in production code
```

**Key Points:**
- Graceful handling of failures
- Cancellation signals stop child agents
- Results provide detailed error messages
- Summary statistics easily computed

---

## Example 5: Nested Delegation with Context

**Scenario:** A complex workflow with multiple delegation levels.

```python
from app.agent import Agent

class ProjectWorkflow:
    def __init__(self):
        self.project_lead = Agent(
            name="Project Lead",
            model="gpt-4",
            _max_delegate_depth=4
        )
    
    def run_feature_development(self, feature_description):
        """Orchestrate feature development through multiple levels."""
        
        # Level 1: Delegate to tech lead
        architecture_plan = self.project_lead.delegate(
            task=f"""
            Create technical architecture for feature:
            {feature_description}
            
            Please break this down into:
            1. System design overview
            2. Data model changes
            3. API endpoints needed
            4. Database migrations
            """,
            from_agent="project_lead"
        )
        
        # Level 2: Delegate implementation tasks based on plan
        impl_tasks = [
            {
                "task": "Implement backend API endpoints",
                "context": f"Based on: {architecture_plan[:500]}",
                "agent_id": "backend_impl"
            },
            {
                "task": "Implement database schema changes",
                "context": f"Based on: {architecture_plan[:500]}",
                "agent_id": "db_impl"
            },
            {
                "task": "Write integration tests",
                "context": f"Based on: {architecture_plan[:500]}",
                "agent_id": "test_impl"
            },
        ]
        
        # Create a tech lead agent for parallel delegation
        tech_lead = Agent(name="Tech Lead", model="gpt-4")
        tech_lead._delegate_depth = 1
        tech_lead._max_delegate_depth = self.project_lead._max_delegate_depth
        
        impl_results = tech_lead.delegate_parallel(impl_tasks, max_workers=3)
        
        return {
            "architecture": architecture_plan,
            "implementations": impl_results
        }

# Usage
workflow = ProjectWorkflow()
result = workflow.run_feature_development(
    feature_description="Add user profile customization feature"
)

print("Feature Development Results:")
print(f"Architecture:\n{result['architecture'][:300]}...\n")
print(f"Implementations: {len(result['implementations'])} tasks completed")
```

**Key Points:**
- Multi-level coordination (depth 0 → 1 → 2)
- Context passing between delegation levels
- Parallel execution at each level
- Orchestration of complex workflows

---

## Example 6: Error Recovery and Retry Logic

**Scenario:** Delegate with error handling and retry capability.

```python
from app.agent import Agent
import time

def delegate_with_retry(agent, task, max_retries=3):
    """Delegate a task with automatic retry on failure."""
    for attempt in range(max_retries):
        try:
            result = agent.delegate(task, from_agent=agent.name)
            if not result.startswith("ERROR"):
                return result, attempt + 1
            
            print(f"⚠️  Attempt {attempt + 1} failed, retrying...")
            time.sleep(2 ** attempt)  # Exponential backoff
            
        except Exception as e:
            print(f"✗ Exception on attempt {attempt + 1}: {e}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
            continue
    
    return f"ERROR: Failed after {max_retries} attempts", max_retries

# Usage
agent = Agent(name="Worker", model="gpt-4")

result, attempts = delegate_with_retry(
    agent,
    task="Complex analysis task that might fail",
    max_retries=3
)

print(f"Result after {attempts} attempt(s):")
print(result)
```

**Key Points:**
- Graceful error handling
- Exponential backoff between retries
- Detailed attempt tracking
- Suitable for unreliable operations

---

## Example 7: Monitoring Delegation Depth

**Scenario:** Track and limit delegation depth across an organization.

```python
from app.agent import Agent

def create_agent_hierarchy(name, depth=0, max_depth=3):
    """Create agent with proper depth configuration."""
    agent = Agent(name=name, model="gpt-4")
    agent._delegate_depth = depth
    agent._max_delegate_depth = max_depth
    return agent

def check_delegation_capacity(agent):
    """Check if agent can delegate further."""
    remaining_depth = agent._max_delegate_depth - agent._delegate_depth
    return remaining_depth > 0

# Example hierarchy
ceo = create_agent_hierarchy("CEO", depth=0, max_depth=3)
vp = create_agent_hierarchy("VP", depth=1, max_depth=3)
manager = create_agent_hierarchy("Manager", depth=2, max_depth=3)
contributor = create_agent_hierarchy("Contributor", depth=3, max_depth=3)

# Check delegation capacity at each level
agents = [
    ("CEO", ceo),
    ("VP", vp),
    ("Manager", manager),
    ("Contributor", contributor),
]

print("Agent Delegation Capacity:")
print("-" * 50)
for name, agent in agents:
    can_delegate = check_delegation_capacity(agent)
    remaining = agent._max_delegate_depth - agent._delegate_depth
    status = "Can delegate" if can_delegate else "At max depth"
    
    print(f"{name:15} | Depth {agent._delegate_depth}/{agent._max_delegate_depth} | {status}")

print("-" * 50)
```

**Expected Output:**
```
Agent Delegation Capacity:
--------------------------------------------------
CEO             | Depth 0/3 | Can delegate
VP              | Depth 1/3 | Can delegate
Manager         | Depth 2/3 | Can delegate
Contributor     | Depth 3/3 | At max depth
--------------------------------------------------
```

**Key Points:**
- Organizational hierarchy tracking
- Capacity checking before delegation
- Prevents unauthorized deep nesting

---

## Example 8: Real-World Code Review Workflow

**Scenario:** Complete code review workflow using parallel delegation.

```python
from app.agent import Agent
from pathlib import Path

class CodeReviewOrchestrator:
    def __init__(self, project_path):
        self.project_path = project_path
        self.lead_reviewer = Agent(
            name="Code Review Lead",
            model="gpt-4",
            working_dir=str(project_path),
        )
    
    def review_pull_request(self, pr_files):
        """Orchestrate parallel code review of PR files."""
        
        # Create review tasks
        review_tasks = []
        for file_path in pr_files:
            # Read file content
            with open(self.project_path / file_path, 'r') as f:
                content = f.read()
            
            review_tasks.append({
                "task": f"Review file: {file_path}",
                "context": f"File content:\n{content[:2000]}",
                "agent_id": f"reviewer_{file_path.replace('/', '_')}"
            })
        
        # Run parallel reviews
        print(f"Starting parallel review of {len(review_tasks)} files...")
        results = self.lead_reviewer.delegate_parallel(
            review_tasks,
            max_workers=min(4, len(review_tasks))
        )
        
        # Aggregate results
        summary = self._aggregate_results(results)
        return summary
    
    def _aggregate_results(self, results):
        """Aggregate review results into summary."""
        issues = []
        suggestions = []
        
        for result in results:
            if result['status'] == 'success':
                # Parse review output for issues/suggestions
                content = result['result']
                issues.extend(self._extract_issues(content))
                suggestions.extend(self._extract_suggestions(content))
        
        return {
            "total_reviews": len(results),
            "success": sum(1 for r in results if r['status'] == 'success'),
            "issues": issues,
            "suggestions": suggestions
        }
    
    def _extract_issues(self, content):
        """Extract issues from review content."""
        # Simple extraction - could be more sophisticated
        lines = content.split('\n')
        return [l for l in lines if 'issue' in l.lower()]
    
    def _extract_suggestions(self, content):
        """Extract suggestions from review content."""
        lines = content.split('\n')
        return [l for l in lines if 'suggest' in l.lower()]

# Usage
pr_files = [
    "src/auth.py",
    "src/database.py",
    "src/api.py",
]

orchestrator = CodeReviewOrchestrator(Path("/projects/my_app"))
summary = orchestrator.review_pull_request(pr_files)

print(f"\nCode Review Summary:")
print(f"  Files reviewed: {summary['total_reviews']}")
print(f"  Successful reviews: {summary['success']}")
print(f"  Issues found: {len(summary['issues'])}")
print(f"  Suggestions: {len(summary['suggestions'])}")
```

**Key Points:**
- Real-world workflow pattern
- File I/O with delegation
- Result aggregation across parallel tasks
- Scalable to many files

---

## Best Practices

### 1. Depth Configuration
```python
# Set appropriate max depth for your use case
agent._max_delegate_depth = 3  # Shallow hierarchy
agent._max_delegate_depth = 7  # Deep hierarchy
```

### 2. Worker Count
```python
# Balance between parallelism and resource usage
results = agent.delegate_parallel(tasks, max_workers=2)  # Conservative
results = agent.delegate_parallel(tasks, max_workers=4)  # Aggressive (max)
```

### 3. Error Handling
```python
# Always check status in parallel results
for result in results:
    if result['status'] != 'success':
        logger.error(f"Task {result['agent_id']} failed: {result['error']}")
```

### 4. Context Passing
```python
# Provide rich context to child agents
tasks = [{
    "task": "Analyze performance",
    "context": "Historical metrics: ..., Targets: ..., Constraints: ..."
}]
```

### 5. Cancellation Handling
```python
# Always provide timeout or cancellation mechanism
import threading
timeout = threading.Timer(60, lambda: agent.cancel_children())
timeout.start()
try:
    results = agent.delegate_parallel(tasks)
finally:
    timeout.cancel()
```

---

## Summary

The delegation system enables:

- **Sequential delegation** with parent-child relationships
- **Parallel execution** of independent tasks
- **Depth limiting** to prevent runaway nesting
- **Isolation** between agent message histories
- **Graceful cancellation** for interrupt handling
- **Rich logging** for monitoring and debugging

For more details, see `DELEGATION_IMPLEMENTATION.md`.
