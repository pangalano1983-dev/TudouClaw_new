"""
Tests for Role Growth Path — 角色成长路径系统
Covers: data models, growth path templates, Agent integration, SelfImprovement integration, closed loop.
"""
import copy
import time
import unittest
from dataclasses import dataclass, field

# --- Direct imports (avoid heavy Agent import chain) ---
from app.core.role_growth_path import (
    LearningObjective,
    GrowthStage,
    RoleGrowthPath,
    ROLE_GROWTH_PATHS,
    build_learning_task_prompt,
)


class TestRoleGrowthPathModels(unittest.TestCase):
    """Test 01-04: Data models and templates."""

    def test_01_learning_objective_serialization(self):
        obj = LearningObjective(
            id="test_obj_1",
            title="Test Objective",
            description="Learn something important",
            knowledge_domains=["testing", "qa"],
            resource_hints=["Read the docs"],
            learning_prompt="Study testing frameworks",
            skill_tags=["testing"],
        )
        d = obj.to_dict()
        restored = LearningObjective.from_dict(d)
        self.assertEqual(restored.id, "test_obj_1")
        self.assertEqual(restored.title, "Test Objective")
        self.assertEqual(restored.knowledge_domains, ["testing", "qa"])
        self.assertFalse(restored.completed)

    def test_02_growth_stage_completion(self):
        objs = [
            LearningObjective(id=f"obj_{i}", title=f"Obj {i}", completed=(i < 2))
            for i in range(5)
        ]
        stage = GrowthStage(
            stage_id="junior", name="Junior",
            objectives=objs,
            min_completed_objectives=2,
        )
        self.assertEqual(stage.completion_rate, 40.0)  # 2/5
        self.assertTrue(stage.can_advance)  # 2 >= 2

        # Not enough
        stage.min_completed_objectives = 3
        self.assertFalse(stage.can_advance)

    def test_03_role_growth_path_advance(self):
        stage1 = GrowthStage(
            stage_id="junior", name="Junior",
            objectives=[LearningObjective(id="s1_o1", completed=True)],
            min_completed_objectives=1,
        )
        stage2 = GrowthStage(
            stage_id="mid", name="Mid",
            objectives=[LearningObjective(id="s2_o1")],
            min_completed_objectives=1,
        )
        gp = RoleGrowthPath(
            role="tester", role_name="测试工程师",
            stages=[stage1, stage2],
        )
        self.assertEqual(gp.current_stage_idx, 0)
        self.assertEqual(gp.overall_progress, 50.0)  # 1/2

        # Advance
        advanced = gp.try_advance()
        self.assertTrue(advanced)
        self.assertEqual(gp.current_stage_idx, 1)
        self.assertEqual(gp.current_stage.name, "Mid")

        # Can't advance past last stage
        self.assertFalse(gp.try_advance())

    def test_04_mark_objective_completed(self):
        gp = RoleGrowthPath(
            role="test", role_name="Test",
            stages=[GrowthStage(
                stage_id="s1", name="S1",
                objectives=[
                    LearningObjective(id="a"),
                    LearningObjective(id="b"),
                ],
            )],
        )
        ok = gp.mark_objective_completed("a", experience_ids=["exp_1"])
        self.assertTrue(ok)
        self.assertTrue(gp.stages[0].objectives[0].completed)
        self.assertIn("exp_1", gp.stages[0].objectives[0].experience_ids)
        self.assertEqual(gp.total_learning_sessions, 1)

        # Non-existent
        self.assertFalse(gp.mark_objective_completed("nonexistent"))

    def test_05_serialization_round_trip(self):
        gp = RoleGrowthPath(
            role="coder", role_name="开发工程师",
            stages=[
                GrowthStage(
                    stage_id="junior", name="Junior",
                    objectives=[LearningObjective(id="o1", title="T1", completed=True)],
                    min_completed_objectives=1,
                ),
                GrowthStage(
                    stage_id="mid", name="Mid",
                    objectives=[LearningObjective(id="o2", title="T2")],
                ),
            ],
            current_stage_idx=1,
            total_learning_sessions=5,
        )
        d = gp.to_dict()
        restored = RoleGrowthPath.from_dict(d)
        self.assertEqual(restored.role, "coder")
        self.assertEqual(restored.current_stage_idx, 1)
        self.assertEqual(restored.total_learning_sessions, 5)
        self.assertTrue(restored.stages[0].objectives[0].completed)
        self.assertEqual(len(restored.stages), 2)

    def test_06_get_summary(self):
        gp = RoleGrowthPath(
            role="legal", role_name="法务顾问",
            stages=[
                GrowthStage(
                    stage_id="junior", name="初级法务",
                    objectives=[
                        LearningObjective(id="o1", title="Contract Law", completed=True),
                        LearningObjective(id="o2", title="IP Law"),
                    ],
                ),
            ],
        )
        s = gp.get_summary()
        self.assertEqual(s["role"], "legal")
        self.assertEqual(s["role_name"], "法务顾问")
        self.assertEqual(s["overall_progress"], 50.0)
        self.assertIn("IP Law", s["next_objectives"])


class TestRoleTemplates(unittest.TestCase):
    """Test 07-08: Built-in role templates."""

    def test_07_all_role_templates_exist(self):
        expected_roles = [
            "legal", "coder", "designer", "pm", "data",
            "devops", "ceo", "cto", "tester", "researcher",
            "general", "reviewer",
        ]
        for role in expected_roles:
            self.assertIn(role, ROLE_GROWTH_PATHS,
                          f"Missing growth path for role '{role}'")

    def test_08_templates_structure_valid(self):
        for role, gp in ROLE_GROWTH_PATHS.items():
            self.assertTrue(gp.role, f"{role}: missing role")
            self.assertTrue(gp.role_name, f"{role}: missing role_name")
            self.assertTrue(len(gp.stages) > 0, f"{role}: no stages")
            for stage in gp.stages:
                self.assertTrue(stage.stage_id, f"{role}: stage missing id")
                self.assertTrue(stage.name, f"{role}: stage missing name")
                self.assertTrue(len(stage.objectives) > 0,
                                f"{role}/{stage.stage_id}: no objectives")
                for obj in stage.objectives:
                    self.assertTrue(obj.id, f"{role}/{stage.stage_id}: obj missing id")
                    self.assertTrue(obj.title, f"{role}/{stage.stage_id}: obj missing title")


class TestBuildLearningPrompt(unittest.TestCase):
    """Test 09: Learning prompt generation."""

    def test_09_build_learning_prompt(self):
        obj = LearningObjective(
            id="legal_contract",
            title="中国合同法核心条款",
            description="学习中国合同法的关键条款",
            knowledge_domains=["contract_law"],
            resource_hints=["中国民法典合同编"],
            learning_prompt="重点学习合同成立、效力、履行相关条款",
        )
        prompt = build_learning_task_prompt(obj, role_name="法务顾问")
        self.assertIn("法务顾问", prompt)
        self.assertIn("中国合同法核心条款", prompt)
        self.assertIn("中国民法典合同编", prompt)
        self.assertIn("核心知识点", prompt)


class TestAgentGrowthPathIntegration(unittest.TestCase):
    """Test 10-11: Agent integration (without full Agent import chain)."""

    def test_10_deepcopy_template(self):
        """Ensure ensure_growth_path creates independent copies."""
        template = ROLE_GROWTH_PATHS.get("legal")
        self.assertIsNotNone(template)

        copy1 = copy.deepcopy(template)
        copy2 = copy.deepcopy(template)

        # Modify copy1
        copy1.mark_objective_completed(copy1.stages[0].objectives[0].id)
        # copy2 should not be affected
        self.assertFalse(copy2.stages[0].objectives[0].completed)
        self.assertTrue(copy1.stages[0].objectives[0].completed)

    def test_11_growth_path_in_persist_dict(self):
        """Test growth path serialization mimicking Agent persist pattern."""
        gp = copy.deepcopy(ROLE_GROWTH_PATHS["coder"])
        gp.mark_objective_completed(gp.stages[0].objectives[0].id)

        # Simulate to_persist_dict
        persist = {"growth_path": gp.to_dict()}
        # Simulate from_persist_dict
        restored_gp = RoleGrowthPath.from_dict(persist["growth_path"])
        self.assertEqual(restored_gp.role, "coder")
        self.assertTrue(restored_gp.stages[0].objectives[0].completed)
        self.assertEqual(restored_gp.total_learning_sessions, 1)


class TestSelfImprovementIntegration(unittest.TestCase):
    """Test 12: SelfImprovementEngine + Growth Path integration."""

    def test_12_growth_path_driven_learning(self):
        """Simulate the full growth-path-driven active learning loop."""
        # 1. Create a growth path
        gp = copy.deepcopy(ROLE_GROWTH_PATHS["legal"])
        self.assertTrue(len(gp.stages) > 0)
        self.assertTrue(len(gp.stages[0].objectives) > 0)

        # 2. Get next objective
        next_objs = gp.get_next_objectives(limit=1)
        self.assertEqual(len(next_objs), 1)
        obj = next_objs[0]
        self.assertFalse(obj.completed)

        # 3. Generate learning prompt
        prompt = build_learning_task_prompt(obj, gp.role_name)
        self.assertIn(obj.title, prompt)
        self.assertTrue(len(prompt) > 50)

        # 4. Simulate learning completion — mark objective done
        gp.mark_objective_completed(obj.id, experience_ids=["exp_sim_1", "exp_sim_2"])
        self.assertTrue(obj.completed)
        self.assertIn("exp_sim_1", obj.experience_ids)
        self.assertEqual(gp.total_learning_sessions, 1)

        # 5. Check if stage advance works after all objectives done
        stage = gp.current_stage
        for o in stage.objectives:
            if not o.completed:
                gp.mark_objective_completed(o.id)

        # Try advance
        if gp.current_stage_idx + 1 < len(gp.stages):
            advanced = gp.try_advance()
            self.assertTrue(advanced)
            self.assertEqual(gp.current_stage_idx, 1)


class TestFullClosedLoop(unittest.TestCase):
    """Test 13: Full closed-loop structural verification."""

    def test_13_structural_completeness(self):
        """Verify all integration points are properly wired via source reading."""
        import os

        base = os.path.dirname(os.path.abspath(__file__))

        # 1. role_growth_path.py has required exports
        from app.core.role_growth_path import (
            LearningObjective, GrowthStage, RoleGrowthPath,
            ROLE_GROWTH_PATHS, build_learning_task_prompt,
        )

        # 2-5. Agent.py source checks (avoid importing due to heavy deps)
        with open(os.path.join(base, "app/agent.py")) as f:
            agent_src = f.read()
        self.assertIn("from .core.role_growth_path import RoleGrowthPath", agent_src)
        self.assertIn("growth_path: RoleGrowthPath", agent_src)
        self.assertIn("ensure_growth_path", agent_src)
        self.assertIn("get_next_learning_objective", agent_src)
        # Persistence
        self.assertIn('"growth_path": self.growth_path.to_dict()', agent_src)
        self.assertIn('RoleGrowthPath.from_dict(d["growth_path"])', agent_src)
        # API serialization
        self.assertIn('self.growth_path.get_summary()', agent_src)

        # 6. SelfImprovementEngine references growth path (root-level file)
        with open(os.path.join(base, "app/experience_library.py")) as f:
            exp_src = f.read()
        self.assertIn("get_next_learning_objective", exp_src)
        self.assertIn("growth_path", exp_src)
        self.assertIn("mark_objective_completed", exp_src)
        self.assertIn("objective_id", exp_src)

        # 7. Portal endpoints (split into GET/POST route files)
        with open(os.path.join(base, "app/server/portal_routes_get.py")) as f:
            get_src = f.read()
        with open(os.path.join(base, "app/server/portal_routes_post.py")) as f:
            post_src = f.read()
        portal_src = get_src + post_src
        self.assertIn("/growth", portal_src)
        self.assertIn("growth-paths", portal_src)
        self.assertIn("trigger_learning", portal_src)
        self.assertIn("complete_objective", portal_src)

        # 8. Portal UI
        with open(os.path.join(base, "app/server/portal_templates.py")) as f:
            pt_src = f.read()
        self.assertIn("showGrowthPathPanel", pt_src)
        self.assertIn("completeObjective", pt_src)
        self.assertIn("triggerGrowthLearning", pt_src)
        self.assertIn("Role Growth", pt_src)

        print("\n✅ All 8 structural integration points verified")


if __name__ == "__main__":
    unittest.main(verbosity=2)
