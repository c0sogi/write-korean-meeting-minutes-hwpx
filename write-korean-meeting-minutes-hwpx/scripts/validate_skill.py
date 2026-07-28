#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from _console import configure_utf8_output

configure_utf8_output()

ALLOWED_FIELDS = {"name", "description"}
NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def parse_frontmatter(text: str) -> tuple[dict[str, str], list[str]]:
    errors: list[str] = []
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, ["SKILL.md가 YAML frontmatter 구분자(---)로 시작하지 않음"]
    try:
        end = next(i for i, line in enumerate(lines[1:], start=1) if line.strip() == "---")
    except StopIteration:
        return {}, ["YAML frontmatter 종료 구분자(---)가 없음"]

    fields: dict[str, str] = {}
    for lineno, line in enumerate(lines[1:end], start=2):
        if not line.strip() or line.startswith((" ", "\t")):
            continue
        if ":" not in line:
            errors.append(f"frontmatter {lineno}행: key: value 형식이 아님")
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if key in fields:
            errors.append(f"frontmatter {lineno}행: 중복 필드 {key}")
        fields[key] = value
    return fields, errors


def main() -> None:
    parser = argparse.ArgumentParser(description="번들 Agent Skill의 핵심 명세 규칙을 검사합니다.")
    parser.add_argument("skill_dir", nargs="?", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--strict", action="store_true", help="권장사항 경고도 오류로 처리합니다.")
    args = parser.parse_args()

    root = args.skill_dir.expanduser().resolve()
    errors: list[str] = []
    warnings: list[str] = []
    skill_file = root / "SKILL.md"
    if not root.is_dir():
        errors.append("스킬 디렉터리를 찾을 수 없음")
        text = ""
    elif not skill_file.is_file():
        errors.append("필수 파일 SKILL.md가 없음")
        text = ""
    else:
        text = skill_file.read_text(encoding="utf-8")

    fields, parse_errors = parse_frontmatter(text) if text else ({}, [])
    errors.extend(parse_errors)
    extra = set(fields) - ALLOWED_FIELDS
    if extra:
        errors.append("허용되지 않은 frontmatter 필드: " + ", ".join(sorted(extra)))

    name = fields.get("name", "").strip("'\"")
    description = fields.get("description", "").strip("'\"")
    compatibility = fields.get("compatibility", "").strip("'\"")

    if not name:
        errors.append("필수 필드 name이 비어 있음")
    else:
        if len(name) > 64:
            errors.append("name이 64자를 초과함")
        if not NAME_RE.fullmatch(name):
            errors.append("name은 소문자 영숫자와 단일 하이픈만 사용할 수 있으며 연속 하이픈을 쓸 수 없음")
        if root.name != name:
            errors.append(f"name({name})과 상위 디렉터리명({root.name})이 다름")

    if not description:
        errors.append("필수 필드 description이 비어 있음")
    elif len(description) > 1024:
        errors.append("description이 1024자를 초과함")

    if compatibility and len(compatibility) > 500:
        errors.append("compatibility가 500자를 초과함")

    line_count = len(text.splitlines()) if text else 0
    if line_count > 500:
        warnings.append(f"SKILL.md가 {line_count}줄로 500줄 권장 한도를 초과함")

    for required_dir in ("scripts", "references", "assets"):
        if not (root / required_dir).is_dir():
            warnings.append(f"이 스킬에서 사용하는 {required_dir}/ 디렉터리가 없음")

    status = "ok" if not errors and not (args.strict and warnings) else "error"
    print(
        json.dumps(
            {
                "status": status,
                "skill_dir": str(root),
                "metrics": {
                    "name_length": len(name),
                    "description_length": len(description),
                    "compatibility_length": len(compatibility),
                    "skill_md_lines": line_count,
                },
                "errors": errors,
                "warnings": warnings,
                "note": "Agent Skills 핵심 명세를 확인하는 번들 로컬 검사이며 공식 skills-ref의 완전한 대체는 아닙니다.",
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    raise SystemExit(0 if status == "ok" else 1)


if __name__ == "__main__":
    main()
