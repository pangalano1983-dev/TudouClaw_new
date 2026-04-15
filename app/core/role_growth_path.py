"""
Role Growth Path — 角色成长路径系统

为每个 Agent 角色定义结构化的自我成长路径:
- 阶段制成长 (初级→中级→高级→专家)
- 每阶段定义: 需要掌握的知识领域、学习目标、关键技能指标
- 主动学习任务生成: 根据当前阶段和已掌握知识，生成下一步学习任务
- 与 SelfImprovementEngine 集成: 学习成果沉淀为 Experience

设计理念:
- 不同角色有完全不同的成长路径 (法务 ≠ 开发 ≠ 设计)
- 每个阶段有明确的学习资源指引 (公开法律/RFC/设计规范等)
- 进度可量化, 与 GrowthTracker 的 SkillProgress 联动
"""
from __future__ import annotations
import time
from dataclasses import dataclass, field

from ..infra.logging import get_logger

logger = get_logger("tudou.role_growth_path")


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

@dataclass
class LearningObjective:
    """一个具体的学习目标."""
    id: str = ""
    title: str = ""                   # e.g. "中国《合同法》核心条款"
    description: str = ""             # 详细描述要学什么
    knowledge_domains: list[str] = field(default_factory=list)  # ["contract_law", "china_law"]
    resource_hints: list[str] = field(default_factory=list)     # 学习资源提示
    learning_prompt: str = ""         # 给 Agent 的学习指令
    skill_tags: list[str] = field(default_factory=list)         # 完成后关联的技能
    estimated_sessions: int = 1       # 预计需要几次学习
    # --- Progress ---
    completed: bool = False
    completed_at: float = 0.0
    experience_ids: list[str] = field(default_factory=list)  # 生成的经验ID

    def to_dict(self) -> dict:
        return {
            "id": self.id, "title": self.title,
            "description": self.description,
            "knowledge_domains": self.knowledge_domains,
            "resource_hints": self.resource_hints,
            "learning_prompt": self.learning_prompt,
            "skill_tags": self.skill_tags,
            "estimated_sessions": self.estimated_sessions,
            "completed": self.completed,
            "completed_at": self.completed_at,
            "experience_ids": self.experience_ids,
        }

    @staticmethod
    def from_dict(d: dict) -> LearningObjective:
        return LearningObjective(
            id=d.get("id", ""), title=d.get("title", ""),
            description=d.get("description", ""),
            knowledge_domains=d.get("knowledge_domains", []),
            resource_hints=d.get("resource_hints", []),
            learning_prompt=d.get("learning_prompt", ""),
            skill_tags=d.get("skill_tags", []),
            estimated_sessions=d.get("estimated_sessions", 1),
            completed=d.get("completed", False),
            completed_at=d.get("completed_at", 0.0),
            experience_ids=d.get("experience_ids", []),
        )


@dataclass
class GrowthStage:
    """成长阶段 (e.g. 初级→中级→高级→专家)."""
    stage_id: str = ""            # "junior", "mid", "senior", "expert"
    name: str = ""                # "初级法务助理"
    description: str = ""         # 阶段说明
    level_range: tuple[int, int] = (1, 3)  # SkillProgress level range
    objectives: list[LearningObjective] = field(default_factory=list)
    # Requirements to advance
    min_completed_objectives: int = 0    # 至少完成几个目标才能进阶
    min_total_tasks: int = 0             # 至少完成几个任务
    min_avg_rating: float = 0.0          # 最低平均评分

    @property
    def completion_rate(self) -> float:
        if not self.objectives:
            return 0.0
        done = sum(1 for o in self.objectives if o.completed)
        return round(done / len(self.objectives) * 100, 1)

    @property
    def can_advance(self) -> bool:
        done = sum(1 for o in self.objectives if o.completed)
        return done >= self.min_completed_objectives

    def to_dict(self) -> dict:
        return {
            "stage_id": self.stage_id, "name": self.name,
            "description": self.description,
            "level_range": list(self.level_range),
            "objectives": [o.to_dict() for o in self.objectives],
            "min_completed_objectives": self.min_completed_objectives,
            "min_total_tasks": self.min_total_tasks,
            "min_avg_rating": self.min_avg_rating,
            "completion_rate": self.completion_rate,
        }

    @staticmethod
    def from_dict(d: dict) -> GrowthStage:
        lr = d.get("level_range", [1, 3])
        return GrowthStage(
            stage_id=d.get("stage_id", ""),
            name=d.get("name", ""),
            description=d.get("description", ""),
            level_range=tuple(lr) if len(lr) == 2 else (1, 3),
            objectives=[LearningObjective.from_dict(o) for o in d.get("objectives", [])],
            min_completed_objectives=d.get("min_completed_objectives", 0),
            min_total_tasks=d.get("min_total_tasks", 0),
            min_avg_rating=d.get("min_avg_rating", 0.0),
        )


@dataclass
class RoleGrowthPath:
    """完整的角色成长路径."""
    role: str = ""                    # "legal", "coder", "designer", etc.
    role_name: str = ""               # "法务顾问"
    description: str = ""             # 角色成长路径总述
    stages: list[GrowthStage] = field(default_factory=list)
    current_stage_idx: int = 0        # 当前所在阶段
    total_learning_sessions: int = 0  # 总学习次数
    last_learning_at: float = 0.0

    @property
    def current_stage(self) -> GrowthStage | None:
        if 0 <= self.current_stage_idx < len(self.stages):
            return self.stages[self.current_stage_idx]
        return None

    @property
    def overall_progress(self) -> float:
        """Overall completion across all stages, 0-100%."""
        if not self.stages:
            return 0.0
        total_objs = sum(len(s.objectives) for s in self.stages)
        done_objs = sum(1 for s in self.stages for o in s.objectives if o.completed)
        return round(done_objs / total_objs * 100, 1) if total_objs else 0.0

    def get_next_objectives(self, limit: int = 3) -> list[LearningObjective]:
        """Get next uncompleted objectives from current stage."""
        stage = self.current_stage
        if not stage:
            return []
        return [o for o in stage.objectives if not o.completed][:limit]

    def try_advance(self) -> bool:
        """Check if can advance to next stage. Returns True if advanced."""
        stage = self.current_stage
        if not stage:
            return False
        if stage.can_advance and self.current_stage_idx + 1 < len(self.stages):
            self.current_stage_idx += 1
            logger.info("RoleGrowthPath: %s advanced to stage %d: %s",
                        self.role, self.current_stage_idx, self.stages[self.current_stage_idx].name)
            return True
        return False

    def mark_objective_completed(self, objective_id: str,
                                  experience_ids: list[str] | None = None) -> bool:
        """Mark a learning objective as completed."""
        for stage in self.stages:
            for obj in stage.objectives:
                if obj.id == objective_id:
                    obj.completed = True
                    obj.completed_at = time.time()
                    if experience_ids:
                        obj.experience_ids.extend(experience_ids)
                    self.total_learning_sessions += 1
                    self.last_learning_at = time.time()
                    return True
        return False

    # ─── Eval-driven completion (P2 #7) ───

    def find_objective(self, objective_id: str) -> LearningObjective | None:
        for stage in self.stages:
            for obj in stage.objectives:
                if obj.id == objective_id:
                    return obj
        return None

    def evaluate_objective_completion(
        self, objective_id: str,
        new_experiences: list[dict],
    ) -> tuple[bool, float, str]:
        """
        Eval-driven check before marking a learning objective as done.

        Scores a set of newly-produced experience dicts against the objective's
        expected knowledge_domains and skill_tags. An objective only gets
        marked complete when the score crosses a threshold — otherwise it
        stays open and the agent is asked to keep learning.

        Returns (passed, score_0_to_1, reason).
        """
        obj = self.find_objective(objective_id)
        if not obj:
            return False, 0.0, "objective not found"
        if not new_experiences:
            return False, 0.0, "no experiences produced"

        expected_tags = {t.lower() for t in (obj.skill_tags or [])}
        expected_domains = {d.lower() for d in (obj.knowledge_domains or [])}

        # Collect all tags + content tokens from produced experiences
        seen_tags: set[str] = set()
        content_blob = ""
        for e in new_experiences:
            for t in (e.get("tags") or []):
                seen_tags.add(str(t).lower())
            content_blob += " ".join([
                str(e.get("scene") or ""),
                str(e.get("core_knowledge") or ""),
                " ".join(e.get("action_rules") or []),
            ]).lower() + " "

        tag_cover = 0.0
        if expected_tags:
            hits = len(expected_tags & seen_tags)
            tag_cover = hits / len(expected_tags)

        domain_cover = 0.0
        if expected_domains:
            hits = sum(1 for d in expected_domains if d in content_blob)
            domain_cover = hits / len(expected_domains)

        # Depth signal: at least one experience with non-empty action_rules
        depth_ok = any((e.get("action_rules") or []) for e in new_experiences)

        # Weighted score
        if expected_tags or expected_domains:
            score = 0.5 * tag_cover + 0.4 * domain_cover + (0.1 if depth_ok else 0.0)
        else:
            # No expectations defined: accept any substantive experience
            score = 0.8 if depth_ok else 0.5

        threshold = 0.5
        passed = score >= threshold

        reason_parts = []
        if expected_tags:
            reason_parts.append(f"tags {int(tag_cover * 100)}%")
        if expected_domains:
            reason_parts.append(f"domains {int(domain_cover * 100)}%")
        reason_parts.append("has_action_rules" if depth_ok else "missing_action_rules")
        reason = ", ".join(reason_parts)

        return passed, round(score, 2), reason

    def evaluate_and_complete(
        self, objective_id: str,
        new_experiences: list[dict],
        experience_ids: list[str] | None = None,
    ) -> dict:
        """Evaluate an objective and, if it passes, mark it completed.

        Returns a dict with keys: passed, score, reason, completed.
        """
        passed, score, reason = self.evaluate_objective_completion(
            objective_id, new_experiences,
        )
        completed = False
        if passed:
            completed = self.mark_objective_completed(
                objective_id, experience_ids=experience_ids,
            )
        else:
            logger.info(
                "GrowthPath eval: objective %s NOT completed (score=%.2f, %s)",
                objective_id, score, reason,
            )
        return {
            "passed": passed,
            "score": score,
            "reason": reason,
            "completed": completed,
        }

    def get_summary(self) -> dict:
        stage = self.current_stage
        return {
            "role": self.role,
            "role_name": self.role_name,
            "current_stage": stage.name if stage else "未开始",
            "current_stage_idx": self.current_stage_idx,
            "stage_count": len(self.stages),
            "overall_progress": self.overall_progress,
            "stage_progress": stage.completion_rate if stage else 0,
            "next_objectives": [o.title for o in self.get_next_objectives(3)],
            "total_learning_sessions": self.total_learning_sessions,
            "stages": [
                {"name": s.name, "completion": s.completion_rate,
                 "objectives": len(s.objectives)}
                for s in self.stages
            ],
        }

    def to_dict(self) -> dict:
        return {
            "role": self.role, "role_name": self.role_name,
            "description": self.description,
            "stages": [s.to_dict() for s in self.stages],
            "current_stage_idx": self.current_stage_idx,
            "total_learning_sessions": self.total_learning_sessions,
            "last_learning_at": self.last_learning_at,
        }

    @staticmethod
    def from_dict(d: dict) -> RoleGrowthPath:
        return RoleGrowthPath(
            role=d.get("role", ""),
            role_name=d.get("role_name", ""),
            description=d.get("description", ""),
            stages=[GrowthStage.from_dict(s) for s in d.get("stages", [])],
            current_stage_idx=d.get("current_stage_idx", 0),
            total_learning_sessions=d.get("total_learning_sessions", 0),
            last_learning_at=d.get("last_learning_at", 0.0),
        )


# ---------------------------------------------------------------------------
# Learning Prompt Generator
# ---------------------------------------------------------------------------

def build_learning_task_prompt(objective: LearningObjective, role_name: str = "") -> str:
    """
    Generate a learning prompt for the Agent to execute.
    This is injected as a task for the agent to process.
    """
    parts = []
    parts.append(f"## 主动学习任务 — {role_name or '角色成长'}")
    parts.append(f"\n### 学习目标: {objective.title}")
    parts.append(f"\n{objective.description}")

    if objective.learning_prompt:
        parts.append(f"\n### 学习指引\n{objective.learning_prompt}")

    if objective.resource_hints:
        parts.append("\n### 参考资源")
        for hint in objective.resource_hints:
            parts.append(f"- {hint}")

    if objective.knowledge_domains:
        parts.append(f"\n### 涉及知识领域: {', '.join(objective.knowledge_domains)}")

    parts.append("\n### 输出要求")
    parts.append("请完成学习后，总结出以下内容:")
    parts.append("1. **核心知识点**: 学到的关键知识（3-5条）")
    parts.append("2. **实操规则**: 在实际工作中应该遵循的规则（2-3条）")
    parts.append("3. **禁忌事项**: 需要避免的常见错误（1-2条）")
    parts.append("4. **适用场景**: 这些知识在什么场景下使用")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Built-in Role Growth Path Templates
# ---------------------------------------------------------------------------

def _make_obj(id: str, title: str, desc: str, domains: list, hints: list,
              prompt: str = "", tags: list = None, sessions: int = 1) -> LearningObjective:
    return LearningObjective(
        id=id, title=title, description=desc,
        knowledge_domains=domains, resource_hints=hints,
        learning_prompt=prompt, skill_tags=tags or domains,
        estimated_sessions=sessions,
    )


ROLE_GROWTH_PATHS: dict[str, RoleGrowthPath] = {}


def _register(path: RoleGrowthPath):
    ROLE_GROWTH_PATHS[path.role] = path


# ============================================================
# 法务 (Legal)
# ============================================================
_register(RoleGrowthPath(
    role="legal", role_name="法务顾问",
    description="从法律基础知识到跨境合规专家的完整成长路径",
    stages=[
        GrowthStage(
            stage_id="junior", name="初级法务助理", level_range=(1, 3),
            description="掌握基础法律框架和常见法务工作流程",
            min_completed_objectives=4, min_total_tasks=10,
            objectives=[
                _make_obj("LEG-J01", "中国《民法典》合同编核心条款",
                          "学习合同成立、效力、履行、违约责任等基本概念",
                          ["contract_law", "china_law"],
                          ["《民法典》全文（公开）", "最高人民法院合同纠纷司法解释"],
                          "请学习中国《民法典》合同编（第三编）的核心条款，包括：合同的订立（要约与承诺）、合同效力、合同履行规则、违约责任与免责事由。总结关键条款及其实务应用要点。"),
                _make_obj("LEG-J02", "知识产权基础（著作权、商标、专利）",
                          "了解三大知识产权类型的保护范围、申请流程、侵权判定",
                          ["ip_law", "copyright", "trademark", "patent"],
                          ["《著作权法》《商标法》《专利法》", "国家知识产权局公开文件"],
                          "请学习中国知识产权法的基础框架：著作权（自动取得、保护期限、合理使用）、商标权（注册流程、驰名商标保护）、专利权（发明/实用新型/外观设计区别、申请流程）。"),
                _make_obj("LEG-J03", "劳动法与雇佣关系",
                          "掌握劳动合同签订、解除、补偿的基本规则",
                          ["labor_law"],
                          ["《劳动法》《劳动合同法》", "各地劳动仲裁委公开案例"],
                          "请学习中国劳动法核心内容：劳动合同类型（固定/无固定/完成任务期限）、试用期规则、经济补偿金计算、违法解除赔偿金、竞业限制与保密协议。"),
                _make_obj("LEG-J04", "公司法基础与公司治理",
                          "了解公司设立、股东权利、董事责任等基本概念",
                          ["corporate_law", "governance"],
                          ["《公司法》（2023修订版）", "公司登记管理条例"],
                          "学习中国《公司法》核心内容：公司设立条件、股东权利义务、董事会和监事会职责、公司资本制度、股权转让规则。"),
                _make_obj("LEG-J05", "合同审查实务",
                          "学习合同审查的基本方法论和常见风险点",
                          ["contract_review", "risk_management"],
                          ["合同审查实务指南（法律出版社）", "企业法务常见问题汇编"],
                          "请学习合同审查的基本方法：审查清单（主体资格、权利义务对等、违约条款、争议解决）、常见风险条款识别、修改建议的撰写规范。"),
            ],
        ),
        GrowthStage(
            stage_id="mid", name="中级法务专员", level_range=(3, 6),
            description="深入行业合规、数据保护、争议解决等专业领域",
            min_completed_objectives=4, min_total_tasks=30,
            objectives=[
                _make_obj("LEG-M01", "数据保护与隐私合规 (PIPL/GDPR)",
                          "掌握中国《个人信息保护法》和欧盟 GDPR 的核心要求",
                          ["data_protection", "privacy", "gdpr", "pipl"],
                          ["《个人信息保护法》全文", "GDPR 官方文本 (EUR-Lex)", "国家互联网信息办公室执法案例"],
                          "对比学习中国 PIPL 和欧盟 GDPR：个人信息定义、处理的合法性基础、数据主体权利、跨境传输规则、数据处理者义务、违规处罚标准。",
                          ["data_protection", "privacy", "compliance"], 2),
                _make_obj("LEG-M02", "反垄断与反不正当竞争",
                          "学习反垄断法的基本框架和互联网领域适用",
                          ["antitrust", "competition_law"],
                          ["《反垄断法》（2022修订）", "《反不正当竞争法》", "市场监管总局公开处罚案例"],
                          "学习反垄断法核心概念：垄断协议、滥用市场支配地位、经营者集中审查。重点关注互联网平台领域的反垄断执法案例和合规要点。"),
                _make_obj("LEG-M03", "争议解决机制（诉讼 vs 仲裁 vs 调解）",
                          "掌握不同争议解决方式的适用场景和程序要求",
                          ["dispute_resolution", "litigation", "arbitration"],
                          ["《民事诉讼法》", "《仲裁法》", "中国国际经济贸易仲裁委员会规则"],
                          "对比学习三种争议解决方式：法院诉讼（管辖、流程、上诉）、商事仲裁（仲裁协议、机构选择、裁决执行）、调解（人民调解、商事调解）。"),
                _make_obj("LEG-M04", "行业特定合规（科技/金融/医疗任选一）",
                          "深入学习一个行业的监管框架",
                          ["industry_regulation", "compliance"],
                          ["相关行业监管法规", "行业协会合规指引"],
                          "请选择科技、金融或医疗行业之一，深入学习其特定监管要求：牌照/资质、核心合规义务、常见处罚案例、合规体系建设要点。"),
                _make_obj("LEG-M05", "国际贸易法基础",
                          "掌握国际贸易术语、信用证、国际货物买卖公约",
                          ["international_trade", "incoterms"],
                          ["CISG（联合国国际货物销售合同公约）", "Incoterms 2020", "WTO 争端解决案例"],
                          "学习国际贸易法核心内容：Incoterms 2020 常用术语（FOB/CIF/EXW）、CISG 适用范围和核心条款、信用证 UCP600 基础。"),
            ],
        ),
        GrowthStage(
            stage_id="senior", name="高级法务经理", level_range=(6, 8),
            description="跨境法律事务、复杂交易结构、法律风险管理体系",
            min_completed_objectives=3, min_total_tasks=60,
            objectives=[
                _make_obj("LEG-S01", "跨境并购与投资法律架构",
                          "学习跨境交易的法律架构设计和审批流程",
                          ["m_and_a", "cross_border", "foreign_investment"],
                          ["《外商投资法》", "商务部外资安全审查办法", "常见跨境并购案例分析"],
                          "学习跨境并购核心法律问题：交易结构（资产收购vs股权收购vs合并）、外资安全审查、反垄断申报、税务架构规划、跨境资金安排。", sessions=2),
                _make_obj("LEG-S02", "企业合规体系建设",
                          "设计和实施完整的企业合规管理体系",
                          ["compliance_management", "risk_management"],
                          ["ISO 37301 合规管理体系标准", "美国 DOJ 合规指引", "中国企业合规管理体系建设指南"],
                          "学习企业合规体系的全面建设：合规政策制度、风险评估方法论、合规培训体系、举报机制、合规审计、整改与持续改进。", sessions=2),
                _make_obj("LEG-S03", "知识产权战略与布局",
                          "从战略层面规划企业知识产权组合",
                          ["ip_strategy", "patent_portfolio"],
                          ["企业知识产权管理规范（GB/T 29490）", "全球主要专利局公开数据库"],
                          "学习知识产权战略规划：专利布局策略（核心专利+外围专利）、商标全球注册策略、开源软件合规、技术秘密保护体系、IP尽调方法。"),
                _make_obj("LEG-S04", "美国/欧盟出口管制与制裁合规",
                          "掌握国际出口管制和经济制裁的核心规则",
                          ["export_control", "sanctions", "us_law", "eu_law"],
                          ["美国 EAR/ITAR 法规", "EU 出口管制条例", "OFAC 制裁名单", "中国《出口管制法》"],
                          "对比学习中美欧出口管制体系：管控物项范围、最终用户/用途审查、制裁名单筛查（SDN/Entity List）、合规筛查流程建设。", sessions=2),
            ],
        ),
        GrowthStage(
            stage_id="expert", name="首席法务官/法律专家", level_range=(8, 10),
            description="法律战略制定、复杂争议管理、行业影响力建设",
            min_completed_objectives=2, min_total_tasks=100,
            objectives=[
                _make_obj("LEG-E01", "AI 与新兴技术法律问题",
                          "前沿法律问题：AI 监管、自动驾驶责任、区块链法律地位",
                          ["ai_law", "emerging_tech", "regulatory_sandbox"],
                          ["EU AI Act", "中国《生成式人工智能服务管理暂行办法》", "各国 AI 监管动态"],
                          "研究 AI 法律前沿：EU AI Act 风险分级制度、中国生成式 AI 法规、AI 生成内容的知识产权归属、自动决策的法律责任、监管沙盒机制。", sessions=2),
                _make_obj("LEG-E02", "ESG 合规与可持续发展法律框架",
                          "环境、社会和治理（ESG）领域的法律合规要求",
                          ["esg", "sustainability", "corporate_governance"],
                          ["EU CSRD/SFDR", "中国 ESG 信息披露指引", "ISSB 准则"],
                          "学习 ESG 法律框架：EU 可持续金融分类法、企业可持续发展报告指令（CSRD）、气候相关财务信息披露、供应链尽职调查法律义务。"),
            ],
        ),
    ],
))


# ============================================================
# 开发 (Coder)
# ============================================================
_register(RoleGrowthPath(
    role="coder", role_name="开发工程师",
    description="从基础编码能力到架构级工程能力的成长路径",
    stages=[
        GrowthStage(
            stage_id="junior", name="初级开发", level_range=(1, 3),
            description="扎实的编码基础和工程规范",
            min_completed_objectives=4, min_total_tasks=15,
            objectives=[
                _make_obj("DEV-J01", "代码规范与最佳实践",
                          "学习主流语言的编码规范和代码质量标准",
                          ["code_quality", "conventions"],
                          ["Google Style Guide", "PEP 8 (Python)", "Airbnb JS Style Guide"],
                          "学习并总结代码规范核心原则：命名规范、函数长度控制、注释规范、错误处理模式、代码复用原则。"),
                _make_obj("DEV-J02", "Git 工作流与版本管理",
                          "掌握 Git 分支策略和协作流程",
                          ["git", "version_control"],
                          ["Pro Git 官方文档", "Git Flow / GitHub Flow / Trunk-Based Development"],
                          "学习 Git 工作流：分支策略选择、commit message 规范、code review 流程、merge 策略、冲突解决。"),
                _make_obj("DEV-J03", "单元测试与 TDD",
                          "掌握测试驱动开发方法论和测试策略",
                          ["testing", "tdd", "quality"],
                          ["pytest / Jest 官方文档", "《Test-Driven Development》Kent Beck"],
                          "学习测试策略：单元测试编写方法、Mock/Stub 技术、测试覆盖率目标、TDD 红绿重构循环、集成测试基础。"),
                _make_obj("DEV-J04", "数据结构与算法基础",
                          "常用数据结构和算法复杂度分析",
                          ["algorithms", "data_structures"],
                          ["算法导论（CLRS）", "LeetCode 分类题解"],
                          "复习核心数据结构（数组、链表、树、哈希表、图）和常用算法（排序、搜索、递归、动态规划），总结时间/空间复杂度分析方法。"),
                _make_obj("DEV-J05", "调试与问题排查方法",
                          "系统化的调试方法论",
                          ["debugging", "troubleshooting"],
                          ["各语言调试器文档", "日志分析方法"],
                          "学习系统化调试方法：日志分级策略、断点调试技巧、二分法定位、性能 profiling、错误追踪(stack trace)分析。"),
            ],
        ),
        GrowthStage(
            stage_id="mid", name="中级开发", level_range=(3, 6),
            description="系统设计能力和工程效率提升",
            min_completed_objectives=4, min_total_tasks=40,
            objectives=[
                _make_obj("DEV-M01", "设计模式与架构原则",
                          "GoF 设计模式 + SOLID/DRY/KISS 原则",
                          ["design_patterns", "architecture"],
                          ["《设计模式》GoF", "《Clean Architecture》Robert Martin"],
                          "学习常用设计模式（策略、观察者、工厂、装饰器、适配器）及 SOLID 原则，总结每种模式的适用场景和实现要点。"),
                _make_obj("DEV-M02", "API 设计与 RESTful 规范",
                          "设计一致性好、可维护的 API",
                          ["api_design", "rest", "graphql"],
                          ["REST API 设计指南（Microsoft/Google）", "OpenAPI 规范", "GraphQL 官方文档"],
                          "学习 API 设计最佳实践：RESTful 资源命名、HTTP 方法语义、状态码使用、版本管理、分页/过滤/排序、错误响应格式、认证方案（OAuth2/JWT）。"),
                _make_obj("DEV-M03", "数据库设计与优化",
                          "关系型和非关系型数据库的设计与优化",
                          ["database", "sql", "nosql"],
                          ["《数据库系统概念》", "PostgreSQL/MySQL 官方文档", "Redis/MongoDB 文档"],
                          "学习数据库设计：范式理论、索引策略、查询优化(EXPLAIN)、分库分表、缓存策略、事务隔离级别、数据库选型（SQL vs NoSQL）。"),
                _make_obj("DEV-M04", "CI/CD 与 DevOps 基础",
                          "持续集成/部署流水线搭建",
                          ["cicd", "devops", "automation"],
                          ["GitHub Actions 文档", "Docker 官方文档", "Jenkins/GitLab CI"],
                          "学习 CI/CD 流水线：自动化测试集成、Docker 容器化、镜像构建策略、部署策略（蓝绿/金丝雀/滚动）、环境管理。"),
                _make_obj("DEV-M05", "安全编码实践",
                          "常见安全漏洞和防护措施",
                          ["security", "secure_coding"],
                          ["OWASP Top 10", "CWE/SANS Top 25", "各语言安全编码指南"],
                          "学习安全编码：OWASP Top 10（注入、XSS、CSRF、SSRF）、输入验证、密码存储、安全的会话管理、API 安全、依赖安全。"),
            ],
        ),
        GrowthStage(
            stage_id="senior", name="高级开发 / 技术负责人", level_range=(6, 8),
            description="系统架构设计和技术决策能力",
            min_completed_objectives=3, min_total_tasks=80,
            objectives=[
                _make_obj("DEV-S01", "分布式系统设计",
                          "CAP 理论、一致性模型、分布式架构模式",
                          ["distributed_systems", "architecture"],
                          ["《Designing Data-Intensive Applications》Martin Kleppmann", "分布式系统论文（Raft/Paxos/CRDT）"],
                          "学习分布式系统核心概念：CAP/BASE 理论、一致性模型、共识算法、分布式事务(2PC/Saga)、消息队列模式、服务发现、负载均衡。", sessions=2),
                _make_obj("DEV-S02", "性能优化方法论",
                          "系统级性能分析和优化策略",
                          ["performance", "optimization"],
                          ["《Systems Performance》Brendan Gregg", "各语言 profiling 工具文档"],
                          "学习性能优化方法：性能指标定义(P50/P99/吞吐量)、bottleneck 定位方法(flame graph/profiling)、缓存策略、异步处理、数据库优化、CDN/边缘计算。"),
                _make_obj("DEV-S03", "技术选型与架构决策",
                          "如何进行技术选型和架构 trade-off 分析",
                          ["tech_decision", "architecture"],
                          ["ADR (Architecture Decision Records) 模板", "ThoughtWorks 技术雷达"],
                          "学习技术决策方法论：架构决策记录(ADR)编写、技术选型评估矩阵、PoC验证方法、技术债务管理、迁移策略规划。"),
            ],
        ),
        GrowthStage(
            stage_id="expert", name="架构师 / 技术专家", level_range=(8, 10),
            description="行业级技术洞察力和技术战略制定",
            min_completed_objectives=2, min_total_tasks=120,
            objectives=[
                _make_obj("DEV-E01", "大规模系统架构案例研究",
                          "研究知名系统的架构演进和设计决策",
                          ["system_design", "case_study"],
                          ["各大公司技术博客（Netflix/Google/Meta/字节跳动）", "InfoQ 架构师系列"],
                          "研究2-3个大规模系统的架构案例：架构演进历程、关键设计决策、遇到的挑战和解决方案、可借鉴的模式。", sessions=2),
                _make_obj("DEV-E02", "AI/LLM 工程实践",
                          "将 AI/LLM 集成到软件系统的工程实践",
                          ["ai_engineering", "llm", "mlops"],
                          ["LangChain/LlamaIndex 文档", "Anthropic/OpenAI API 指南", "MLOps 最佳实践"],
                          "学习 AI 工程实践：LLM 应用架构模式（RAG/Agent/Chain）、prompt engineering 方法论、模型评估、成本优化、安全与对齐、部署策略。", sessions=2),
            ],
        ),
    ],
))


# ============================================================
# 设计 (Designer)
# ============================================================
_register(RoleGrowthPath(
    role="designer", role_name="设计师",
    description="从视觉基础到体验战略的设计师成长路径",
    stages=[
        GrowthStage(
            stage_id="junior", name="初级设计师", level_range=(1, 3),
            description="视觉基础和设计工具熟练使用",
            min_completed_objectives=3, min_total_tasks=10,
            objectives=[
                _make_obj("DES-J01", "设计基础原则",
                          "学习视觉设计四大原则和色彩理论",
                          ["visual_design", "color_theory"],
                          ["《写给大家看的设计书》Robin Williams", "Material Design 3 指南", "Apple HIG"],
                          "学习设计基础：对齐、对比、重复、亲密性四大原则；色彩理论（色轮、配色方案、无障碍色彩对比度）；排版基础（字体选择、层次、行距）。"),
                _make_obj("DES-J02", "组件化设计与设计系统",
                          "理解设计系统的构建方法",
                          ["design_system", "components"],
                          ["Material Design 组件库", "Ant Design 设计语言", "Atomic Design 方法论"],
                          "学习设计系统：原子设计方法论、组件拆分原则、Token 系统（色彩/间距/圆角）、组件文档编写、设计与开发交接规范。"),
                _make_obj("DES-J03", "用户体验基础与可用性原则",
                          "学习 UX 设计的基本原则和评估方法",
                          ["ux_design", "usability"],
                          ["《Don't Make Me Think》Steve Krug", "Nielsen Norman Group 文章", "WCAG 无障碍指南"],
                          "学习 UX 基础：Nielsen 十大可用性原则、信息架构、用户旅程图、交互模式（导航/表单/反馈）、无障碍设计（WCAG AA标准）。"),
            ],
        ),
        GrowthStage(
            stage_id="mid", name="中级设计师", level_range=(3, 6),
            description="用户研究和交互设计深度能力",
            min_completed_objectives=3, min_total_tasks=30,
            objectives=[
                _make_obj("DES-M01", "用户研究方法论",
                          "定性与定量研究方法",
                          ["user_research", "methodology"],
                          ["《用户体验度量》", "NNGroup 研究方法指南"],
                          "学习用户研究方法：用户访谈技巧、可用性测试设计、问卷设计、A/B测试、数据分析（转化漏斗/热力图）、研究报告撰写。"),
                _make_obj("DES-M02", "交互设计模式与微交互",
                          "复杂交互场景的设计方法",
                          ["interaction_design", "microinteraction"],
                          ["《Microinteractions》Dan Saffer", "Lottie 动画库", "Principle/Framer 文档"],
                          "学习高级交互设计：手势交互设计、动效原则（Disney 12 Principles）、状态转换、错误处理交互、加载策略（骨架屏/乐观更新）。"),
                _make_obj("DES-M03", "数据可视化设计",
                          "将复杂数据转化为清晰可理解的视觉表达",
                          ["data_visualization", "chart_design"],
                          ["《The Visual Display of Quantitative Information》Edward Tufte", "D3.js Gallery", "Observable HQ"],
                          "学习数据可视化：图表选择指南（何时用柱/线/饼/散点）、仪表盘设计原则、数据故事讲述、色彩映射、交互式可视化。"),
            ],
        ),
        GrowthStage(
            stage_id="senior", name="高级设计师 / 设计负责人", level_range=(6, 8),
            description="设计战略与团队领导力",
            min_completed_objectives=2, min_total_tasks=50,
            objectives=[
                _make_obj("DES-S01", "设计战略与商业价值",
                          "将设计与商业目标对齐的方法",
                          ["design_strategy", "business_value"],
                          ["《设计冲刺》Jake Knapp", "《商业模式画布》"],
                          "学习设计战略：Design Sprint 方法、OKR 驱动的设计决策、ROI 量化（转化率/留存率）、竞品分析框架、设计提案撰写。"),
                _make_obj("DES-S02", "AI 辅助设计与生成式设计",
                          "利用 AI 工具提升设计效率和创新",
                          ["ai_design", "generative_design"],
                          ["Midjourney/Stable Diffusion 指南", "Figma AI 功能", "设计领域 AI 应用案例"],
                          "探索 AI 辅助设计：AI 生成图像/图标的使用规范、AI 辅助布局和配色、AI 用户研究（情感分析）、AI 设计工具工作流。"),
            ],
        ),
    ],
))


# ============================================================
# 产品经理 (PM)
# ============================================================
_register(RoleGrowthPath(
    role="pm", role_name="产品经理",
    description="从需求分析到产品战略的成长路径",
    stages=[
        GrowthStage(
            stage_id="junior", name="初级产品经理", level_range=(1, 3),
            description="需求分析和产品文档编写能力",
            min_completed_objectives=3, min_total_tasks=10,
            objectives=[
                _make_obj("PM-J01", "需求分析方法论",
                          "用户故事、用例分析、需求优先级排序",
                          ["requirements", "user_story"],
                          ["《用户故事地图》Jeff Patton", "INVEST 原则", "MoSCoW 方法"],
                          "学习需求分析：用户故事编写（As a...I want...So that...）、验收标准定义、用户故事地图、需求优先级排序（RICE/MoSCoW/Kano模型）。"),
                _make_obj("PM-J02", "PRD 与产品文档编写",
                          "规范的产品需求文档编写方法",
                          ["prd", "documentation"],
                          ["主流互联网公司 PRD 模板", "Confluence/Notion 文档最佳实践"],
                          "学习 PRD 编写规范：背景与目标、用户场景、功能需求（列表+流程图）、非功能需求（性能/安全/兼容性）、数据指标定义、里程碑规划。"),
                _make_obj("PM-J03", "竞品分析与市场研究",
                          "系统化的竞品分析方法",
                          ["competitive_analysis", "market_research"],
                          ["SimilarWeb/App Annie 数据", "行业报告（艾瑞/QuestMobile）"],
                          "学习竞品分析方法：竞品识别与分类、功能对比矩阵、差异化分析、SWOT 分析、用户评价挖掘、市场趋势研判。"),
            ],
        ),
        GrowthStage(
            stage_id="mid", name="中级产品经理", level_range=(3, 6),
            description="数据驱动决策和增长能力",
            min_completed_objectives=3, min_total_tasks=30,
            objectives=[
                _make_obj("PM-M01", "数据驱动产品决策",
                          "产品数据分析和 A/B 测试方法",
                          ["data_driven", "analytics", "ab_testing"],
                          ["Google Analytics/Mixpanel 文档", "《精益数据分析》"],
                          "学习数据驱动方法：核心指标体系搭建（北极星指标/AARRR）、埋点方案设计、A/B测试设计与统计显著性判断、数据分析报告。"),
                _make_obj("PM-M02", "用户增长策略",
                          "产品增长模型和增长实验方法",
                          ["growth", "user_acquisition", "retention"],
                          ["《增长黑客》Sean Ellis", "Reforge Growth 框架"],
                          "学习增长方法论：增长模型构建、获客渠道分析、激活优化、留存策略（Hook模型）、推荐系统、增长实验设计。"),
                _make_obj("PM-M03", "商业模式设计",
                          "商业模式画布和盈利模型设计",
                          ["business_model", "monetization"],
                          ["《商业模式新生代》", "各类 SaaS/平台/广告模式案例"],
                          "学习商业模式：商业模式画布九要素、定价策略（免费增值/订阅/交易费）、成本结构分析、单位经济模型（LTV/CAC）。"),
            ],
        ),
        GrowthStage(
            stage_id="senior", name="高级产品经理 / 产品总监", level_range=(6, 10),
            description="产品战略制定和组织能力",
            min_completed_objectives=2, min_total_tasks=60,
            objectives=[
                _make_obj("PM-S01", "产品战略与路线图",
                          "长期产品战略制定和路线图规划",
                          ["product_strategy", "roadmap"],
                          ["《启示录》Marty Cagan", "《产品领导力》"],
                          "学习产品战略：愿景定义、战略拆解、路线图类型（时间轴/主题/目标型）、OKR 对齐、利益相关者管理、战略沟通。"),
                _make_obj("PM-S02", "AI 产品设计方法论",
                          "AI/LLM 产品的特殊设计考量",
                          ["ai_product", "llm_product"],
                          ["Google PAIR Guidebook", "Anthropic 产品设计指南", "AI 产品案例分析"],
                          "学习 AI 产品设计：AI 能力边界评估、人机交互模式（co-pilot/autopilot）、置信度展示、错误处理、伦理考量、用户信任建设。"),
            ],
        ),
    ],
))


# ============================================================
# 数据分析 (Data)
# ============================================================
_register(RoleGrowthPath(
    role="data", role_name="数据工程师/分析师",
    description="从数据分析基础到数据架构的成长路径",
    stages=[
        GrowthStage(
            stage_id="junior", name="初级数据分析", level_range=(1, 3),
            description="SQL、Python 数据分析和可视化基础",
            min_completed_objectives=3, min_total_tasks=10,
            objectives=[
                _make_obj("DAT-J01", "SQL 高级查询与优化",
                          "窗口函数、CTE、查询计划分析",
                          ["sql", "query_optimization"],
                          ["PostgreSQL/MySQL 官方文档", "《SQL 进阶教程》"],
                          "学习 SQL 高级技巧：窗口函数（ROW_NUMBER/RANK/LAG/LEAD）、CTE 递归查询、子查询优化、索引策略、EXPLAIN 分析。"),
                _make_obj("DAT-J02", "Python 数据分析栈",
                          "pandas/numpy/matplotlib 核心使用",
                          ["python", "pandas", "data_analysis"],
                          ["pandas 官方文档", "《利用 Python 进行数据分析》Wes McKinney"],
                          "学习 Python 数据分析：pandas DataFrame 操作（groupby/merge/pivot）、数据清洗方法、numpy 数组运算、matplotlib/seaborn 可视化。"),
                _make_obj("DAT-J03", "统计学基础",
                          "描述统计、假设检验、概率分布",
                          ["statistics", "probability"],
                          ["《统计学》David Freedman", "Khan Academy 统计课"],
                          "学习统计学核心：描述统计（均值/中位数/标准差/分位数）、概率分布（正态/二项/泊松）、假设检验（t检验/卡方检验）、相关与回归。"),
            ],
        ),
        GrowthStage(
            stage_id="mid", name="中级数据工程师", level_range=(3, 6),
            description="数据管道、ETL 和大数据技术",
            min_completed_objectives=3, min_total_tasks=30,
            objectives=[
                _make_obj("DAT-M01", "ETL 管道设计",
                          "数据管道架构和常见工具使用",
                          ["etl", "data_pipeline"],
                          ["Apache Airflow 文档", "dbt 文档", "数据仓库设计方法论"],
                          "学习 ETL 设计：数据管道架构模式、Airflow DAG 编写、dbt 数据转换、数据质量检测、幂等性设计、错误处理与重试。"),
                _make_obj("DAT-M02", "数据仓库建模",
                          "维度建模和数据仓库分层架构",
                          ["data_warehouse", "dimensional_modeling"],
                          ["《维度建模》Ralph Kimball", "数据仓库分层（ODS/DWD/DWS/ADS）"],
                          "学习数据仓库：星型/雪花模型、维度表与事实表设计、缓慢变化维、数据仓库分层架构、数据集市、数据治理。"),
                _make_obj("DAT-M03", "机器学习基础",
                          "监督/非监督学习算法和评估方法",
                          ["machine_learning", "modeling"],
                          ["scikit-learn 文档", "《统计学习方法》李航", "Kaggle 竞赛入门"],
                          "学习 ML 基础：分类算法（逻辑回归/决策树/随机森林/XGBoost）、聚类（KMeans）、评估指标（AUC/F1/RMSE）、交叉验证、特征工程。"),
            ],
        ),
    ],
))


# ============================================================
# DevOps / 运维
# ============================================================
_register(RoleGrowthPath(
    role="devops", role_name="DevOps 工程师",
    description="从运维基础到 SRE 和平台工程的成长路径",
    stages=[
        GrowthStage(
            stage_id="junior", name="初级运维", level_range=(1, 3),
            description="Linux 系统管理和基础运维技能",
            min_completed_objectives=3, min_total_tasks=10,
            objectives=[
                _make_obj("OPS-J01", "Linux 系统管理",
                          "Linux 命令行、文件系统、进程管理、网络配置",
                          ["linux", "sysadmin"],
                          ["《鸟哥的 Linux 私房菜》", "Linux man pages"],
                          "学习 Linux 核心：文件权限、进程管理(ps/top/kill)、网络诊断(netstat/ss/tcpdump)、磁盘管理(df/du/fdisk)、systemd 服务管理。"),
                _make_obj("OPS-J02", "Docker 容器化",
                          "Docker 镜像构建和容器编排基础",
                          ["docker", "containerization"],
                          ["Docker 官方文档", "Dockerfile 最佳实践"],
                          "学习 Docker：Dockerfile 编写（多阶段构建、层缓存优化）、docker-compose 编排、网络模式、数据持久化、安全最佳实践。"),
                _make_obj("OPS-J03", "监控与告警基础",
                          "系统监控、日志采集和告警配置",
                          ["monitoring", "logging", "alerting"],
                          ["Prometheus + Grafana 文档", "ELK Stack 文档"],
                          "学习监控体系：Prometheus 指标采集与 PromQL、Grafana 仪表盘、日志采集(Filebeat/Fluentd)、告警规则设计、SLI/SLO 定义。"),
            ],
        ),
        GrowthStage(
            stage_id="mid", name="中级 DevOps / SRE", level_range=(3, 6),
            description="Kubernetes、IaC 和可靠性工程",
            min_completed_objectives=3, min_total_tasks=30,
            objectives=[
                _make_obj("OPS-M01", "Kubernetes 运维",
                          "K8s 集群管理、Deployment、Service、HPA",
                          ["kubernetes", "orchestration"],
                          ["Kubernetes 官方文档", "《Kubernetes in Action》"],
                          "学习 K8s：Pod 生命周期、Deployment 策略、Service 类型、Ingress 配置、HPA/VPA 自动伸缩、ConfigMap/Secret 管理、RBAC。", sessions=2),
                _make_obj("OPS-M02", "基础设施即代码 (IaC)",
                          "Terraform/Ansible 基础设施自动化",
                          ["iac", "terraform", "ansible"],
                          ["Terraform 官方文档", "Ansible 文档"],
                          "学习 IaC：Terraform 资源定义与状态管理、模块化设计、Ansible Playbook 编写、GitOps 工作流、基础设施变更审计。"),
                _make_obj("OPS-M03", "故障响应与 SRE 实践",
                          "故障处理流程和可靠性工程方法论",
                          ["sre", "incident_management"],
                          ["Google SRE Book", "《SRE: 可靠性工程实践》"],
                          "学习 SRE 实践：SLI/SLO/SLA 定义、Error Budget 管理、故障响应流程（On-Call/Incident Commander）、Post-Mortem 编写、混沌工程基础。"),
            ],
        ),
    ],
))


# ============================================================
# CEO / 管理者
# ============================================================
_register(RoleGrowthPath(
    role="ceo", role_name="CEO / 管理者",
    description="企业管理者的战略决策和领导力成长路径",
    stages=[
        GrowthStage(
            stage_id="junior", name="初级管理者", level_range=(1, 3),
            description="管理基础和团队建设",
            min_completed_objectives=3, min_total_tasks=10,
            objectives=[
                _make_obj("CEO-J01", "管理学基础框架",
                          "PDCA、OKR、SWOT 等管理工具",
                          ["management", "frameworks"],
                          ["《管理的实践》Peter Drucker", "OKR 工作法", "SWOT/PEST 分析"],
                          "学习管理基础框架：PDCA 循环、OKR 设定与跟踪方法、SWOT 分析、PEST 宏观环境分析、5W2H 问题分析法。"),
                _make_obj("CEO-J02", "团队管理与沟通",
                          "团队建设、绩效管理、冲突解决",
                          ["team_management", "communication"],
                          ["《高效能人士的七个习惯》", "《非暴力沟通》"],
                          "学习团队管理：团队发展阶段(Tuckman 模型)、1-on-1 沟通技巧、绩效反馈方法(SBI模型)、委派与授权、冲突解决策略。"),
                _make_obj("CEO-J03", "财务报表阅读",
                          "理解三大财务报表和关键财务指标",
                          ["finance", "accounting"],
                          ["《一本书读懂财报》", "CPA 基础教材"],
                          "学习财务基础：资产负债表、利润表、现金流量表的结构和关系；关键指标（ROE/ROA/毛利率/净利率/现金比率）；杜邦分析法。"),
            ],
        ),
        GrowthStage(
            stage_id="mid", name="中高级管理者", level_range=(3, 7),
            description="战略思维和商业洞察力",
            min_completed_objectives=3, min_total_tasks=30,
            objectives=[
                _make_obj("CEO-M01", "竞争战略",
                          "波特五力、蓝海战略、平台经济理论",
                          ["strategy", "competition"],
                          ["《竞争战略》Michael Porter", "《蓝海战略》", "《平台革命》"],
                          "学习竞争战略：波特五力模型、三大通用战略（成本领先/差异化/集中化）、蓝海战略方法论、平台经济双边网络效应。"),
                _make_obj("CEO-M02", "融资与资本运作基础",
                          "股权融资、风险投资、估值方法",
                          ["fundraising", "valuation", "capital"],
                          ["《风险投资交易》Brad Feld", "估值方法论（DCF/可比公司/交易先例）"],
                          "学习资本运作：融资轮次与阶段、Term Sheet 关键条款、估值方法（DCF/市盈率/可比交易）、股权结构设计、反稀释条款。"),
                _make_obj("CEO-M03", "数字化转型战略",
                          "企业数字化转型路径和 AI 赋能策略",
                          ["digital_transformation", "ai_strategy"],
                          ["McKinsey Digital 报告", "《AI 超级力量》李开复"],
                          "学习数字化转型：数字化成熟度评估模型、AI 应用场景识别、数据战略规划、组织能力建设、变革管理方法。"),
            ],
        ),
    ],
))


# ============================================================
# CTO / 技术管理
# ============================================================
_register(RoleGrowthPath(
    role="cto", role_name="CTO / 技术管理者",
    description="技术管理者的工程管理和技术战略成长路径",
    stages=[
        GrowthStage(
            stage_id="junior", name="技术主管", level_range=(1, 3),
            description="技术团队管理和工程流程",
            min_completed_objectives=3, min_total_tasks=10,
            objectives=[
                _make_obj("CTO-J01", "工程管理方法论",
                          "敏捷开发、Scrum、看板方法",
                          ["agile", "scrum", "engineering_management"],
                          ["《敏捷软件开发》Robert Martin", "Scrum Guide 官方", "Atlassian Agile 指南"],
                          "学习工程管理：Scrum 框架（Sprint/Daily/Retro）、看板方法与 WIP 限制、敏捷估算(Story Points)、Sprint 规划、Velocity 追踪。"),
                _make_obj("CTO-J02", "技术招聘与团队建设",
                          "技术面试设计、人才梯度建设",
                          ["hiring", "team_building"],
                          ["《谁》Geoff Smart", "系统设计面试指南"],
                          "学习技术招聘：JD 编写、技术面试设计（算法/系统设计/行为面试）、面试评估标准、人才梯度规划（T/P 序列）、技术培训体系。"),
                _make_obj("CTO-J03", "技术债务管理",
                          "识别、量化和偿还技术债务",
                          ["tech_debt", "code_quality"],
                          ["Martin Fowler 技术债务文章", "SonarQube/CodeClimate 文档"],
                          "学习技术债务管理：技术债务分类（设计/代码/测试/文档）、量化方法、偿债优先级排序、20%技术改进时间的实施、架构演进路线图。"),
            ],
        ),
        GrowthStage(
            stage_id="mid", name="技术总监 / VP", level_range=(3, 7),
            description="技术战略和组织架构设计",
            min_completed_objectives=2, min_total_tasks=30,
            objectives=[
                _make_obj("CTO-M01", "技术战略规划",
                          "长期技术路线图和技术投资决策",
                          ["tech_strategy", "roadmap"],
                          ["ThoughtWorks 技术雷达", "Gartner Hype Cycle", "《CTO 之路》"],
                          "学习技术战略：技术雷达编制、Build vs Buy 决策框架、技术投资 ROI 评估、平台战略、技术标准化与创新平衡。"),
                _make_obj("CTO-M02", "安全与合规架构",
                          "信息安全管理体系和合规要求",
                          ["security", "compliance", "iso27001"],
                          ["ISO 27001 标准", "SOC 2 合规指南", "NIST 网络安全框架"],
                          "学习安全架构：ISO 27001 管理体系、SOC 2 审计要求、安全开发生命周期(SDL)、渗透测试管理、安全应急响应、数据分类与保护。"),
            ],
        ),
    ],
))


# ============================================================
# 测试 (Tester)
# ============================================================
_register(RoleGrowthPath(
    role="tester", role_name="测试工程师",
    description="从手工测试到自动化测试和质量工程的成长路径",
    stages=[
        GrowthStage(
            stage_id="junior", name="初级测试", level_range=(1, 3),
            description="测试基础和用例设计方法",
            min_completed_objectives=3, min_total_tasks=10,
            objectives=[
                _make_obj("TST-J01", "测试设计方法",
                          "等价类、边界值、场景法、判定表",
                          ["test_design", "test_cases"],
                          ["ISTQB 基础级教材", "《软件测试的艺术》"],
                          "学习测试设计方法：等价类划分、边界值分析、判定表、状态转换测试、场景法、错误推测法。理解黑盒/白盒/灰盒测试区别。"),
                _make_obj("TST-J02", "自动化测试入门",
                          "Selenium/Playwright/pytest 自动化框架",
                          ["automation", "selenium", "pytest"],
                          ["Playwright 官方文档", "pytest 文档", "Selenium 文档"],
                          "学习自动化测试：测试框架选择、Page Object 模式、测试数据管理、断言设计、CI 集成、测试报告生成。"),
                _make_obj("TST-J03", "缺陷管理与测试报告",
                          "缺陷生命周期管理和测试报告编写",
                          ["bug_tracking", "reporting"],
                          ["Jira/Linear 缺陷管理", "测试报告模板"],
                          "学习缺陷管理：缺陷报告编写（标题/重现步骤/预期vs实际/严重等级）、缺陷生命周期、测试进度报告、覆盖率报告、风险评估。"),
            ],
        ),
        GrowthStage(
            stage_id="mid", name="中级质量工程师", level_range=(3, 6),
            description="性能测试、安全测试、质量体系",
            min_completed_objectives=2, min_total_tasks=30,
            objectives=[
                _make_obj("TST-M01", "性能测试",
                          "负载测试、压力测试、性能调优",
                          ["performance_testing", "load_testing"],
                          ["JMeter/k6/Locust 文档", "性能测试方法论"],
                          "学习性能测试：测试场景设计（基准/负载/压力/浸泡测试）、JMeter/k6 脚本编写、性能指标（TPS/响应时间/错误率）、瓶颈定位、调优建议。"),
                _make_obj("TST-M02", "API 测试与契约测试",
                          "REST API 测试策略和消费者驱动契约",
                          ["api_testing", "contract_testing"],
                          ["Postman/Newman 文档", "Pact 契约测试", "OpenAPI 规范"],
                          "学习 API 测试：REST API 测试策略、Postman Collection 编写、契约测试(Pact)、Mock Server、GraphQL 测试。"),
            ],
        ),
    ],
))


# ============================================================
# 研究员 (Researcher)
# ============================================================
_register(RoleGrowthPath(
    role="researcher", role_name="研究员",
    description="从信息检索到深度研究的成长路径",
    stages=[
        GrowthStage(
            stage_id="junior", name="初级研究助理", level_range=(1, 3),
            description="信息检索和研究方法基础",
            min_completed_objectives=3, min_total_tasks=10,
            objectives=[
                _make_obj("RES-J01", "信息检索与文献综述",
                          "学术搜索、文献管理、综述写作方法",
                          ["literature_review", "search"],
                          ["Google Scholar 使用技巧", "Zotero/Mendeley 文献管理"],
                          "学习研究方法：学术数据库使用（Google Scholar/CNKI/Web of Science）、关键词策略、文献筛选标准、文献综述写作结构、引用管理。"),
                _make_obj("RES-J02", "数据收集与验证",
                          "数据源评估、事实核查方法",
                          ["data_collection", "fact_checking"],
                          ["数据新闻学方法论", "事实核查工具指南"],
                          "学习数据收集：一手vs二手数据、数据源可信度评估、交叉验证方法、偏差识别、样本量考量、数据清洗方法。"),
                _make_obj("RES-J03", "研究报告写作",
                          "结构化研究报告的写作规范",
                          ["report_writing", "academic_writing"],
                          ["APA/Chicago 格式指南", "《学术写作指南》"],
                          "学习研究写作：摘要写作、引言结构、方法论描述、结果呈现、讨论与结论、参考文献格式。"),
            ],
        ),
        GrowthStage(
            stage_id="mid", name="中级研究员", level_range=(3, 7),
            description="独立研究能力和方法论深度",
            min_completed_objectives=2, min_total_tasks=30,
            objectives=[
                _make_obj("RES-M01", "研究方法论",
                          "定性与定量研究方法、混合方法",
                          ["methodology", "qualitative", "quantitative"],
                          ["《研究方法导论》", "统计分析软件教程（R/SPSS/Python）"],
                          "学习研究方法论：定性方法（扎根理论/案例研究/内容分析）、定量方法（实验设计/调查研究/统计分析）、混合方法设计。"),
                _make_obj("RES-M02", "行业分析框架",
                          "产业研究和市场分析的系统方法",
                          ["industry_analysis", "market_research"],
                          ["波特五力分析", "BCG矩阵", "行业报告撰写指南"],
                          "学习行业分析：宏观环境分析(PEST)、行业结构分析(Porter)、价值链分析、竞争格局映射、趋势预测方法、行业研究报告撰写。"),
            ],
        ),
    ],
))


# ============================================================
# 通用 (General) — 适用于未指定角色的 Agent
# ============================================================
_register(RoleGrowthPath(
    role="general", role_name="通用助手",
    description="通用能力提升路径，适用于各类辅助工作",
    stages=[
        GrowthStage(
            stage_id="junior", name="基础阶段", level_range=(1, 3),
            description="基础工作方法和效率工具",
            min_completed_objectives=3, min_total_tasks=10,
            objectives=[
                _make_obj("GEN-J01", "结构化思维方法",
                          "MECE、金字塔原理、问题拆解方法",
                          ["structured_thinking", "problem_solving"],
                          ["《金字塔原理》Barbara Minto", "《麦肯锡方法》"],
                          "学习结构化思维：MECE 原则、金字塔原理（结论先行/归纳分组/逻辑递进）、问题树分析、假设驱动方法。"),
                _make_obj("GEN-J02", "高效沟通与文档写作",
                          "清晰表达、邮件写作、文档规范",
                          ["communication", "writing"],
                          ["《非暴力沟通》", "商务写作指南"],
                          "学习沟通技巧：金字塔结构表达法、STAR 方法讲故事、邮件写作规范（主题/正文/行动项）、会议纪要撰写、技术文档模板。"),
                _make_obj("GEN-J03", "时间管理与任务规划",
                          "GTD、番茄工作法、优先级管理",
                          ["time_management", "productivity"],
                          ["《Getting Things Done》David Allen", "Eisenhower矩阵"],
                          "学习时间管理：GTD 五步法（收集/处理/组织/回顾/执行）、Eisenhower 矩阵（紧急/重要分类）、番茄工作法、Weekly Review 方法。"),
            ],
        ),
    ],
))


# ============================================================
# Reviewer (代码审查)
# ============================================================
_register(RoleGrowthPath(
    role="reviewer", role_name="代码审查专家",
    description="代码审查能力的系统化成长路径",
    stages=[
        GrowthStage(
            stage_id="junior", name="初级审查员", level_range=(1, 3),
            description="代码审查基础和常见问题识别",
            min_completed_objectives=3, min_total_tasks=10,
            objectives=[
                _make_obj("REV-J01", "代码审查方法论",
                          "审查清单、常见问题模式、反馈技巧",
                          ["code_review", "methodology"],
                          ["Google Code Review 指南", "《Code Review 最佳实践》"],
                          "学习代码审查：审查清单（正确性/可读性/安全性/性能/可维护性）、常见问题模式、建设性反馈的写法、审查速度与深度平衡。"),
                _make_obj("REV-J02", "安全漏洞识别",
                          "代码中常见安全问题的识别",
                          ["security_review", "vulnerability"],
                          ["OWASP Code Review Guide", "CWE Top 25"],
                          "学习安全审查：SQL注入/XSS/CSRF 识别、硬编码密钥检测、不安全的反序列化、路径遍历、权限控制缺失、加密误用。"),
                _make_obj("REV-J03", "性能问题识别",
                          "代码中常见性能反模式",
                          ["performance_review", "antipatterns"],
                          ["各语言性能反模式集", "数据库查询优化指南"],
                          "学习性能审查：N+1 查询问题、内存泄漏模式、不必要的对象创建、锁竞争、I/O 阻塞、缓存缺失、算法复杂度问题。"),
            ],
        ),
    ],
))


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def get_growth_path(role: str) -> RoleGrowthPath | None:
    """Get the growth path template for a role. Returns None if not defined."""
    return ROLE_GROWTH_PATHS.get(role)


def get_or_create_growth_path(role: str) -> RoleGrowthPath:
    """Get growth path for role, falling back to 'general' if not defined."""
    path = ROLE_GROWTH_PATHS.get(role)
    if path:
        # Return a deep copy so each agent gets their own instance
        return RoleGrowthPath.from_dict(path.to_dict())
    # Fallback to general
    general = ROLE_GROWTH_PATHS.get("general")
    if general:
        p = RoleGrowthPath.from_dict(general.to_dict())
        p.role = role
        return p
    # Minimal fallback
    return RoleGrowthPath(role=role, role_name=role)


def list_available_roles() -> list[dict]:
    """List all roles that have growth paths defined."""
    return [
        {"role": p.role, "role_name": p.role_name,
         "stages": len(p.stages),
         "total_objectives": sum(len(s.objectives) for s in p.stages),
         "description": p.description[:100]}
        for p in ROLE_GROWTH_PATHS.values()
    ]
