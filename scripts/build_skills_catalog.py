#!/usr/bin/env python3
"""Build app/data/community_skills.json from a directory of agency-agents
markdown files (format: YAML frontmatter + markdown body).

Usage:
  python scripts/build_skills_catalog.py <src_dir> [<out_path>]

Default out_path: app/data/community_skills.json
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

# Category icons (fallback to 📦)
CATEGORY_ICONS = {
    "academic": "🎓", "design": "🎨", "engineering": "💻",
    "finance": "💰", "game-development": "🎮", "hr": "👥",
    "legal": "⚖️", "marketing": "📣", "paid-media": "📊",
    "product": "📋", "project-management": "📅", "sales": "🤝",
    "spatial-computing": "🥽", "specialized": "✨", "strategy": "🧭",
    "supply-chain": "🏭", "support": "🎧", "testing": "🧪",
}

# How big each skill's knowledge body should be (chars)
BODY_MAX_CHARS = 2500
MAX_SECTIONS_PER_SKILL = 5
SECTION_CHAR_LIMIT = 600
IDENTITY_CHAR_LIMIT = 500


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Parse YAML-ish frontmatter. Returns (meta, body)."""
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end < 0:
        return {}, text
    head = text[3:end].strip()
    body = text[end + 4:].lstrip("\n")
    meta = {}
    for line in head.splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        key, _, val = line.partition(":")
        val = val.strip().strip('"').strip("'")
        meta[key.strip()] = val
    return meta, body


def extract_sections(body: str) -> list[dict]:
    """Split body by ## headers into knowledge entries."""
    sections = []
    lines = body.splitlines()
    current_title = None
    current_buf: list[str] = []
    for line in lines:
        m = re.match(r"^##\s+(.+)$", line)
        if m:
            if current_title and current_buf:
                content = "\n".join(current_buf).strip()
                if content:
                    sections.append({"title": current_title, "content": content})
            current_title = m.group(1).strip()
            current_buf = []
        else:
            if current_title:
                current_buf.append(line)
    if current_title and current_buf:
        content = "\n".join(current_buf).strip()
        if content:
            sections.append({"title": current_title, "content": content})
    return sections


def slugify(name: str) -> str:
    """Make safe preset id from file path stem."""
    return re.sub(r"[^a-z0-9_]+", "_", name.lower()).strip("_")


def build_catalog(src_dir: Path) -> dict:
    skills: list[dict] = []
    for md_path in sorted(src_dir.rglob("*.md")):
        rel = md_path.relative_to(src_dir)
        # Skip top-level docs
        top = rel.parts[0] if rel.parts else ""
        if top in ("", "README.md") or md_path.name in (
                "README.md", "README.zh-TW.md", "CATALOG.md", "AGENT-LIST.md",
                "CONTRIBUTING.md", "UPSTREAM.md", "LICENSE",
        ):
            continue
        # Skip integrations/scripts/examples and hidden directories
        if top in ("integrations", "scripts", "examples") or top.startswith("."):
            continue
        try:
            text = md_path.read_text(encoding="utf-8")
        except OSError:
            continue
        meta, body = parse_frontmatter(text)
        zh_name = meta.get("name", "").strip()
        desc = meta.get("description", "").strip()
        if not zh_name or not body:
            continue

        category = top
        icon = CATEGORY_ICONS.get(category, "📦")
        stem = md_path.stem  # e.g. sales-discovery-coach
        preset_id = f"agency_{slugify(stem)}"[:64]

        sections = extract_sections(body)[:MAX_SECTIONS_PER_SKILL]
        # Build knowledge entries from top sections. Cap body chars.
        entries = []
        total = 0
        for i, sec in enumerate(sections):
            content = sec["content"]
            if len(content) > SECTION_CHAR_LIMIT:
                content = content[:SECTION_CHAR_LIMIT] + "…"
            if total + len(content) > BODY_MAX_CHARS:
                break
            total += len(content)
            entries.append({
                "id": f"{preset_id}_k{i}",
                "title": sec["title"],
                "content": content,
                "category": "best_practice",
                "tags": [category, stem],
                "priority": 7 if i < 3 else 5,
            })

        # Persona identity entry (always first)
        identity = body.split("##", 1)[0].strip()
        if identity:
            if len(identity) > IDENTITY_CHAR_LIMIT:
                identity = identity[:IDENTITY_CHAR_LIMIT] + "…"
            entries.insert(0, {
                "id": f"{preset_id}_identity",
                "title": f"{zh_name} 身份与使命",
                "content": identity,
                "category": "reference",
                "tags": [category, stem],
                "priority": 9,
            })

        skills.append({
            "id": preset_id,
            "name": zh_name,
            "description": desc[:200],
            "icon": icon,
            "category": category,
            "source": "agency-agents-zh",
            "entries": entries,
        })

    catalog = {
        "version": 1,
        "source": "agency-agents-zh-main",
        "skills_count": len(skills),
        "categories": sorted(set(s["category"] for s in skills)),
        "skills": skills,
    }
    return catalog


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    src = Path(sys.argv[1]).expanduser().resolve()
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else (
        Path(__file__).resolve().parent.parent / "app" / "data" /
        "community_skills.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    print(f"Scanning {src} …")
    catalog = build_catalog(src)
    out.write_text(json.dumps(catalog, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    total_entries = sum(len(s["entries"]) for s in catalog["skills"])
    size_kb = out.stat().st_size / 1024
    print(f"Wrote {out}")
    print(f"  skills:       {catalog['skills_count']}")
    print(f"  categories:   {len(catalog['categories'])}")
    print(f"  entries:      {total_entries}")
    print(f"  file size:    {size_kb:.1f} KB")


if __name__ == "__main__":
    main()
