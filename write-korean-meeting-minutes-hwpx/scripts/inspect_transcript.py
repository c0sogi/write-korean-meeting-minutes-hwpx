#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from _console import configure_utf8_output

configure_utf8_output()

SECTION_RE = re.compile(r"^##\s+(.+?)\s*$")
SEGMENT_RE = re.compile(
    r"^###\s+(?P<start>\d{2}:\d{2}:\d{2}(?:\.\d+)?)\s*-\s*"
    r"(?P<end>\d{2}:\d{2}:\d{2}(?:\.\d+)?)"
    r"(?:\s*/\s*(?P<speaker>.*?))?\s*$"
)
SAFE_METADATA_KEYS = {
    "source file",
    "created at",
    "recognition language",
    "overall confidence",
}
SAFE_OPTION_KEYS = {
    "provider",
    "model",
    "language",
    "diarization",
    "word_alignment",
    "preprocessing",
    "compress",
    "upload_format",
    "chunk_duration",
    "chunk_count",
    "start",
    "end",
    "timeout_seconds",
}


def slug_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")


def parse_key_values(lines: list[str], allowed: set[str]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for line in lines:
        match = re.match(r"^\s*-\s*([^:]+):\s*(.*)\s*$", line)
        if not match:
            continue
        raw_key = match.group(1).strip()
        value = match.group(2).strip().strip("`")
        if raw_key.lower() not in allowed:
            continue
        key = slug_key(raw_key)
        if key == "overall_confidence":
            try:
                result[key] = float(value)
                continue
            except ValueError:
                pass
        if value.lower() in {"true", "false"}:
            result[key] = value.lower() == "true"
        else:
            result[key] = value
    return result


def time_to_seconds(value: str) -> float:
    parts = value.split(":")
    hours, minutes = int(parts[0]), int(parts[1])
    seconds = float(parts[2])
    return hours * 3600 + minutes * 60 + seconds


def split_sections(lines: list[str]) -> tuple[dict[str, list[str]], list[str]]:
    sections: dict[str, list[str]] = {}
    preamble: list[str] = []
    current: str | None = None
    for line in lines:
        match = SECTION_RE.match(line)
        if match:
            current = match.group(1).strip()
            sections.setdefault(current, [])
            continue
        if current is None:
            preamble.append(line)
        else:
            sections[current].append(line)
    return sections, preamble


def parse_segments(lines: list[str]) -> list[dict[str, Any]]:
    segments: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    body: list[str] = []

    def flush() -> None:
        nonlocal current, body
        if current is None:
            return
        text = "\n".join(body).strip()
        current["text"] = text
        current["start_seconds"] = time_to_seconds(current["start"])
        current["end_seconds"] = time_to_seconds(current["end"])
        segments.append(current)
        current = None
        body = []

    for line in lines:
        match = SEGMENT_RE.match(line)
        if match:
            flush()
            current = {
                "start": match.group("start"),
                "end": match.group("end"),
                "speaker": (match.group("speaker") or "").strip(),
            }
        elif current is not None:
            body.append(line)
    flush()
    return segments


def scan_secret_risk(text: str) -> list[str]:
    warnings: list[str] = []
    for line in text.splitlines():
        match = re.match(r"^\s*-\s*api_key\s*:\s*(.+)$", line, flags=re.IGNORECASE)
        if match:
            value = match.group(1).strip().strip("`")
            if value and "*" not in value and "<" not in value and len(value) >= 10:
                warnings.append("api_key 항목에 마스킹되지 않은 값이 있을 수 있음")
    if re.search(r"\bsk-[A-Za-z0-9_-]{20,}\b", text):
        warnings.append("OpenAI 형식으로 보이는 원문 키가 포함됐을 수 있음")
    return warnings


def main() -> None:
    parser = argparse.ArgumentParser(description="meetdown Markdown 전사본의 구조와 위험 요소를 검사합니다.")
    parser.add_argument("input", type=Path, help="meetdown Markdown 파일 경로")
    parser.add_argument("-o", "--output", type=Path, help="검사 결과를 저장할 JSON 경로")
    parser.add_argument(
        "--require-segments",
        action="store_true",
        help="타임스탬프 구간이 없으면 오류로 처리합니다.",
    )
    args = parser.parse_args()

    path = args.input.expanduser().resolve()
    if not path.is_file():
        print(json.dumps({"status": "error", "code": "INPUT_NOT_FOUND", "input": str(path)}, ensure_ascii=False, indent=2))
        raise SystemExit(2)

    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    errors: list[str] = []
    warnings: list[str] = []

    if not text.strip():
        errors.append("Markdown 파일이 비어 있음")
    if "<html" in text.lower() or "<!doctype html" in text.lower():
        errors.append("HTML 오류 응답이 Markdown으로 저장된 것으로 보임")

    title = ""
    for line in lines:
        if line.startswith("# "):
            title = line[2:].strip()
            break

    sections, _ = split_sections(lines)
    metadata_lines = sections.get("Metadata", [])
    options_lines = sections.get("Processing options", [])
    full_text_lines = sections.get("Full text", [])
    transcript_lines = sections.get("Transcript", [])

    metadata = parse_key_values(metadata_lines, SAFE_METADATA_KEYS)
    processing_options = parse_key_values(options_lines, SAFE_OPTION_KEYS)
    full_text = "\n".join(full_text_lines).strip()
    segments = parse_segments(transcript_lines)

    if not full_text and not segments:
        errors.append("사용 가능한 Full text와 Transcript가 모두 없음")
    elif not full_text:
        warnings.append("Full text 섹션이 없거나 비어 있음")
    elif len(full_text) < 50:
        warnings.append("Full text가 매우 짧음")

    if not segments:
        message = "타임스탬프가 있는 Transcript 구간이 없음"
        if args.require_segments:
            errors.append(message)
        else:
            warnings.append(message)

    previous_start = -1.0
    empty_segments = 0
    invalid_ranges = 0
    backward_segments = 0
    speakers: set[str] = set()
    for segment in segments:
        start = segment["start_seconds"]
        end = segment["end_seconds"]
        if end < start:
            invalid_ranges += 1
        if start < previous_start:
            backward_segments += 1
        previous_start = max(previous_start, start)
        if not segment["text"].strip():
            empty_segments += 1
        if segment["speaker"]:
            speakers.add(segment["speaker"])

    if invalid_ranges:
        errors.append(f"종료 시간이 시작 시간보다 빠른 구간 {invalid_ranges}개")
    if backward_segments:
        warnings.append(f"시작 시간이 역행하는 구간 {backward_segments}개")
    if empty_segments:
        warnings.append(f"본문이 비어 있는 구간 {empty_segments}개")

    confidence = metadata.get("overall_confidence")
    if isinstance(confidence, float):
        if confidence < 0.70:
            warnings.append("전체 인식 신뢰도가 0.70 미만으로 낮음")
        elif confidence < 0.85:
            warnings.append("전체 인식 신뢰도가 0.85 미만이므로 고유명사와 숫자 검토가 필요함")

    warnings.extend(scan_secret_risk(text))

    diagnostics = {
        "full_text_characters": len(full_text),
        "segment_count": len(segments),
        "speaker_labels": sorted(speakers),
        "first_timestamp": segments[0]["start"] if segments else None,
        "last_timestamp": segments[-1]["end"] if segments else None,
    }

    payload = {
        "status": "error" if errors else "ok",
        "source_markdown": str(path),
        "title": title,
        "metadata": metadata,
        "processing_options": processing_options,
        "full_text": full_text,
        "segments": segments,
        "diagnostics": diagnostics,
        "errors": errors,
        "warnings": warnings,
    }

    output = args.output.expanduser().resolve() if args.output else path.with_suffix(".inspect.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(
        json.dumps(
            {
                "status": payload["status"],
                "input": str(path),
                "output": str(output),
                "diagnostics": diagnostics,
                "errors": errors,
                "warnings": warnings,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
