#!/usr/bin/env python3
import argparse
import os
import re
import sys


def _read(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _validate_frontmatter(skill_md: str) -> list[str]:
    errs: list[str] = []
    if not skill_md.startswith("---\n"):
        return ["SKILL.md must start with YAML frontmatter (---)"]
    end = skill_md.find("\n---\n", 4)
    if end < 0:
        return ["SKILL.md frontmatter must end with ---"]
    fm = skill_md[4:end].strip("\n")
    keys = []
    for line in fm.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        m = re.match(r"^([a-zA-Z0-9_-]+)\s*:\s*(.*)$", line)
        if not m:
            errs.append(f"Invalid frontmatter line: {line!r}")
            continue
        keys.append(m.group(1))
    if keys.count("name") != 1:
        errs.append("Frontmatter must include exactly one 'name:'")
    if keys.count("description") != 1:
        errs.append("Frontmatter must include exactly one 'description:'")
    extra = [k for k in keys if k not in {"name", "description"}]
    if extra:
        errs.append(f"Frontmatter must only contain name/description; found: {sorted(set(extra))}")
    return errs


def main() -> int:
    parser = argparse.ArgumentParser(description="Lightweight local validator for this skill (no PyYAML).")
    parser.add_argument("skill_dir", help="Skill directory path")
    args = parser.parse_args()

    skill_dir = os.path.abspath(args.skill_dir)
    errs: list[str] = []

    skill_md_path = os.path.join(skill_dir, "SKILL.md")
    if not os.path.exists(skill_md_path):
        errs.append("Missing SKILL.md")
    else:
        errs.extend(_validate_frontmatter(_read(skill_md_path)))

    openai_yaml_path = os.path.join(skill_dir, "agents", "openai.yaml")
    if not os.path.exists(openai_yaml_path):
        errs.append("Missing agents/openai.yaml")
    else:
        text = _read(openai_yaml_path)
        for needle in ['display_name:', 'short_description:', 'default_prompt:', 'allow_implicit_invocation:']:
            if needle not in text:
                errs.append(f"agents/openai.yaml missing field: {needle}")

    for rel in ["scripts", "references"]:
        p = os.path.join(skill_dir, rel)
        if not os.path.isdir(p):
            errs.append(f"Missing directory: {rel}/")

    if errs:
        for e in errs:
            print(f"[ERROR] {e}")
        return 2

    print("[OK] Skill structure looks valid (local checks).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

