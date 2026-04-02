from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import re

from app.platform.skills.base import SkillBundle, SkillResource, SkillStageConfig


_FRONTMATTER_PATTERN = re.compile(r"^---\n(?P<frontmatter>.*?)\n---\n(?P<body>.*)$", re.DOTALL)
_HEADER_PATTERN = re.compile(r"^##\s+(?P<title>.+?)\s*$")
_KEY_VALUE_PATTERN = re.compile(r"^(?P<key>[A-Za-z0-9_\-]+):\s*(?P<value>.*)$")


class SkillFileLoader:
    def __init__(self, root_dir: Path) -> None:
        self.root_dir = root_dir

    def list_skill_dirs(self) -> list[Path]:
        if not self.root_dir.exists():
            return []
        return sorted(path for path in self.root_dir.iterdir() if path.is_dir() and (path / "SKILL.md").exists())

    def scan_metadata(self) -> list[SkillBundle]:
        bundles: list[SkillBundle] = []
        for skill_dir in self.list_skill_dirs():
            bundles.append(self._load_bundle(skill_dir, hydrate=False))
        return bundles

    def hydrate(self, skill_id: str, source_dir: str) -> SkillBundle:
        skill_dir = Path(source_dir)
        if not skill_dir.exists():
            skill_dir = self.root_dir / skill_id
        return self._load_bundle(skill_dir, hydrate=True)

    def _load_bundle(self, skill_dir: Path, *, hydrate: bool) -> SkillBundle:
        raw = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
        match = _FRONTMATTER_PATTERN.match(raw.strip())
        if not match:
            raise ValueError(f"Skill file at {skill_dir / 'SKILL.md'} is missing valid frontmatter")
        frontmatter = self._parse_frontmatter(match.group("frontmatter"))
        body = match.group("body").strip()
        sections = self._parse_sections(body)

        skill_id = frontmatter.get("name", skill_dir.name).strip()
        bundle = SkillBundle(
            skill_id=skill_id,
            name=frontmatter.get("display_name", self._humanize_name(skill_id)),
            description=frontmatter.get("description", "").strip(),
            prompt_fragments=sections.get("instructions", []),
            tool_names=frontmatter.get("tools", []),
            tags=frontmatter.get("tags", []),
            stage_configs={
                stage: SkillStageConfig(stage=stage, prompt_fragments=fragments)
                for stage, fragments in sections.get("stage_fragments", {}).items()
            },
            metadata={key: value for key, value in frontmatter.items() if key not in {"name", "display_name", "description", "tools", "tags"}},
            source_dir=str(skill_dir),
            instructions_markdown=body if hydrate else "",
            hydrated=hydrate,
        )
        bundle.references = self._load_resources(skill_dir, sections.get("references", []), resource_type="reference", load_content=hydrate)
        bundle.scripts = self._load_resources(skill_dir, sections.get("scripts", []), resource_type="script", load_content=False)
        bundle.assets = self._load_resources(skill_dir, sections.get("assets", []), resource_type="asset", load_content=False)
        return bundle

    @staticmethod
    def _humanize_name(skill_id: str) -> str:
        return " ".join(part.capitalize() for part in skill_id.replace("-", "_").split("_") if part)

    def _load_resources(
        self,
        skill_dir: Path,
        relative_paths: list[str],
        *,
        resource_type: str,
        load_content: bool,
    ) -> list[SkillResource]:
        resources: list[SkillResource] = []
        for relative_path in relative_paths:
            absolute_path = (skill_dir / relative_path).resolve()
            content = ""
            if load_content and absolute_path.exists() and absolute_path.is_file():
                content = absolute_path.read_text(encoding="utf-8", errors="ignore")[:2000].strip()
            resources.append(
                SkillResource(
                    title=Path(relative_path).name,
                    resource_type=resource_type,
                    relative_path=relative_path,
                    absolute_path=str(absolute_path),
                    content=content,
                )
            )
        return resources

    @staticmethod
    def _parse_frontmatter(frontmatter_text: str) -> dict[str, object]:
        result: dict[str, object] = {}
        current_list_key: str | None = None
        for raw_line in frontmatter_text.splitlines():
            line = raw_line.rstrip()
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if stripped.startswith("- "):
                if current_list_key is None:
                    continue
                result.setdefault(current_list_key, [])
                casted = result[current_list_key]
                if isinstance(casted, list):
                    casted.append(stripped[2:].strip())
                continue
            match = _KEY_VALUE_PATTERN.match(stripped)
            if not match:
                continue
            key = match.group("key").strip()
            value = match.group("value").strip()
            if not value:
                result[key] = []
                current_list_key = key
                continue
            current_list_key = None
            result[key] = value
        return result

    @staticmethod
    def _parse_sections(body: str) -> dict[str, object]:
        current_section = "instructions"
        current_stage: str | None = None
        instructions: list[str] = []
        stage_fragments: dict[str, list[str]] = {}
        references: list[str] = []
        scripts: list[str] = []
        assets: list[str] = []
        section_targets = {
            "references": references,
            "scripts": scripts,
            "assets": assets,
        }

        for raw_line in body.splitlines():
            line = raw_line.rstrip()
            stripped = line.strip()
            if stripped.startswith("# "):
                continue
            header_match = _HEADER_PATTERN.match(stripped)
            if header_match:
                title = header_match.group("title").strip()
                if title.lower().startswith("stage:"):
                    current_section = "stage"
                    current_stage = title.split(":", 1)[1].strip()
                    stage_fragments.setdefault(current_stage, [])
                elif title.lower() in {"instructions", "references", "scripts", "assets"}:
                    current_section = title.lower()
                    current_stage = None
                else:
                    current_section = "instructions"
                    current_stage = None
                continue
            if not stripped:
                continue
            if current_section == "stage" and current_stage:
                item = stripped[2:].strip() if stripped.startswith("- ") else stripped
                if item:
                    stage_fragments[current_stage].append(item)
                continue
            if current_section in section_targets:
                item = stripped[2:].strip() if stripped.startswith("- ") else stripped
                if item:
                    section_targets[current_section].append(item)
                continue
            item = stripped[2:].strip() if stripped.startswith("- ") else stripped
            if item:
                instructions.append(item)

        return {
            "instructions": instructions,
            "stage_fragments": stage_fragments,
            "references": references,
            "scripts": scripts,
            "assets": assets,
        }
