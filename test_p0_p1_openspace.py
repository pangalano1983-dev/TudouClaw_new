#!/usr/bin/env python3
"""
Tests for P0 (ExecutionAnalyzer) and P1 (Skill System) implementations.
Validates the complete closed-loop: Skill discovery → BM25 match → injection →
execution analysis → GrowthTracker feedback → skill effectiveness tracking.

Uses standalone extraction to avoid heavy import chains.
"""
import math
import os
import re
import sys
import tempfile
import time
import unittest
import shutil
from collections import Counter
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Standalone extractions (avoid agent.py import chain)
# ---------------------------------------------------------------------------

# --- Minimal AgentEvent ---
@dataclass
class AgentEvent:
    timestamp: float
    kind: str
    data: dict

# --- Minimal AgentTask ---
@dataclass
class AgentTask:
    id: str = ''
    title: str = ''
    description: str = ''
    status: str = 'done'
    result: str = ''
    tags: list = field(default_factory=list)
    rating: int = 0
    feedback_text: str = ''
    feedback_at: float = 0.0
    skill_tags: list = field(default_factory=list)

# --- Minimal GrowthTracker & SkillProgress ---
@dataclass
class SkillProgress:
    skill_id: str = ''
    skill_name: str = ''
    level: int = 1
    proficiency: float = 0.0
    total_tasks: int = 0
    success_count: int = 0
    fail_count: int = 0
    total_rating: int = 0
    last_used_at: float = 0.0
    created_at: float = field(default_factory=time.time)
    def apply_feedback(self, rating):
        self.total_tasks += 1
        self.total_rating += rating
        self.last_used_at = time.time()
        if rating >= 4: self.success_count += 1
        elif rating <= 2: self.fail_count += 1
        gain = 0.0
        if rating >= 4: gain = max(2.0, 20.0 - self.level * 1.5)
        elif rating == 3: gain = max(1.0, 8.0 - self.level * 0.5)
        self.proficiency += gain
        leveled_up = False
        if self.proficiency >= 100.0 and self.level < 10:
            self.proficiency -= 100.0
            self.level += 1
            leveled_up = True
        return {'leveled_up': leveled_up, 'proficiency_gain': gain, 'new_level': self.level}

@dataclass
class GrowthTracker:
    skill_progress: dict = field(default_factory=dict)
    growth_events: list = field(default_factory=list)
    total_tasks_completed: int = 0
    total_feedback_count: int = 0
    total_positive_feedback: int = 0
    created_at: float = field(default_factory=time.time)
    def get_or_create_skill(self, skill_id, skill_name=''):
        if skill_id not in self.skill_progress:
            self.skill_progress[skill_id] = SkillProgress(skill_id=skill_id, skill_name=skill_name or skill_id)
        return self.skill_progress[skill_id]

# --- Mock Agent ---
class MockAgent:
    def __init__(self):
        self.id = 'test_agent_01'
        self.name = 'TestAgent'
        self.events = []
        self.tasks = []
        self.growth_tracker = GrowthTracker()
        self.bound_skill_ids = []
        self._execution_analyzer = None
        self._active_skill_ids = []


# ===========================================================================
# Test P0: ExecutionAnalyzer
# ===========================================================================

class TestExecutionAnalyzer(unittest.TestCase):

    def test_01_analyzer_basic(self):
        """ExecutionAnalyzer extracts insights from events."""
        # Import standalone (the module has minimal deps)
        sys.path.insert(0, '.')
        from app.core.execution_analyzer import ExecutionAnalyzer, ExecutionAnalysis

        analyzer = ExecutionAnalyzer()
        agent = MockAgent()
        now = time.time()

        # Simulate: user asked question → tool_call bash → tool_result OK → assistant response
        agent.events = [
            AgentEvent(now, 'tool_call', {'name': 'bash', 'arguments': {'command': 'python test.py'}}),
            AgentEvent(now + 1, 'tool_result', {'name': 'bash', 'result': 'All tests passed'}),
            AgentEvent(now + 2, 'tool_call', {'name': 'write_file', 'arguments': {'path': 'out.txt', 'content': 'done'}}),
            AgentEvent(now + 3, 'tool_result', {'name': 'write_file', 'result': 'OK'}),
            AgentEvent(now + 4, 'message', {'role': 'assistant', 'content': 'Task completed!'}),
        ]

        analysis = analyzer.analyze_chat_events(agent, task_id='test_01')
        print(f"  Analysis: completed={analysis.task_completed}, rating={analysis.auto_rating}, "
              f"tools={analysis.tools_used}, errors={analysis.error_count}")

        self.assertTrue(analysis.task_completed)
        self.assertEqual(analysis.auto_rating, 5)
        self.assertIn('bash', analysis.tools_used)
        self.assertIn('write_file', analysis.tools_used)
        self.assertEqual(analysis.tool_call_count, 2)
        self.assertEqual(analysis.error_count, 0)
        self.assertIn('python', analysis.inferred_skill_tags)
        self.assertIn('file_ops', analysis.inferred_skill_tags)
        print('  P0 basic analysis: OK ✓')

    def test_02_analyzer_errors(self):
        """Analyzer detects errors and downgrades rating."""
        from app.core.execution_analyzer import ExecutionAnalyzer

        analyzer = ExecutionAnalyzer()
        agent = MockAgent()
        now = time.time()

        agent.events = [
            AgentEvent(now, 'tool_call', {'name': 'mcp_call', 'arguments': {}}),
            AgentEvent(now + 1, 'tool_result', {'name': 'mcp_call', 'result': 'Error: Connection refused'}),
            AgentEvent(now + 2, 'tool_call', {'name': 'mcp_call', 'arguments': {}}),
            AgentEvent(now + 3, 'tool_result', {'name': 'mcp_call', 'result': 'Error: Connection refused'}),
            AgentEvent(now + 4, 'tool_call', {'name': 'mcp_call', 'arguments': {}}),
            AgentEvent(now + 5, 'tool_result', {'name': 'mcp_call', 'result': 'Error: Connection refused'}),
            AgentEvent(now + 6, 'message', {'role': 'assistant', 'content': 'Failed to connect'}),
        ]

        analysis = analyzer.analyze_chat_events(agent, task_id='test_02')
        print(f"  Analysis: completed={analysis.task_completed}, rating={analysis.auto_rating}, "
              f"errors={analysis.error_count}, issues={len(analysis.tool_issues)}")

        self.assertTrue(analysis.error_count >= 3)
        self.assertTrue(analysis.auto_rating <= 3)
        self.assertTrue(len(analysis.tool_issues) > 0)
        # Check issue details
        mcp_issue = analysis.tool_issues[0]
        self.assertEqual(mcp_issue.tool_name, 'mcp_call')
        self.assertEqual(mcp_issue.severity, 'high')
        print('  P0 error detection: OK ✓')

    def test_03_analyzer_serialization(self):
        """ExecutionAnalysis round-trips through dict."""
        from app.core.execution_analyzer import ExecutionAnalysis, ToolIssue

        a = ExecutionAnalysis(
            task_id='ser_test', agent_id='a1', task_completed=True,
            auto_rating=4, execution_note='Test note',
            tool_issues=[ToolIssue(tool_name='bash', issue_type='error',
                                   description='oops', severity='low')],
            tools_used=['bash', 'read_file'],
            inferred_skill_tags=['shell', 'file_ops'],
        )
        d = a.to_dict()
        a2 = ExecutionAnalysis.from_dict(d)
        self.assertEqual(a2.task_id, 'ser_test')
        self.assertEqual(a2.auto_rating, 4)
        self.assertEqual(len(a2.tool_issues), 1)
        self.assertEqual(a2.tool_issues[0].tool_name, 'bash')
        print('  P0 serialization: OK ✓')

    def test_04_analyze_and_grow(self):
        """analyze_and_grow feeds analysis into GrowthTracker."""
        from app.core.execution_analyzer import analyze_and_grow

        agent = MockAgent()
        now = time.time()

        # Add a task with skill tags
        task = AgentTask(id='task_grow', title='Deploy app', skill_tags=['devops', 'shell'])
        agent.tasks.append(task)

        agent.events = [
            AgentEvent(now, 'tool_call', {'name': 'bash', 'arguments': {'command': 'docker build .'}}),
            AgentEvent(now + 1, 'tool_result', {'name': 'bash', 'result': 'Image built OK'}),
            AgentEvent(now + 2, 'message', {'role': 'assistant', 'content': 'Deployed!'}),
        ]

        analysis = analyze_and_grow(agent, task_id='task_grow', start_time=now - 1)

        self.assertEqual(analysis.auto_rating, 5)
        self.assertTrue(agent.growth_tracker.total_tasks_completed >= 1)
        # Check skills were updated
        self.assertIn('devops', agent.growth_tracker.skill_progress)
        self.assertIn('shell', agent.growth_tracker.skill_progress)
        # Check growth events were generated
        auto_events = [e for e in agent.growth_tracker.growth_events if e['type'] == 'auto_analysis']
        self.assertTrue(len(auto_events) > 0)
        print(f'  P0 analyze_and_grow: skills={list(agent.growth_tracker.skill_progress.keys())}, '
              f'events={len(agent.growth_tracker.growth_events)}')
        print('  P0 analyze_and_grow: OK ✓')


# ===========================================================================
# Test P1: Skill System
# ===========================================================================

class TestSkillSystem(unittest.TestCase):

    def setUp(self):
        """Create temp skill directories."""
        self.tmpdir = tempfile.mkdtemp(prefix='tudou_skill_test_')
        # Create skill 1
        skill1_dir = os.path.join(self.tmpdir, 'email_skill')
        os.makedirs(skill1_dir)
        with open(os.path.join(skill1_dir, 'SKILL.md'), 'w') as f:
            f.write("""---
name: Email Automation
description: Automate sending emails via SMTP MCP server
category: workflow
tags: email, smtp, automation, mcp
---

# Email Automation

Use the MCP email server to send emails. Steps:
1. Call mcp_call with mcp_id='email'
2. Use tool 'send_email' with recipients, subject, body
3. Check result for delivery confirmation
""")

        # Create skill 2
        skill2_dir = os.path.join(self.tmpdir, 'git_workflow')
        os.makedirs(skill2_dir)
        with open(os.path.join(skill2_dir, 'SKILL.md'), 'w') as f:
            f.write("""---
name: Git Workflow
description: Standard git workflow for code reviews and PRs
category: tool_guide
tags: git, code_review, pull_request
---

# Git Workflow

1. Create feature branch
2. Make changes
3. Commit with descriptive message
4. Push and create PR
""")

        # Create skill 3
        skill3_dir = os.path.join(self.tmpdir, 'data_analysis')
        os.makedirs(skill3_dir)
        with open(os.path.join(skill3_dir, 'SKILL.md'), 'w') as f:
            f.write("""---
name: Data Analysis Pipeline
description: 数据分析流程，使用Python进行数据处理和可视化
category: workflow
tags: python, data, pandas, visualization, 数据分析
---

# 数据分析流程

1. 读取数据文件 (CSV/Excel)
2. 数据清洗与预处理
3. 统计分析
4. 生成可视化图表
5. 输出报告
""")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_05_parse_skill_md(self):
        """Parse SKILL.md files with YAML frontmatter."""
        sys.path.insert(0, '.')
        from app.core.skill_system import parse_skill_md

        path = os.path.join(self.tmpdir, 'email_skill', 'SKILL.md')
        record = parse_skill_md(path)

        self.assertIsNotNone(record)
        self.assertEqual(record.name, 'Email Automation')
        self.assertIn('email', record.tags)
        self.assertIn('mcp', record.tags)
        self.assertEqual(record.category, 'workflow')
        self.assertTrue(record.skill_id)
        self.assertIn('mcp_call', record.content)
        print(f'  P1 parse_skill_md: name={record.name}, id={record.skill_id}, tags={record.tags}')
        print('  P1 parse_skill_md: OK ✓')

    def test_06_skill_store_scan(self):
        """SkillStore scans directories for SKILL.md files."""
        from app.core.skill_system import SkillStore

        store = SkillStore()
        store.add_scan_dir(self.tmpdir)
        new_count = store.scan()

        self.assertEqual(new_count, 3)
        self.assertEqual(len(store.get_active()), 3)
        stats = store.get_stats()
        self.assertEqual(stats['active'], 3)
        print(f'  P1 SkillStore scan: found {new_count} skills, stats={stats}')
        print('  P1 SkillStore scan: OK ✓')

    def test_07_bm25_ranker(self):
        """BM25 ranker matches skills by relevance."""
        from app.core.skill_system import SkillStore, BM25Ranker

        store = SkillStore()
        store.add_scan_dir(self.tmpdir)
        store.scan()

        ranker = BM25Ranker()
        ranker.index(store.get_active())

        # Query about email
        results = ranker.query("send an email to the team", top_k=3)
        print(f'  BM25 "email": {[(sid[:20], round(score, 2)) for sid, score in results]}')
        self.assertTrue(len(results) > 0)
        top_id = results[0][0]
        top_skill = store.get(top_id)
        self.assertIn('email', top_skill.name.lower())

        # Query about git
        results2 = ranker.query("create pull request for code review", top_k=3)
        print(f'  BM25 "git PR": {[(sid[:20], round(score, 2)) for sid, score in results2]}')
        self.assertTrue(len(results2) > 0)
        top_id2 = results2[0][0]
        top_skill2 = store.get(top_id2)
        self.assertIn('git', top_skill2.name.lower())

        # Query in Chinese
        results3 = ranker.query("数据分析 python 可视化", top_k=3)
        print(f'  BM25 "数据分析": {[(sid[:20], round(score, 2)) for sid, score in results3]}')
        self.assertTrue(len(results3) > 0)
        top_id3 = results3[0][0]
        top_skill3 = store.get(top_id3)
        self.assertIn('data', top_skill3.name.lower())

        print('  P1 BM25 ranker: OK ✓')

    def test_08_skill_registry(self):
        """SkillRegistry provides high-level discovery + matching."""
        from app.core.skill_system import SkillRegistry, SkillStore

        store = SkillStore()
        registry = SkillRegistry(store=store)

        # Discover skills
        new = registry.discover([self.tmpdir])
        self.assertEqual(new, 3)

        # Match skills (use English for reliable BM25 match)
        matched = registry.match_skills("send email to team via smtp automation", top_k=2)
        print(f'  Registry match "email": {[s.name for s in matched]}')
        self.assertTrue(len(matched) > 0)

        # Build context injection
        skill_ids = [s.skill_id for s in matched]
        context = registry.build_context_injection(skill_ids)
        self.assertIn('可用技能参考', context)
        self.assertTrue('Email' in context or 'email' in context.lower())
        print(f'  Context injection: {len(context)} chars')

        # Check selection tracking (build_context_injection tracks selections)
        for s in matched:
            record = registry.store.get(s.skill_id)
            self.assertTrue(record.total_selections > 0)
        print('  P1 SkillRegistry: OK ✓')

    def test_09_skill_applied_tracking(self):
        """Mark skills as applied/not-applied after execution."""
        from app.core.skill_system import SkillRegistry, SkillStore

        store = SkillStore()
        registry = SkillRegistry(store=store)
        registry.discover([self.tmpdir])

        matched = registry.match_skills("send email via smtp", top_k=1)
        self.assertTrue(len(matched) > 0)
        sid = matched[0].skill_id

        # Build context injection first (this tracks total_selections)
        registry.build_context_injection([sid])

        # Mark applied
        registry.mark_skill_applied(sid, applied=True, task_completed=True)
        record = registry.store.get(sid)
        self.assertEqual(record.total_applied, 1)
        self.assertEqual(record.total_completions, 1)
        self.assertTrue(record.total_selections > 0, "Selections should be tracked by build_context_injection")
        self.assertTrue(record.effectiveness > 0)

        # Mark fallback
        registry.mark_skill_applied(sid, applied=False)
        self.assertEqual(record.total_fallbacks, 1)
        print(f'  Skill effectiveness: {record.effectiveness}%, completions: {record.completion_rate}%')
        print('  P1 skill tracking: OK ✓')

    def test_10_store_serialization(self):
        """SkillStore/Registry round-trip through dict."""
        from app.core.skill_system import SkillRegistry, SkillStore

        store = SkillStore()
        registry = SkillRegistry(store=store)
        registry.discover([self.tmpdir])

        # Serialize
        d = registry.to_dict()
        self.assertIn('skills', d)
        self.assertEqual(len(d['skills']), 3)

        # Deserialize
        registry2 = SkillRegistry.from_dict(d)
        self.assertEqual(len(registry2.store.get_active()), 3)

        # Matching still works after restore
        matched = registry2.match_skills("git code review", top_k=1)
        self.assertTrue(len(matched) > 0)
        print('  P1 serialization round-trip: OK ✓')


# ===========================================================================
# Test Integration: Full closed-loop
# ===========================================================================

class TestFullClosedLoop(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix='tudou_loop_test_')
        skill_dir = os.path.join(self.tmpdir, 'deploy_skill')
        os.makedirs(skill_dir)
        with open(os.path.join(skill_dir, 'SKILL.md'), 'w') as f:
            f.write("""---
name: Docker Deploy
description: Deploy applications using Docker containers
category: tool_guide
tags: docker, deploy, devops
---

# Docker Deploy Guide

1. Build image: docker build -t app .
2. Push to registry
3. Deploy to server
""")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_11_full_closed_loop(self):
        """
        Full closed-loop test:
        1. Discover skills
        2. Match skills to task
        3. Build injection context
        4. Simulate execution with events
        5. Auto-analyze
        6. Feed GrowthTracker
        7. Mark skill effectiveness
        8. Verify everything connects
        """
        sys.path.insert(0, '.')
        from app.core.skill_system import SkillRegistry, SkillStore, get_skill_registry, set_skill_registry
        from app.core.execution_analyzer import ExecutionAnalyzer, analyze_and_grow

        # Step 1: Discover
        store = SkillStore()
        registry = SkillRegistry(store=store)
        set_skill_registry(registry)  # set global
        new = registry.discover([self.tmpdir])
        self.assertEqual(new, 1)
        print(f'  Step 1 - Discover: found {new} skill')

        # Step 2: Match
        matched = registry.match_skills("deploy the docker container to production", top_k=1)
        self.assertEqual(len(matched), 1)
        self.assertIn('docker', matched[0].name.lower())
        skill_id = matched[0].skill_id
        print(f'  Step 2 - Match: {matched[0].name} (id={skill_id[:20]}...)')

        # Step 3: Build injection
        context = registry.build_context_injection([skill_id])
        self.assertIn('Docker Deploy', context)
        self.assertIn('docker build', context)
        print(f'  Step 3 - Injection: {len(context)} chars')

        # Step 4: Simulate execution
        agent = MockAgent()
        agent.bound_skill_ids = [skill_id]
        agent._active_skill_ids = [skill_id]
        now = time.time()
        task = AgentTask(id='deploy_task', title='Deploy Docker app',
                        skill_tags=['docker', 'devops'])
        agent.tasks.append(task)

        agent.events = [
            AgentEvent(now, 'tool_call', {'name': 'bash', 'arguments': {'command': 'docker build -t myapp .'}}),
            AgentEvent(now + 2, 'tool_result', {'name': 'bash', 'result': 'Successfully built myapp'}),
            AgentEvent(now + 3, 'tool_call', {'name': 'bash', 'arguments': {'command': 'docker push myapp'}}),
            AgentEvent(now + 5, 'tool_result', {'name': 'bash', 'result': 'Push complete'}),
            AgentEvent(now + 6, 'message', {'role': 'assistant', 'content': 'Docker app deployed!'}),
        ]
        print(f'  Step 4 - Execution: {len(agent.events)} events')

        # Step 5: Auto-analyze
        analysis = analyze_and_grow(agent, task_id='deploy_task', start_time=now - 1)
        self.assertEqual(analysis.auto_rating, 5)
        self.assertTrue(analysis.task_completed)
        self.assertIn('devops', analysis.inferred_skill_tags)  # docker commands → devops tag
        print(f'  Step 5 - Analysis: rating={analysis.auto_rating}, tags={analysis.inferred_skill_tags}')

        # Step 6: Verify GrowthTracker was updated
        self.assertTrue(agent.growth_tracker.total_tasks_completed >= 1)
        self.assertIn('docker', agent.growth_tracker.skill_progress)
        self.assertIn('devops', agent.growth_tracker.skill_progress)
        docker_sp = agent.growth_tracker.skill_progress['docker']
        self.assertTrue(docker_sp.total_tasks > 0)
        print(f'  Step 6 - Growth: docker level={docker_sp.level} prof={docker_sp.proficiency:.1f}%, '
              f'events={len(agent.growth_tracker.growth_events)}')

        # Step 7: Mark skill effectiveness
        registry.mark_skill_applied(skill_id, applied=True, task_completed=True)
        record = registry.store.get(skill_id)
        self.assertTrue(record.total_applied > 0)
        self.assertTrue(record.total_completions > 0)
        print(f'  Step 7 - Skill tracking: selections={record.total_selections}, '
              f'applied={record.total_applied}, effectiveness={record.effectiveness}%')

        # Step 8: Verify full chain
        self.assertTrue(record.total_selections > 0, "Skill was selected")
        self.assertTrue(record.total_applied > 0, "Skill was marked applied")
        self.assertTrue(analysis.auto_rating >= 4, "Good auto-rating")
        self.assertTrue(docker_sp.total_tasks > 0, "GrowthTracker skill updated")
        auto_events = [e for e in agent.growth_tracker.growth_events if e['type'] == 'auto_analysis']
        self.assertTrue(len(auto_events) > 0, "Auto-analysis event recorded in growth")
        print('  Step 8 - Full chain verified')
        print()
        print('  ✅ FULL CLOSED-LOOP: Discover → Match → Inject → Execute → Analyze → Grow → Track')

    def test_12_structural_checks(self):
        """Verify integration points exist in source files."""
        # Agent.chat() has skill injection (app/agent.py is the real impl)
        with open('app/agent.py') as f:
            agent_src = f.read()
        self.assertIn('get_skill_registry', agent_src)
        self.assertIn('match_skills', agent_src)
        self.assertIn('build_context_injection', agent_src)
        self.assertIn('analyze_and_grow', agent_src)
        self.assertIn('mark_skill_applied', agent_src)
        self.assertIn('bound_skill_ids', agent_src)
        self.assertIn('_active_skill_ids', agent_src)
        print('  Agent.chat() integration points: OK ✓')

        # Portal has skill/analysis endpoints (split into GET/POST files)
        with open('app/server/portal_routes_get.py') as f:
            get_src = f.read()
        with open('app/server/portal_routes_post.py') as f:
            post_src = f.read()
        portal_src = get_src + post_src
        self.assertIn('/skills', portal_src)
        self.assertIn('/analyses', portal_src)
        self.assertIn('discover', portal_src)
        self.assertIn('bind', portal_src)
        self.assertIn('unbind', portal_src)
        print('  Portal API endpoints: OK ✓')

        # Portal UI has skill panel
        with open('app/server/portal_templates.py') as f:
            ui_src = f.read()
        self.assertIn('showSkillPanel', ui_src)
        self.assertIn('showAnalysisPanel', ui_src)
        self.assertIn('unbindSkill', ui_src)
        self.assertIn('discoverSkills', ui_src)
        self.assertIn('auto_stories', ui_src)  # skill icon
        self.assertIn('analytics', ui_src)  # analysis icon
        print('  Portal UI components: OK ✓')


if __name__ == '__main__':
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    print('=' * 60)
    print(' P0 + P1 Test Suite (OpenSpace-inspired features)')
    print('=' * 60)
    print()
    unittest.main(verbosity=2)
