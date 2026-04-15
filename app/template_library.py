"""
Template Library — 模版库管理系统

为Agent提供领域专业的提示词工程模版。每个模版是一个结构化的 .md 文件，
包含该领域任务执行需要关注的维度、步骤、检查清单和最佳实践。

Agent在收到任务时，自动匹配对应的模版，注入到上下文中作为执行指南。

Architecture:
  TemplateLibrary (管理所有模版)
    └── Template (.md files in templates/ directory)
         ├── 产品设计模版
         ├── 市场调查模版
         ├── 代码审查模版
         ├── ...
         └── 自定义模版

Usage:
    lib = get_template_library()
    templates = lib.match_templates("帮我做一个市场调研")
    context = lib.render_for_agent(templates)
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("tudou.template_library")

# Default templates directory
_DEFAULT_TEMPLATES_DIR = str(Path(__file__).resolve().parent.parent / "templates")


@dataclass
class Template:
    """A single template entry."""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:10])
    name: str = ""                    # display name, e.g. "产品设计模版"
    filename: str = ""                # e.g. "product_design.md"
    description: str = ""             # short description
    roles: list[str] = field(default_factory=list)  # applicable roles
    tags: list[str] = field(default_factory=list)    # matching keywords
    category: str = "general"         # general | development | business | research | operations
    content: str = ""                 # the actual markdown content (loaded lazily)
    created_at: float = field(default_factory=time.time)
    created_by: str = "system"
    enabled: bool = True

    def to_dict(self, include_content: bool = False) -> dict:
        d = {
            "id": self.id, "name": self.name,
            "filename": self.filename,
            "description": self.description,
            "roles": self.roles,
            "tags": self.tags,
            "category": self.category,
            "created_at": self.created_at,
            "created_by": self.created_by,
            "enabled": self.enabled,
        }
        if include_content:
            d["content"] = self.content
        return d

    @staticmethod
    def from_dict(d: dict) -> Template:
        return Template(
            id=d.get("id", uuid.uuid4().hex[:10]),
            name=d.get("name", ""),
            filename=d.get("filename", ""),
            description=d.get("description", ""),
            roles=d.get("roles", []),
            tags=d.get("tags", []),
            category=d.get("category", "general"),
            content=d.get("content", ""),
            created_at=d.get("created_at", time.time()),
            created_by=d.get("created_by", "system"),
            enabled=d.get("enabled", True),
        )


class TemplateLibrary:
    """Manages all templates. Loads from templates/ directory."""

    def __init__(self, templates_dir: str = ""):
        self.templates_dir = templates_dir or _DEFAULT_TEMPLATES_DIR
        self.templates: dict[str, Template] = {}
        self._index_file = os.path.join(self.templates_dir, "_index.json")
        self._load_index()

    def _load_index(self):
        """Load template index from disk."""
        if os.path.exists(self._index_file):
            try:
                with open(self._index_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for td in data.get("templates", []):
                    tpl = Template.from_dict(td)
                    self.templates[tpl.id] = tpl
                logger.info("Loaded %d templates from index", len(self.templates))
            except Exception:
                import traceback
                traceback.print_exc()
        # Also scan for .md files not yet in index
        self._scan_directory()

    def _scan_directory(self):
        """Scan templates directory for .md files not yet indexed."""
        if not os.path.isdir(self.templates_dir):
            os.makedirs(self.templates_dir, exist_ok=True)
            return
        known_files = {t.filename for t in self.templates.values()}
        for fname in os.listdir(self.templates_dir):
            if fname.endswith(".md") and fname != "_index.md" and fname not in known_files:
                fpath = os.path.join(self.templates_dir, fname)
                try:
                    content = Path(fpath).read_text(encoding="utf-8", errors="replace")
                    # Extract title from first line
                    first_line = content.split("\n")[0].strip().lstrip("#").strip()
                    tpl = Template(
                        name=first_line or fname.replace(".md", "").replace("_", " ").title(),
                        filename=fname,
                        description=f"Auto-imported from {fname}",
                        content=content,
                        tags=self._extract_tags(content),
                    )
                    self.templates[tpl.id] = tpl
                except Exception:
                    pass
        self._save_index()

    def _extract_tags(self, content: str) -> list[str]:
        """Extract keywords from content for matching."""
        # Look for YAML frontmatter tags or extract from headers
        tags = []
        for line in content.split("\n")[:30]:
            if line.startswith("## "):
                tags.append(line[3:].strip().lower())
            if line.startswith("tags:"):
                tags.extend([t.strip() for t in line[5:].split(",") if t.strip()])
        return tags

    def _save_index(self):
        """Save template index to disk."""
        os.makedirs(self.templates_dir, exist_ok=True)
        data = {"templates": [t.to_dict(include_content=False)
                              for t in self.templates.values()]}
        try:
            with open(self._index_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def add_template(self, name: str, content: str,
                     description: str = "", roles: list[str] | None = None,
                     tags: list[str] | None = None, category: str = "general",
                     created_by: str = "admin") -> Template:
        """Add a new template. Saves the .md file and updates index."""
        # Generate safe filename
        filename = re.sub(r"[^\w\u4e00-\u9fff\-]", "_", name) + ".md"
        filename = filename.lower()

        tpl = Template(
            name=name, filename=filename,
            description=description,
            roles=roles or [], tags=tags or [],
            category=category, content=content,
            created_by=created_by,
        )

        # Save .md file
        fpath = os.path.join(self.templates_dir, filename)
        Path(fpath).write_text(content, encoding="utf-8")

        self.templates[tpl.id] = tpl
        self._save_index()
        logger.info("Template added: %s (%s)", name, filename)
        return tpl

    def update_template(self, template_id: str, content: str = "",
                        name: str = "", description: str = "",
                        roles: list[str] | None = None,
                        tags: list[str] | None = None) -> Template | None:
        tpl = self.templates.get(template_id)
        if not tpl:
            return None
        if content:
            tpl.content = content
            fpath = os.path.join(self.templates_dir, tpl.filename)
            Path(fpath).write_text(content, encoding="utf-8")
        if name:
            tpl.name = name
        if description:
            tpl.description = description
        if roles is not None:
            tpl.roles = roles
        if tags is not None:
            tpl.tags = tags
        self._save_index()
        return tpl

    def remove_template(self, template_id: str) -> bool:
        tpl = self.templates.pop(template_id, None)
        if not tpl:
            return False
        # Remove file
        fpath = os.path.join(self.templates_dir, tpl.filename)
        try:
            os.remove(fpath)
        except OSError:
            pass
        self._save_index()
        return True

    def get_template(self, template_id: str) -> Template | None:
        tpl = self.templates.get(template_id)
        if tpl and not tpl.content:
            # Lazy load content
            fpath = os.path.join(self.templates_dir, tpl.filename)
            if os.path.exists(fpath):
                tpl.content = Path(fpath).read_text(encoding="utf-8", errors="replace")
        return tpl

    def get_template_content(self, template_id: str) -> str:
        tpl = self.get_template(template_id)
        return tpl.content if tpl else ""

    def list_templates(self, role: str = "", category: str = "") -> list[Template]:
        """List templates, optionally filtered by role or category."""
        result = []
        for tpl in self.templates.values():
            if not tpl.enabled:
                continue
            if role and tpl.roles and role not in tpl.roles:
                continue
            if category and tpl.category != category:
                continue
            result.append(tpl)
        return sorted(result, key=lambda t: t.name)

    def match_templates(self, message: str, role: str = "",
                        limit: int = 3) -> list[Template]:
        """Match templates relevant to a user message.

        Uses keyword matching against template tags, names, and descriptions.
        """
        tokens = set(message.lower().split())
        scored = []
        for tpl in self.templates.values():
            if not tpl.enabled:
                continue
            score = 0
            # Role match bonus
            if role and tpl.roles and role in tpl.roles:
                score += 5
            # Tag matching
            for tag in tpl.tags:
                for token in tokens:
                    if token in tag.lower() or tag.lower() in message.lower():
                        score += 3
            # Name matching
            for token in tokens:
                if token in tpl.name.lower():
                    score += 4
            # Description matching
            for token in tokens:
                if token in tpl.description.lower():
                    score += 1
            if score > 0:
                scored.append((score, tpl))
        scored.sort(key=lambda x: -x[0])
        return [t for _, t in scored[:limit]]

    def render_for_agent(self, templates: list[Template],
                         max_chars: int = 6000) -> str:
        """Render matched templates into a context block for agent injection."""
        if not templates:
            return ""

        parts = ["<template_library>"]
        parts.append("以下是与当前任务相关的执行模版，请参考模版中的方法论和检查清单来执行任务:")
        char_count = 0
        for tpl in templates:
            # Lazy load content
            if not tpl.content:
                fpath = os.path.join(self.templates_dir, tpl.filename)
                if os.path.exists(fpath):
                    tpl.content = Path(fpath).read_text(encoding="utf-8", errors="replace")
            content = tpl.content
            if char_count + len(content) > max_chars:
                # Truncate
                remaining = max_chars - char_count
                content = content[:remaining] + "\n...(truncated)"
            parts.append(f"\n--- {tpl.name} ---")
            parts.append(content)
            char_count += len(content)
            if char_count >= max_chars:
                break
        parts.append("</template_library>")
        return "\n".join(parts)

    def push_to_agent_enhancer(self, template_id: str,
                                enhancer: Any) -> bool:
        """Push a template's content as knowledge entries into an agent's enhancer."""
        tpl = self.get_template(template_id)
        if not tpl or not enhancer:
            return False
        # Add as a high-priority knowledge entry
        enhancer.knowledge.add(
            title=f"模版: {tpl.name}",
            content=tpl.content[:3000],
            category="reference",
            tags=tpl.tags,
            priority=8,
            source="template_library",
        )
        logger.info("Pushed template '%s' to agent enhancer", tpl.name)
        return True


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_library: TemplateLibrary | None = None

def get_template_library(templates_dir: str = "") -> TemplateLibrary:
    global _library
    if _library is None:
        _library = TemplateLibrary(templates_dir=templates_dir)
    return _library

def init_template_library(templates_dir: str = "") -> TemplateLibrary:
    global _library
    _library = TemplateLibrary(templates_dir=templates_dir)
    return _library
