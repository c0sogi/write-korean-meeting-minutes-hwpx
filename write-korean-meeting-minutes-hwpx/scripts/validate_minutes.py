#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from _console import configure_utf8_output

configure_utf8_output()

REQUIRED_TOP = {"document_title", "metadata", "meeting_content", "meeting_result", "quality"}
REQUIRED_METADATA = {"agenda", "datetime", "responsible_org", "location", "participants", "main_agenda"}
REQUIRED_POINT = {"text", "emphasis", "important"}
REQUIRED_ACTION = {"task", "owner", "deadline", "status", "emphasis", "important"}
REQUIRED_QUALITY = {"missing_metadata", "ambiguous_terms", "asr_risk"}
PLACEHOLDER_RE = re.compile(r"(?:<[^>]+>|\bTODO\b|\bTBD\b|\[작성(?:\s*필요)?\])", re.IGNORECASE)


def as_nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def check_exact_keys(obj: dict[str, Any], required: set[str], path: str, errors: list[str]) -> None:
    missing = required - obj.keys()
    extra = obj.keys() - required
    if missing:
        errors.append(f"{path}: 필수 키 누락: {', '.join(sorted(missing))}")
    if extra:
        errors.append(f"{path}: 지원하지 않는 키: {', '.join(sorted(extra))}")


def validate_emphasis(
    text: str,
    emphasis: Any,
    important: Any,
    path: str,
    errors: list[str],
    warnings: list[str],
) -> tuple[int, int]:
    if not isinstance(emphasis, list) or not all(as_nonempty_string(x) for x in emphasis):
        errors.append(f"{path}.emphasis: 비어 있지 않은 문자열 배열이어야 함")
        emphasis = []
    if len(set(emphasis)) != len(emphasis):
        errors.append(f"{path}.emphasis: 중복 구절이 있음")
    emphasized_chars = 0
    for phrase in emphasis:
        if phrase not in text:
            errors.append(f"{path}.emphasis: 본문에 없는 구절: {phrase!r}")
        else:
            emphasized_chars += len(phrase)
    if not isinstance(important, bool):
        errors.append(f"{path}.important: 불리언이어야 함")
    elif important and not emphasis:
        warnings.append(f"{path}: important=true이지만 짧은 emphasis가 없어 문장 전체가 강조될 수 있음")
    return emphasized_chars, len(text)


def validate_point(
    point: Any,
    path: str,
    errors: list[str],
    warnings: list[str],
) -> tuple[int, int]:
    if not isinstance(point, dict):
        errors.append(f"{path}: 객체여야 함")
        return 0, 0
    check_exact_keys(point, REQUIRED_POINT, path, errors)
    text = point.get("text")
    if not as_nonempty_string(text):
        errors.append(f"{path}.text: 비어 있지 않은 문자열이어야 함")
        text = ""
    elif len(text) > 1200:
        errors.append(f"{path}.text: 1200자를 초과함")
    elif len(text) > 400:
        warnings.append(f"{path}.text: {len(text)}자로 길어 문단 분리가 필요할 수 있음")
    if text and PLACEHOLDER_RE.search(text):
        errors.append(f"{path}.text: 미완성 플레이스홀더가 포함됨")
    return validate_emphasis(
        text,
        point.get("emphasis"),
        point.get("important"),
        path,
        errors,
        warnings,
    )


def validate_string_array(value: Any, path: str, errors: list[str]) -> None:
    if not isinstance(value, list) or not all(as_nonempty_string(x) for x in value):
        errors.append(f"{path}: 비어 있지 않은 문자열 배열이어야 함")
    elif len(set(value)) != len(value):
        errors.append(f"{path}: 중복 항목이 있음")


def main() -> None:
    parser = argparse.ArgumentParser(description="HWPX 작성에 사용할 minutes.json을 검사합니다.")
    parser.add_argument("input", type=Path, help="검사할 minutes.json 경로")
    parser.add_argument("--strict", action="store_true", help="경고도 오류로 처리합니다.")
    args = parser.parse_args()

    path = args.input.expanduser().resolve()
    errors: list[str] = []
    warnings: list[str] = []

    if not path.is_file():
        print(json.dumps({"status": "error", "errors": ["입력 JSON을 찾을 수 없음"], "input": str(path)}, ensure_ascii=False, indent=2))
        raise SystemExit(2)

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "error", "errors": [f"JSON 읽기 실패: {exc}"]}, ensure_ascii=False, indent=2))
        raise SystemExit(2)

    if not isinstance(data, dict):
        errors.append("최상위 값은 객체여야 함")
        data = {}
    check_exact_keys(data, REQUIRED_TOP, "$", errors)

    title = data.get("document_title")
    if not as_nonempty_string(title):
        errors.append("$.document_title: 비어 있지 않은 문자열이어야 함")
    elif len(title) > 30:
        errors.append("$.document_title: 30자를 초과함")

    metadata = data.get("metadata")
    if not isinstance(metadata, dict):
        errors.append("$.metadata: 객체여야 함")
        metadata = {}
    else:
        check_exact_keys(metadata, REQUIRED_METADATA, "$.metadata", errors)
        for key in sorted(REQUIRED_METADATA - {"participants"}):
            value = metadata.get(key)
            if not isinstance(value, str):
                errors.append(f"$.metadata.{key}: 문자열이어야 함")
            elif not value.strip():
                warnings.append(f"$.metadata.{key}: 비어 있음; 검토본이면 '확인 필요' 사용을 고려")
        participants = metadata.get("participants")
        if isinstance(participants, str):
            if not participants.strip():
                warnings.append("$.metadata.participants: 비어 있음")
        elif isinstance(participants, list):
            if not participants or not all(as_nonempty_string(x) for x in participants):
                errors.append("$.metadata.participants: 비어 있지 않은 문자열 또는 문자열 배열이어야 함")
            elif len(set(participants)) != len(participants):
                errors.append("$.metadata.participants: 중복 참석자가 있음")
        else:
            errors.append("$.metadata.participants: 문자열 또는 문자열 배열이어야 함")

    total_emphasis = 0
    total_text = 0

    content = data.get("meeting_content")
    if not isinstance(content, dict):
        errors.append("$.meeting_content: 객체여야 함")
        content = {}
    else:
        expected = {"summary", "topics"}
        check_exact_keys(content, expected, "$.meeting_content", errors)
        e, t = validate_point(content.get("summary"), "$.meeting_content.summary", errors, warnings)
        total_emphasis += e
        total_text += t
        topics = content.get("topics")
        if not isinstance(topics, list):
            errors.append("$.meeting_content.topics: 배열이어야 함")
            topics = []
        if len(topics) == 0:
            errors.append("$.meeting_content.topics: 최소 1개 주제가 필요함")
        elif not 3 <= len(topics) <= 7:
            warnings.append(f"$.meeting_content.topics: {len(topics)}개; 일반적으로 3–7개가 읽기 좋음")
        if len(topics) > 10:
            errors.append("$.meeting_content.topics: 10개를 초과함")
        seen_titles: set[str] = set()
        for i, topic in enumerate(topics):
            path_prefix = f"$.meeting_content.topics[{i}]"
            if not isinstance(topic, dict):
                errors.append(f"{path_prefix}: 객체여야 함")
                continue
            check_exact_keys(topic, {"title", "points"}, path_prefix, errors)
            topic_title = topic.get("title")
            if not as_nonempty_string(topic_title):
                errors.append(f"{path_prefix}.title: 비어 있지 않은 문자열이어야 함")
            elif topic_title in seen_titles:
                errors.append(f"{path_prefix}.title: 중복 제목 {topic_title!r}")
            else:
                seen_titles.add(topic_title)
            points = topic.get("points")
            if not isinstance(points, list) or not points:
                errors.append(f"{path_prefix}.points: 최소 1개 항목이 필요함")
                continue
            for j, point in enumerate(points):
                e, t = validate_point(point, f"{path_prefix}.points[{j}]", errors, warnings)
                total_emphasis += e
                total_text += t

    result = data.get("meeting_result")
    if not isinstance(result, dict):
        errors.append("$.meeting_result: 객체여야 함")
        result = {}
    else:
        expected = {"summary_points", "action_items", "review_items"}
        check_exact_keys(result, expected, "$.meeting_result", errors)
        for field in ("summary_points", "review_items"):
            value = result.get(field)
            if not isinstance(value, list):
                errors.append(f"$.meeting_result.{field}: 배열이어야 함")
                continue
            for i, point in enumerate(value):
                e, t = validate_point(point, f"$.meeting_result.{field}[{i}]", errors, warnings)
                total_emphasis += e
                total_text += t

        actions = result.get("action_items")
        if not isinstance(actions, list):
            errors.append("$.meeting_result.action_items: 배열이어야 함")
            actions = []
        for i, action in enumerate(actions):
            p = f"$.meeting_result.action_items[{i}]"
            if not isinstance(action, dict):
                errors.append(f"{p}: 객체여야 함")
                continue
            check_exact_keys(action, REQUIRED_ACTION, p, errors)
            task = action.get("task")
            if not as_nonempty_string(task):
                errors.append(f"{p}.task: 비어 있지 않은 문자열이어야 함")
                task = ""
            elif len(task) > 800:
                errors.append(f"{p}.task: 800자를 초과함")
            for field in ("owner", "deadline", "status"):
                if not isinstance(action.get(field), str):
                    errors.append(f"{p}.{field}: 문자열이어야 함")
            e, t = validate_emphasis(
                task,
                action.get("emphasis"),
                action.get("important"),
                p,
                errors,
                warnings,
            )
            total_emphasis += e
            total_text += t

    quality = data.get("quality")
    if not isinstance(quality, dict):
        errors.append("$.quality: 객체여야 함")
    else:
        check_exact_keys(quality, REQUIRED_QUALITY, "$.quality", errors)
        for key in sorted(REQUIRED_QUALITY):
            validate_string_array(quality.get(key), f"$.quality.{key}", errors)

    emphasis_ratio = (total_emphasis / total_text) if total_text else 0.0
    if emphasis_ratio > 0.30:
        warnings.append(f"파란색 강조 예상 비율이 {emphasis_ratio:.1%}로 높음; 핵심 구절만 남길 것")

    status = "error" if errors else ("warning" if warnings else "ok")
    output = {
        "status": status,
        "input": str(path),
        "metrics": {
            "text_characters": total_text,
            "emphasis_characters": total_emphasis,
            "emphasis_ratio": round(emphasis_ratio, 4),
        },
        "errors": errors,
        "warnings": warnings,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))

    if errors or (args.strict and warnings):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
