"""
SkillScout — Multi-agent skill discovery and evaluation system.

Discovers, evaluates, and generates recommendation reports for skills from
online sources (GitHub, skill registries). Does NOT install anything automatically —
all actions require explicit user approval.

Key responsibilities:
1. Search online sources (GitHub repos, registries) for relevant skills
2. Evaluate discovered skills on quality, security, and compatibility
3. Generate human-readable recommendation reports (markdown)
4. Prepare download/install instructions (no automatic installation)
5. Cache results and handle rate limits (GitHub API: 60 req/hr unauthenticated)

Architecture:
- SkillSource: online source configuration (GitHub repo, registry URL, etc.)
- DiscoveredSkill: skill metadata from online source
- SkillEvaluation: assessment of quality, security, compatibility
- SkillRecommendation: final report with ranked evaluations
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable, Any

logger = logging.getLogger("tudou.skill_scout")


# ─────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────

GITHUB_API_RATE_LIMIT = 60  # requests per hour (unauthenticated)
CACHE_TTL_SECONDS = 3600  # 1 hour
MIN_QUALITY_SCORE_FOR_RECOMMENDATION = 0.5


# ─────────────────────────────────────────────────────────────
# Data Models
# ─────────────────────────────────────────────────────────────

@dataclass
class SkillSource:
    """Configuration for an online skill source."""
    name: str              # Display name: "openclaw/skills", "agentskills.io"
    source_type: str       # "github_repo", "github_search", "registry", "url"
    url: str               # Base URL
    enabled: bool = True
    last_fetched: float = 0.0  # Unix timestamp of last fetch


@dataclass
class DiscoveredSkill:
    """Skill metadata discovered from online source."""
    name: str
    description: str
    source: str            # SkillSource.name
    url: str               # Direct URL to skill (GitHub, registry, etc.)
    author: str
    version: str
    runtime: str           # "python", "markdown", "shell"
    stars: int = 0         # GitHub stars (if from GitHub)
    downloads: int = 0     # Download count (if from registry)
    tags: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)  # MCP tool names
    license: str = ""
    last_updated: str = ""  # ISO 8601 date
    raw_metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Serialize to dict for JSON storage."""
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> DiscoveredSkill:
        """Deserialize from dict."""
        return DiscoveredSkill(**d)


@dataclass
class SkillEvaluation:
    """Assessment of a discovered skill."""
    skill: DiscoveredSkill
    relevance_score: float    # 0-1: how relevant to query/role
    quality_score: float      # 0-1: based on stars, maintenance, docs
    security_risk: str        # "low", "medium", "high"
    compatibility: str        # "compatible", "needs_deps", "incompatible"
    recommendation: str       # "recommended", "caution", "skip"
    reason: str               # Human-readable explanation
    security_notes: list[str] = field(default_factory=list)
    missing_deps: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Serialize to dict (excluding DiscoveredSkill which is separate)."""
        d = asdict(self)
        d["skill"] = self.skill.to_dict()
        return d


@dataclass
class SkillRecommendation:
    """Final recommendation report."""
    query: str                 # Original search query
    agent_role: str            # Agent role context
    evaluations: list[SkillEvaluation]
    generated_at: float        # Unix timestamp
    report_md: str             # Markdown report for user

    def to_dict(self) -> dict:
        """Serialize to dict for JSON storage."""
        return {
            "query": self.query,
            "agent_role": self.agent_role,
            "evaluations": [e.to_dict() for e in self.evaluations],
            "generated_at": self.generated_at,
            "report_md": self.report_md,
        }


# ─────────────────────────────────────────────────────────────
# SkillScout Main Class
# ─────────────────────────────────────────────────────────────

class SkillScout:
    """Discovers and evaluates skills from online sources."""

    DEFAULT_SOURCES = [
        SkillSource(
            name="openclaw/skills",
            source_type="github_repo",
            url="https://github.com/openclaw/skills"
        ),
        SkillSource(
            name="GitHub Agent Skills",
            source_type="github_search",
            url="https://api.github.com/search/repositories",
        ),
        SkillSource(
            name="agentskills.io",
            source_type="registry",
            url="https://api.agentskills.io/v1/search",
        ),
    ]

    def __init__(
        self,
        sources: Optional[list[SkillSource]] = None,
        cache_dir: str = "",
        llm_call_fn: Optional[Callable[[str], str]] = None,
        language: str = "en",
    ):
        """
        Initialize SkillScout.

        Args:
            sources: List of SkillSource configurations. If None, uses DEFAULT_SOURCES.
            cache_dir: Directory for caching fetched metadata. If empty, uses temp.
            llm_call_fn: Callable(prompt) -> str for LLM-based evaluation.
                         If provided, uses LLM for relevance scoring.
            language: Output language ("en" or "zh").
        """
        self.sources = sources or self.DEFAULT_SOURCES
        self.cache_dir = Path(cache_dir or "/tmp/tudou_skill_scout_cache")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.llm_call_fn = llm_call_fn
        self.language = language
        self._cache: dict[str, Any] = {}
        self._load_cache()

    def _load_cache(self) -> None:
        """Load cache from disk."""
        cache_file = self.cache_dir / "metadata_cache.json"
        if cache_file.exists():
            try:
                with open(cache_file, "r") as f:
                    self._cache = json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load cache: {e}")
                self._cache = {}

    def _save_cache(self) -> None:
        """Save cache to disk."""
        cache_file = self.cache_dir / "metadata_cache.json"
        try:
            with open(cache_file, "w") as f:
                json.dump(self._cache, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save cache: {e}")

    def _is_cache_fresh(self, key: str) -> bool:
        """Check if cache entry is fresh (within TTL)."""
        if key not in self._cache:
            return False
        entry = self._cache[key]
        if not isinstance(entry, dict) or "timestamp" not in entry:
            return False
        elapsed = time.time() - entry["timestamp"]
        return elapsed < CACHE_TTL_SECONDS

    def _fetch_json(self, url: str, headers: Optional[dict] = None) -> Optional[dict]:
        """
        Fetch JSON from URL with error handling.

        Returns None on error. Rate limit aware for GitHub API.
        """
        try:
            req = urllib.request.Request(url)
            if headers:
                for key, value in headers.items():
                    req.add_header(key, value)
            req.add_header("User-Agent", "TudouClaw-SkillScout/1.0")

            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode("utf-8"))
                return data
        except urllib.error.HTTPError as e:
            if e.code == 403:
                logger.warning("GitHub API rate limit exceeded")
            else:
                logger.warning(f"HTTP error {e.code}: {e.reason}")
            return None
        except Exception as e:
            logger.warning(f"Failed to fetch {url}: {e}")
            return None

    def search(
        self,
        query: str,
        agent_role: str = "",
        max_results: int = 20,
    ) -> list[DiscoveredSkill]:
        """
        Search online sources for skills matching query.

        Args:
            query: Search query (e.g., "web_scraper", "email", "database")
            agent_role: Optional agent role for context.
            max_results: Maximum number of results to return.

        Returns:
            List of DiscoveredSkill sorted by relevance.
        """
        skills: list[DiscoveredSkill] = []

        for source in self.sources:
            if not source.enabled:
                continue

            logger.info(f"Searching {source.name} for: {query}")

            if source.source_type == "github_repo":
                skills.extend(self._search_github_repo(source, query))
            elif source.source_type == "github_search":
                skills.extend(self._search_github_api(query))
            elif source.source_type == "registry":
                skills.extend(self._search_registry(source, query))

            if len(skills) >= max_results:
                break

        # Deduplicate by name
        seen = set()
        unique_skills = []
        for skill in skills:
            if skill.name not in seen:
                seen.add(skill.name)
                unique_skills.append(skill)

        return unique_skills[:max_results]

    def _search_github_repo(self, source: SkillSource, query: str) -> list[DiscoveredSkill]:
        """
        Search within a specific GitHub repo (e.g., openclaw/skills).

        Looks for directories with manifest.yaml or SKILL.md files.
        """
        skills: list[DiscoveredSkill] = []
        cache_key = f"github_repo:{source.url}:{query}"

        if self._is_cache_fresh(cache_key):
            try:
                return [
                    DiscoveredSkill.from_dict(d)
                    for d in self._cache[cache_key].get("skills", [])
                ]
            except Exception:
                pass

        # Extract owner/repo from URL
        match = re.search(r"github\.com/([^/]+)/([^/]+)", source.url)
        if not match:
            return []

        owner, repo = match.groups()
        api_url = f"https://api.github.com/repos/{owner}/{repo}/contents"

        # Fetch repository contents
        contents = self._fetch_json(api_url)
        if not contents or not isinstance(contents, list):
            return []

        for item in contents:
            if item.get("type") == "dir" and item.get("name") != ".github":
                # Check for manifest.yaml or SKILL.md
                skill_name = item["name"]
                if self._matches_query(skill_name, query):
                    skill = DiscoveredSkill(
                        name=skill_name,
                        description=f"Skill from {source.name}",
                        source=source.name,
                        url=item["html_url"],
                        author=owner,
                        version="unknown",
                        runtime="python",
                        tags=[source.name],
                    )
                    skills.append(skill)

        # Cache results
        self._cache[cache_key] = {
            "timestamp": time.time(),
            "skills": [s.to_dict() for s in skills],
        }
        self._save_cache()

        return skills

    def _search_github_api(self, query: str) -> list[DiscoveredSkill]:
        """
        Search GitHub API for repositories with agent-skill or mcp-skill topics.
        """
        skills: list[DiscoveredSkill] = []
        cache_key = f"github_search:{query}"

        if self._is_cache_fresh(cache_key):
            try:
                return [
                    DiscoveredSkill.from_dict(d)
                    for d in self._cache[cache_key].get("skills", [])
                ]
            except Exception:
                pass

        # Build search query with topic filters
        search_q = (
            f"topic:agent-skill OR topic:mcp-skill {query} "
            f"language:python sort:stars-desc"
        )
        api_url = (
            f"https://api.github.com/search/repositories?"
            f"q={urllib.parse.quote(search_q)}&per_page=10"
        )

        data = self._fetch_json(api_url)
        if not data or "items" not in data:
            return []

        for item in data.get("items", []):
            skill = DiscoveredSkill(
                name=item.get("name", "unknown"),
                description=item.get("description", "") or "No description",
                source="GitHub",
                url=item.get("html_url", ""),
                author=item.get("owner", {}).get("login", "unknown"),
                version=item.get("release_tag_name", "v1.0"),
                runtime="python",
                stars=item.get("stargazers_count", 0),
                tags=item.get("topics", []),
                last_updated=item.get("updated_at", ""),
            )
            skills.append(skill)

        # Cache results
        self._cache[cache_key] = {
            "timestamp": time.time(),
            "skills": [s.to_dict() for s in skills],
        }
        self._save_cache()

        return skills

    def _search_registry(self, source: SkillSource, query: str) -> list[DiscoveredSkill]:
        """
        Search a skill registry (e.g., agentskills.io).
        """
        skills: list[DiscoveredSkill] = []
        cache_key = f"registry:{source.url}:{query}"

        if self._is_cache_fresh(cache_key):
            try:
                return [
                    DiscoveredSkill.from_dict(d)
                    for d in self._cache[cache_key].get("skills", [])
                ]
            except Exception:
                pass

        # Example: search agentskills.io
        search_url = f"{source.url}?q={urllib.parse.quote(query)}&limit=20"
        data = self._fetch_json(search_url)

        if data and "skills" in data:
            for item in data.get("skills", []):
                skill = DiscoveredSkill(
                    name=item.get("name", "unknown"),
                    description=item.get("description", ""),
                    source=source.name,
                    url=item.get("url", ""),
                    author=item.get("author", "unknown"),
                    version=item.get("version", "1.0"),
                    runtime=item.get("runtime", "python"),
                    downloads=item.get("downloads", 0),
                    tags=item.get("tags", []),
                    license=item.get("license", ""),
                )
                skills.append(skill)

        # Cache results
        self._cache[cache_key] = {
            "timestamp": time.time(),
            "skills": [s.to_dict() for s in skills],
        }
        self._save_cache()

        return skills

    def _matches_query(self, name: str, query: str) -> bool:
        """Check if skill name matches search query."""
        if not query:
            return True
        query_lower = query.lower()
        name_lower = name.lower()
        return query_lower in name_lower or name_lower in query_lower

    def evaluate(
        self,
        skill: DiscoveredSkill,
        agent_role: str = "",
        available_mcps: Optional[list[str]] = None,
    ) -> SkillEvaluation:
        """
        Evaluate a discovered skill on quality, security, and compatibility.

        Args:
            skill: DiscoveredSkill to evaluate.
            agent_role: Agent role for relevance scoring.
            available_mcps: List of available MCP IDs in TudouClaw.

        Returns:
            SkillEvaluation with scores and recommendation.
        """
        # Relevance score (0-1)
        relevance_score = self._compute_relevance_score(skill, agent_role)

        # Quality score (0-1): based on stars, maintenance, documentation
        quality_score = self._compute_quality_score(skill)

        # Security assessment
        security_risk, security_notes = self._assess_security(skill)

        # Compatibility check
        available_mcps = available_mcps or []
        compatibility, missing_deps = self._check_compatibility(
            skill, available_mcps
        )

        # Generate recommendation
        recommendation, reason = self._generate_recommendation(
            skill, relevance_score, quality_score, security_risk, compatibility
        )

        return SkillEvaluation(
            skill=skill,
            relevance_score=relevance_score,
            quality_score=quality_score,
            security_risk=security_risk,
            security_notes=security_notes,
            compatibility=compatibility,
            missing_deps=missing_deps,
            recommendation=recommendation,
            reason=reason,
        )

    def _compute_relevance_score(self, skill: DiscoveredSkill, agent_role: str) -> float:
        """Compute relevance score (0-1) for skill given agent role."""
        score = 0.5  # Base score

        # Boost for matching tags
        if agent_role:
            role_lower = agent_role.lower()
            for tag in skill.tags:
                if role_lower in tag.lower() or tag.lower() in role_lower:
                    score += 0.2
                    break

        # Use LLM if available for semantic scoring
        if self.llm_call_fn:
            try:
                prompt = (
                    f"Rate relevance (0-1) of skill '{skill.name}' to role '{agent_role}'. "
                    f"Description: {skill.description}"
                )
                response = self.llm_call_fn(prompt)
                try:
                    score = float(response.strip())
                    score = max(0.0, min(1.0, score))
                except ValueError:
                    pass  # Keep computed score
            except Exception as e:
                logger.warning(f"LLM scoring failed: {e}")

        return min(1.0, score)

    def _compute_quality_score(self, skill: DiscoveredSkill) -> float:
        """Compute quality score (0-1) based on stars, maintenance, docs."""
        score = 0.5  # Base

        # Stars (GitHub popularity)
        if skill.stars > 0:
            # Log scale: 0 stars = 0, 100 stars = +0.3, 1000 stars = +0.5
            stars_boost = min(0.5, (len(str(skill.stars)) - 1) * 0.1)
            score += stars_boost

        # Downloads (registry popularity)
        if skill.downloads > 0:
            downloads_boost = min(0.3, (len(str(skill.downloads)) - 1) * 0.05)
            score += downloads_boost

        # Maintenance (last_updated recency)
        if skill.last_updated:
            try:
                last_update = datetime.fromisoformat(
                    skill.last_updated.replace("Z", "+00:00")
                )
                days_since = (datetime.utcnow() - last_update).days
                if days_since < 30:
                    score += 0.2
                elif days_since < 180:
                    score += 0.1
                # Old skills get no boost, no penalty
            except Exception:
                pass

        # License (presence is positive signal)
        if skill.license:
            score += 0.1

        return min(1.0, score)

    def _assess_security(self, skill: DiscoveredSkill) -> tuple[str, list[str]]:
        """
        Assess security risk based on runtime, dependencies, author.

        Returns: (risk_level, notes)
            risk_level: "low", "medium", "high"
            notes: List of specific security concerns
        """
        notes: list[str] = []
        risk_level = "low"

        # Runtime assessment (this is primary)
        if skill.runtime == "shell":
            risk_level = "high"
            notes.append("Shell runtime allows arbitrary command execution")
        elif skill.runtime == "python":
            # Python with HTTP access
            if any(
                dep in skill.dependencies
                for dep in ["requests", "urllib", "httpx", "aiohttp"]
            ):
                risk_level = "medium"
                notes.append("Python runtime with HTTP access (network dependency)")

            # Python with subprocess
            if any(
                dep in skill.dependencies for dep in ["subprocess", "os.system"]
            ):
                risk_level = "high"
                notes.append("Python with subprocess/system call access")
        elif skill.runtime == "markdown":
            # Markdown runtime is guidance-only, inherently low risk — don't bump for missing author
            notes.append("Markdown runtime (guidance-only, no code execution)")
            return "low", notes

        # For non-markdown: check author reputation
        if skill.author in ["unknown", "anonymous"]:
            # Bump risk by one level
            if risk_level == "low":
                risk_level = "medium"
            elif risk_level == "medium":
                risk_level = "high"
            notes.append("Unknown or anonymous author")

        # License check (only penalize if we also have other risk factors)
        if not skill.license or skill.license.lower() == "unknown":
            if risk_level == "low" and skill.runtime == "python":
                risk_level = "medium"
                notes.append("No license specified (legal risk)")
            elif risk_level == "low":
                notes.append("No license specified")

        # High star count reduces risk
        if skill.stars >= 100:
            if risk_level == "high":
                risk_level = "medium"
            if risk_level == "medium":
                risk_level = "low"
            notes.append("Community validation (high star count)")

        return risk_level, notes

    def _check_compatibility(
        self,
        skill: DiscoveredSkill,
        available_mcps: Optional[list[str]] = None,
    ) -> tuple[str, list[str]]:
        """
        Check if skill dependencies are available.

        Returns: (compatibility_status, missing_deps)
            compatibility_status: "compatible", "needs_deps", "incompatible"
            missing_deps: List of missing dependency IDs
        """
        available_mcps = available_mcps or []
        missing = [
            dep for dep in skill.dependencies if dep not in available_mcps
        ]

        if not missing:
            return "compatible", []

        if len(missing) <= 2:
            return "needs_deps", missing

        return "incompatible", missing

    def _generate_recommendation(
        self,
        skill: DiscoveredSkill,
        relevance_score: float,
        quality_score: float,
        security_risk: str,
        compatibility: str,
    ) -> tuple[str, str]:
        """
        Generate recommendation level and reason.

        Returns: (recommendation, reason)
            recommendation: "recommended", "caution", "skip"
        """
        # Skip if too low quality or incompatible
        if quality_score < MIN_QUALITY_SCORE_FOR_RECOMMENDATION:
            return "skip", "Low quality score"

        if compatibility == "incompatible":
            return "skip", "Missing critical dependencies"

        # Skip high security risk with low stars
        if security_risk == "high" and skill.stars < 50:
            return "skip", "High security risk with limited community validation"

        # Recommend if good quality and compatible
        if quality_score >= 0.7 and compatibility == "compatible":
            return "recommended", "High quality, well-maintained, compatible"

        # Caution for medium scores or medium security
        if security_risk == "medium" or compatibility == "needs_deps":
            reason = []
            if security_risk == "medium":
                reason.append("medium security risk")
            if compatibility == "needs_deps":
                reason.append("some dependencies may need configuration")
            return "caution", "Proceed with care: " + ", ".join(reason)

        # Default to skip
        return "skip", "Quality score below threshold"

    def generate_report(
        self,
        query: str,
        agent_role: str = "",
        max_results: int = 10,
        available_mcps: Optional[list[str]] = None,
    ) -> SkillRecommendation:
        """
        Full pipeline: search → evaluate → rank → generate report.

        Args:
            query: Search query.
            agent_role: Agent role for context.
            max_results: Maximum number of skills to evaluate.
            available_mcps: List of available MCP IDs.

        Returns:
            SkillRecommendation with ranked evaluations and markdown report.
        """
        # Search
        skills = self.search(query, agent_role, max_results)
        logger.info(f"Found {len(skills)} skills for query: {query}")

        # Evaluate
        evaluations = []
        for skill in skills:
            eval_result = self.evaluate(skill, agent_role, available_mcps)
            evaluations.append(eval_result)

        # Rank: by recommendation level, then quality score
        def sort_key(eval_result: SkillEvaluation) -> tuple:
            rec_order = {"recommended": 0, "caution": 1, "skip": 2}
            return (rec_order.get(eval_result.recommendation, 3), -eval_result.quality_score)

        evaluations.sort(key=sort_key)

        # Generate markdown report
        report_md = self._render_report_md(query, agent_role, evaluations)

        return SkillRecommendation(
            query=query,
            agent_role=agent_role,
            evaluations=evaluations,
            generated_at=time.time(),
            report_md=report_md,
        )

    def _render_report_md(
        self,
        query: str,
        agent_role: str,
        evaluations: list[SkillEvaluation],
    ) -> str:
        """
        Render markdown recommendation report.

        Supports Chinese and English based on self.language.
        """
        is_zh = self.language.startswith("zh")

        if is_zh:
            header = "# 技能推荐报告"
            search_label = "搜索"
            role_label = "角色"
            time_label = "时间"
            recommended_header = "## 推荐安装 (Recommended)"
            caution_header = "## 需注意 (Caution)"
            skip_header = "## 不推荐 (Skip)"
            source_label = "来源"
            author_label = "作者"
            desc_label = "描述"
            risk_label = "安全风险"
            compat_label = "兼容性"
            install_label = "安装"
            low_risk = "🟢 低"
            med_risk = "🟡 中"
            high_risk = "🔴 高"
            compatible = "✅ 兼容"
            needs_deps = "⚠️ 需依赖"
            incompatible = "❌ 不兼容"
        else:
            header = "# Skill Recommendations Report"
            search_label = "Query"
            role_label = "Role"
            time_label = "Generated"
            recommended_header = "## Recommended"
            caution_header = "## Caution"
            skip_header = "## Not Recommended"
            source_label = "Source"
            author_label = "Author"
            desc_label = "Description"
            risk_label = "Security Risk"
            compat_label = "Compatibility"
            install_label = "Install"
            low_risk = "🟢 Low"
            med_risk = "🟡 Medium"
            high_risk = "🔴 High"
            compatible = "✅ Compatible"
            needs_deps = "⚠️ Needs Dependencies"
            incompatible = "❌ Incompatible"

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        lines = [
            header,
            "",
            f"{search_label}: \"{query}\" | {role_label}: {agent_role or 'N/A'} | {time_label}: {now}",
            "",
        ]

        # Group by recommendation
        by_rec = {}
        for eval_result in evaluations:
            rec = eval_result.recommendation
            if rec not in by_rec:
                by_rec[rec] = []
            by_rec[rec].append(eval_result)

        # Render sections
        if "recommended" in by_rec:
            lines.append(recommended_header)
            lines.append("")
            for i, eval_result in enumerate(by_rec["recommended"], 1):
                lines.extend(self._render_skill_entry(
                    eval_result, i,
                    low_risk, med_risk, high_risk, compatible,
                    needs_deps, incompatible,
                    source_label, author_label, desc_label, risk_label,
                    compat_label, install_label, is_zh
                ))

        if "caution" in by_rec:
            lines.append(caution_header)
            lines.append("")
            for i, eval_result in enumerate(by_rec["caution"], 1):
                lines.extend(self._render_skill_entry(
                    eval_result, i,
                    low_risk, med_risk, high_risk, compatible,
                    needs_deps, incompatible,
                    source_label, author_label, desc_label, risk_label,
                    compat_label, install_label, is_zh
                ))

        if "skip" in by_rec and len(evaluations) <= 5:
            lines.append(skip_header)
            lines.append("")
            for i, eval_result in enumerate(by_rec["skip"], 1):
                lines.extend(self._render_skill_entry(
                    eval_result, i,
                    low_risk, med_risk, high_risk, compatible,
                    needs_deps, incompatible,
                    source_label, author_label, desc_label, risk_label,
                    compat_label, install_label, is_zh
                ))

        lines.append("")
        if is_zh:
            lines.append("---")
            lines.append("*SkillScout 自动生成。所有安装操作需用户确认。*")
        else:
            lines.append("---")
            lines.append("*Generated by SkillScout. All installations require user confirmation.*")

        return "\n".join(lines)

    def _render_skill_entry(
        self,
        eval_result: SkillEvaluation,
        index: int,
        low_risk: str,
        med_risk: str,
        high_risk: str,
        compatible: str,
        needs_deps: str,
        incompatible: str,
        source_label: str,
        author_label: str,
        desc_label: str,
        risk_label: str,
        compat_label: str,
        install_label: str,
        is_zh: bool,
    ) -> list[str]:
        """Render a single skill entry in markdown."""
        skill = eval_result.skill
        stars_str = f" ⭐×{skill.stars}" if skill.stars > 0 else ""

        risk_icon = {
            "low": low_risk,
            "medium": med_risk,
            "high": high_risk,
        }.get(eval_result.security_risk, low_risk)

        compat_icon = {
            "compatible": compatible,
            "needs_deps": needs_deps,
            "incompatible": incompatible,
        }.get(eval_result.compatibility, compatible)

        lines = [
            f"### {index}. {skill.name}{stars_str}",
            f"- **{source_label}**: {skill.source} | **{author_label}**: {skill.author}",
            f"- **{desc_label}**: {skill.description}",
            f"- **{risk_label}**: {risk_icon} | **{compat_label}**: {compat_icon}",
        ]

        # Add reason and missing deps if needed
        if eval_result.reason:
            lines.append(f"- **{install_label if not is_zh else '说明'}**: {eval_result.reason}")

        if eval_result.missing_deps:
            deps_str = ", ".join(eval_result.missing_deps)
            if is_zh:
                lines.append(f"- **缺失依赖**: {deps_str}")
            else:
                lines.append(f"- **Missing dependencies**: {deps_str}")

        # Installation command
        lines.append(f"- **URL**: `{skill.url}`")
        lines.append("")

        return lines

    def prepare_install(
        self,
        skill: DiscoveredSkill,
        output_dir: str,
    ) -> dict:
        """
        Prepare install instructions/download script for user.

        Does NOT download automatically — generates instructions only.

        Args:
            skill: Skill to install.
            output_dir: Directory to write installation scripts.

        Returns:
            {
                "install_command": str,  # Shell command to install
                "manual_steps": list[str],  # Step-by-step instructions
                "script_path": str,  # Path to generated install script
            }
        """
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        script_filename = f"install_{skill.name}.sh"
        script_path = output_path / script_filename

        # Generate install script
        script_lines = [
            "#!/bin/bash",
            f"# Install {skill.name} from {skill.source}",
            f"# Source: {skill.url}",
            f"# Author: {skill.author}",
            f"# Version: {skill.version}",
            "",
            "set -e",
            "",
        ]

        # Clone from GitHub if applicable
        if "github.com" in skill.url:
            script_lines.extend([
                f"# Clone repository",
                f"git clone {skill.url} ./{skill.name}",
                f"cd ./{skill.name}",
                "",
            ])

        # Generic install instructions
        script_lines.extend([
            "# Install skill to TudouClaw",
            "# Option 1: Direct path installation",
            f"skill install . --name {skill.name}",
            "",
            "# Option 2: From online source",
            f"skill install {skill.url}",
            "",
            "echo 'Installation complete. Verify with: skill list'",
        ])

        # Write script
        with open(script_path, "w") as f:
            f.write("\n".join(script_lines))

        # Make executable
        os.chmod(script_path, 0o755)

        install_cmd = f"skill install {skill.url}"

        manual_steps = [
            f"1. Review: {skill.name} by {skill.author}",
            f"   URL: {skill.url}",
            f"   Runtime: {skill.runtime}",
            f"2. Run installation script: bash {script_path}",
            f"3. Verify: skill list | grep {skill.name}",
            f"4. Grant to agent: agent grant-skill {skill.name}",
        ]

        return {
            "install_command": install_cmd,
            "manual_steps": manual_steps,
            "script_path": str(script_path),
        }
