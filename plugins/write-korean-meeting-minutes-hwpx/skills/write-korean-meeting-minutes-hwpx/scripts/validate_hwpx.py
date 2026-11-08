#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from _console import configure_utf8_output

configure_utf8_output()

HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"
HH = "http://www.hancom.co.kr/hwpml/2011/head"
BLUE = "#2F5597"
PLACEHOLDER_RE = re.compile(r"(?:<[^>]+>|\bTODO\b|\bTBD\b|\[작성(?:\s*필요)?\])", re.IGNORECASE)


def qname(namespace: str, local: str) -> str:
    return f"{{{namespace}}}{local}"


def char_style_map(header: ET.Element) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for char_pr in header.iter(qname(HH, "charPr")):
        char_id = char_pr.get("id")
        if char_id is None:
            continue
        result[char_id] = {
            "color": char_pr.get("textColor", "#000000").upper(),
            "bold": char_pr.find(qname(HH, "bold")) is not None,
        }
    return result


def paragraph_text(paragraph: ET.Element) -> str:
    return "".join((t.text or "") for t in paragraph.iter(qname(HP, "t")))


def run_text(run: ET.Element) -> str:
    return "".join((t.text or "") for t in run.iter(qname(HP, "t")))


def expected_strings(data: dict[str, Any]) -> list[str]:
    values: list[str] = []
    title = data.get("document_title")
    if isinstance(title, str) and title.strip():
        values.append(title.strip())
    metadata = data.get("metadata", {})
    for key in ("agenda", "datetime", "responsible_org", "location", "main_agenda"):
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            values.append(value.strip())
    participants = metadata.get("participants")
    if isinstance(participants, str) and participants.strip():
        values.append(participants.strip())
    elif isinstance(participants, list):
        values.extend(str(item).strip() for item in participants if str(item).strip())

    content = data.get("meeting_content", {})
    summary = content.get("summary", {})
    if isinstance(summary, dict) and isinstance(summary.get("text"), str):
        values.append(summary["text"].strip())
    for topic in content.get("topics", []):
        if isinstance(topic, dict):
            if isinstance(topic.get("title"), str):
                values.append(topic["title"].strip())
            for point in topic.get("points", []):
                if isinstance(point, dict) and isinstance(point.get("text"), str):
                    values.append(point["text"].strip())

    result = data.get("meeting_result", {})
    for field in ("summary_points", "review_items"):
        for point in result.get(field, []):
            if isinstance(point, dict) and isinstance(point.get("text"), str):
                values.append(point["text"].strip())
    for action in result.get("action_items", []):
        if isinstance(action, dict) and isinstance(action.get("task"), str):
            values.append(action["task"].strip())
    return [value for value in values if value]


def expected_blue_phrases(data: dict[str, Any]) -> list[str]:
    phrases: list[str] = []

    def add_point(point: Any, primary_key: str = "text") -> None:
        if not isinstance(point, dict):
            return
        emphasis = point.get("emphasis", [])
        if isinstance(emphasis, list) and emphasis:
            phrases.extend(str(item) for item in emphasis if str(item))
        elif point.get("important") and isinstance(point.get(primary_key), str):
            phrases.append(point[primary_key].strip())

    content = data.get("meeting_content", {})
    add_point(content.get("summary"))
    for topic in content.get("topics", []):
        if isinstance(topic, dict):
            for point in topic.get("points", []):
                add_point(point)

    result = data.get("meeting_result", {})
    for field in ("summary_points", "review_items"):
        for point in result.get(field, []):
            add_point(point)
    for action in result.get("action_items", []):
        add_point(action, primary_key="task")
    return [phrase for phrase in phrases if phrase]


def main() -> None:
    parser = argparse.ArgumentParser(description="생성된 HWPX 회의록의 구조와 스타일을 검사합니다.")
    parser.add_argument("input", type=Path, help="검사할 HWPX 경로")
    parser.add_argument("--expect-data", type=Path, help="HWPX 작성에 사용한 minutes.json 경로")
    args = parser.parse_args()

    path = args.input.expanduser().resolve()
    errors: list[str] = []
    warnings: list[str] = []
    metrics: dict[str, Any] = {}

    if not path.is_file():
        print(json.dumps({"status": "error", "errors": ["HWPX 파일을 찾을 수 없음"], "input": str(path)}, ensure_ascii=False, indent=2))
        raise SystemExit(2)

    try:
        with zipfile.ZipFile(path, "r") as zf:
            names = zf.namelist()
            metrics["zip_members"] = len(names)
            if not names or names[0] != "mimetype":
                errors.append("mimetype가 첫 번째 ZIP 멤버가 아님")
            if "mimetype" not in names:
                errors.append("mimetype 파일이 없음")
            else:
                info = zf.getinfo("mimetype")
                if info.compress_type != zipfile.ZIP_STORED:
                    errors.append("mimetype가 압축되어 있음")
                if zf.read("mimetype") != b"application/hwp+zip":
                    errors.append("mimetype 값이 application/hwp+zip이 아님")

            required_xml = [
                "Contents/header.xml",
                "Contents/section0.xml",
                "Contents/content.hpf",
                "META-INF/manifest.xml",
            ]
            parsed: dict[str, ET.Element] = {}
            for name in required_xml:
                if name not in names:
                    errors.append(f"필수 파일 누락: {name}")
                    continue
                try:
                    parsed[name] = ET.fromstring(zf.read(name))
                except ET.ParseError as exc:
                    errors.append(f"XML 파싱 실패 {name}: {exc}")

            preview_text = ""
            if "Preview/PrvText.txt" in names:
                preview_text = zf.read("Preview/PrvText.txt").decode("utf-8", errors="replace")
            else:
                warnings.append("Preview/PrvText.txt가 없음")
    except zipfile.BadZipFile as exc:
        errors.append(f"유효한 ZIP/HWPX가 아님: {exc}")
        parsed = {}
        preview_text = ""

    header = parsed.get("Contents/header.xml")
    section = parsed.get("Contents/section0.xml")
    all_text = ""
    styles: dict[str, dict[str, Any]] = {}
    blue_run_texts: list[str] = []

    if header is not None and section is not None:
        styles = char_style_map(header)
        paragraphs = list(section.iter(qname(HP, "p")))
        all_text = "".join(paragraph_text(p) for p in paragraphs)
        metrics["paragraphs"] = len(paragraphs)
        metrics["text_characters"] = len(all_text)

        if PLACEHOLDER_RE.search(all_text):
            errors.append("문서 본문에 미완성 플레이스홀더가 있음")

        title_paragraph = paragraphs[0] if paragraphs else None
        if title_paragraph is None:
            errors.append("제목 문단을 찾을 수 없음")
        else:
            title_runs = [child for child in list(title_paragraph) if child.tag == qname(HP, "run")]
            if not title_runs:
                errors.append("제목 run을 찾을 수 없음")
            else:
                style_id = title_runs[0].get("charPrIDRef", "")
                if not styles.get(style_id, {}).get("bold", False):
                    errors.append("문서 제목이 bold 스타일이 아님")

        blue_style_ids = {
            style_id
            for style_id, props in styles.items()
            if props.get("color") == BLUE.upper() and props.get("bold")
        }
        for run in section.iter(qname(HP, "run")):
            if run.get("charPrIDRef") in blue_style_ids:
                blue_run_texts.append(run_text(run))
        metrics["blue_style_ids"] = sorted(blue_style_ids)
        metrics["blue_runs"] = len(blue_run_texts)

        heading_texts = {"회의 요지", "2. 주요 논의", "[요약]", "[후속 조치]", "[확인 필요 사항]"}
        for paragraph in paragraphs:
            text = paragraph_text(paragraph).strip()
            if text in heading_texts or re.match(r"^2\.\d+\.\s+", text):
                runs = [child for child in list(paragraph) if child.tag == qname(HP, "run")]
                if runs:
                    style_id = runs[0].get("charPrIDRef", "")
                    if not styles.get(style_id, {}).get("bold", False):
                        errors.append(f"제목/소제목이 bold가 아님: {text}")

    data: dict[str, Any] | None = None
    if args.expect_data:
        data_path = args.expect_data.expanduser().resolve()
        if not data_path.is_file():
            errors.append(f"기대 데이터 파일을 찾을 수 없음: {data_path}")
        else:
            try:
                data = json.loads(data_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                errors.append(f"기대 데이터 JSON 읽기 실패: {exc}")

    if data is not None and all_text:
        for expected in expected_strings(data):
            if expected not in all_text:
                errors.append(f"HWPX 본문에 기대 문자열이 없음: {expected[:120]!r}")

        blue_text = "".join(blue_run_texts)
        expected_blue = expected_blue_phrases(data)
        if expected_blue and not blue_run_texts:
            errors.append("강조가 요청됐지만 #2F5597 bold run이 없음")
        for phrase in expected_blue:
            if phrase not in blue_text:
                errors.append(f"파란색 강조 run에서 기대 구절을 찾지 못함: {phrase!r}")

        agenda = data.get("metadata", {}).get("agenda")
        if isinstance(agenda, str) and agenda.strip() and agenda.strip() not in preview_text:
            warnings.append("텍스트 미리보기에 안건이 없음")

    status = "error" if errors else ("warning" if warnings else "ok")
    print(
        json.dumps(
            {
                "status": status,
                "input": str(path),
                "bytes": path.stat().st_size,
                "metrics": metrics,
                "errors": errors,
                "warnings": warnings,
                "note": "구조/XML/텍스트 및 제목·강조 서식 검증 결과입니다.",
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
