#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import json
import shutil
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from xml.etree import ElementTree as ET

from _console import configure_utf8_output

configure_utf8_output()

HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"
HH = "http://www.hancom.co.kr/hwpml/2011/head"
HS = "http://www.hancom.co.kr/hwpml/2011/section"
OPF = "http://www.idpf.org/2007/opf/"
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"
BLUE = "#2F5597"


def qname(namespace: str, local: str) -> str:
    return f"{{{namespace}}}{local}"


def emit(payload: dict[str, Any], *, exit_code: int = 0) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    raise SystemExit(exit_code)


def register_namespaces(path: Path) -> None:
    seen: set[tuple[str, str]] = set()
    for _, item in ET.iterparse(path, events=("start-ns",)):
        prefix, uri = item
        prefix = prefix or ""
        if (prefix, uri) in seen or prefix == "xml":
            continue
        seen.add((prefix, uri))
        try:
            ET.register_namespace(prefix, uri)
        except ValueError:
            # ElementTree reserves some generated prefixes; the URI will still be written.
            pass


def parse_xml(path: Path) -> ET.ElementTree:
    register_namespaces(path)
    return ET.parse(path)


def direct_children(parent: ET.Element, namespace: str, local: str) -> list[ET.Element]:
    return [child for child in list(parent) if child.tag == qname(namespace, local)]


def first_descendant(root: ET.Element, namespace: str, local: str) -> ET.Element:
    target = qname(namespace, local)
    for elem in root.iter(target):
        return elem
    raise RuntimeError(f"필수 XML 요소를 찾을 수 없음: {local}")


def find_cell(root: ET.Element, row: int, col: int) -> ET.Element:
    table = first_descendant(root, HP, "tbl")
    for cell in table.iter(qname(HP, "tc")):
        addr = cell.find(qname(HP, "cellAddr"))
        if addr is None:
            continue
        if addr.get("rowAddr") == str(row) and addr.get("colAddr") == str(col):
            return cell
    raise RuntimeError(f"템플릿 셀을 찾을 수 없음: row={row}, col={col}")


def get_sublist(cell: ET.Element) -> ET.Element:
    sublist = cell.find(qname(HP, "subList"))
    if sublist is None:
        raise RuntimeError("템플릿 셀에 subList가 없음")
    return sublist


def remove_lineseg(paragraph: ET.Element) -> None:
    for child in list(paragraph):
        if child.tag == qname(HP, "linesegarray"):
            paragraph.remove(child)


def replace_runs(paragraph: ET.Element, segments: Iterable[tuple[str, str]]) -> ET.Element:
    for child in list(paragraph):
        if child.tag in {qname(HP, "run"), qname(HP, "linesegarray")}:
            paragraph.remove(child)

    for char_pr_id, text in segments:
        run = ET.Element(qname(HP, "run"), {"charPrIDRef": str(char_pr_id)})
        t = ET.SubElement(run, qname(HP, "t"))
        if text.startswith(" ") or text.endswith(" "):
            t.set(XML_SPACE, "preserve")
        t.text = text
        paragraph.append(run)
    return paragraph


def clone_paragraph(template: ET.Element, segments: Iterable[tuple[str, str]]) -> ET.Element:
    paragraph = copy.deepcopy(template)
    return replace_runs(paragraph, segments)


def paragraph_first_style(paragraph: ET.Element, default: str = "0") -> str:
    for run in direct_children(paragraph, HP, "run"):
        return run.get("charPrIDRef", default)
    return default


def char_properties_root(header_root: ET.Element) -> ET.Element:
    return first_descendant(header_root, HH, "charProperties")


def char_pr_by_id(header_root: ET.Element, char_id: str) -> ET.Element:
    props = char_properties_root(header_root)
    for elem in direct_children(props, HH, "charPr"):
        if elem.get("id") == str(char_id):
            return elem
    raise RuntimeError(f"문자 속성을 찾을 수 없음: {char_id}")


def has_bold(char_pr: ET.Element) -> bool:
    return char_pr.find(qname(HH, "bold")) is not None


def font_signature(char_pr: ET.Element) -> tuple[tuple[str, str], ...]:
    font_ref = char_pr.find(qname(HH, "fontRef"))
    return tuple(sorted(font_ref.attrib.items())) if font_ref is not None else ()


def ensure_bold_style(
    header_root: ET.Element,
    base_id: str,
    *,
    color: str | None = None,
) -> str:
    props = char_properties_root(header_root)
    base = char_pr_by_id(header_root, base_id)
    desired_color = color or base.get("textColor", "#000000")
    desired_height = base.get("height")
    desired_font = font_signature(base)

    for existing in direct_children(props, HH, "charPr"):
        if (
            existing.get("textColor", "#000000").upper() == desired_color.upper()
            and existing.get("height") == desired_height
            and font_signature(existing) == desired_font
            and has_bold(existing)
        ):
            return existing.get("id", base_id)

    ids = [int(elem.get("id", "0")) for elem in direct_children(props, HH, "charPr")]
    new_id = str(max(ids, default=-1) + 1)
    new_style = copy.deepcopy(base)
    new_style.set("id", new_id)
    new_style.set("textColor", desired_color)
    if not has_bold(new_style):
        new_style.append(ET.Element(qname(HH, "bold")))
    props.append(new_style)
    props.set("itemCnt", str(len(direct_children(props, HH, "charPr"))))
    return new_id


def set_cell_value(root: ET.Element, row: int, col: int, text: str, char_pr: str = "0") -> None:
    cell = find_cell(root, row, col)
    sublist = get_sublist(cell)
    paragraphs = direct_children(sublist, HP, "p")
    if not paragraphs:
        raise RuntimeError(f"템플릿 셀에 문단이 없음: row={row}, col={col}")
    replace_runs(paragraphs[0], [(char_pr, text)])
    for extra in paragraphs[1:]:
        sublist.remove(extra)


def normalized_text(value: Any, *, fallback: str = "확인 필요") -> str:
    if isinstance(value, list):
        value = ", ".join(str(item).strip() for item in value if str(item).strip())
    if isinstance(value, str) and value.strip():
        return value.strip()
    return fallback


def point_segments(point: dict[str, Any], normal_style: str, blue_style: str, *, prefix: str = "") -> list[tuple[str, str]]:
    core = str(point.get("text", "")).strip()
    full_text = prefix + core
    emphasis = [str(item) for item in point.get("emphasis", []) if str(item)]
    if bool(point.get("important")) and not emphasis and core:
        emphasis = [core]

    ranges: list[tuple[int, int]] = []
    for phrase in emphasis:
        start = full_text.find(phrase)
        if start < 0:
            continue
        ranges.append((start, start + len(phrase)))
    ranges.sort()

    merged: list[tuple[int, int]] = []
    for start, end in ranges:
        if merged and start < merged[-1][1]:
            continue
        merged.append((start, end))

    if not merged:
        return [(normal_style, full_text)]

    segments: list[tuple[str, str]] = []
    cursor = 0
    for start, end in merged:
        if start > cursor:
            segments.append((normal_style, full_text[cursor:start]))
        segments.append((blue_style, full_text[start:end]))
        cursor = end
    if cursor < len(full_text):
        segments.append((normal_style, full_text[cursor:]))
    return segments


def action_as_point(action: dict[str, Any]) -> dict[str, Any]:
    task = str(action.get("task", "")).strip()
    details: list[str] = []
    owner = str(action.get("owner", "")).strip()
    deadline = str(action.get("deadline", "")).strip()
    status = str(action.get("status", "")).strip()
    if owner:
        details.append(f"담당: {owner}")
    if deadline:
        details.append(f"기한: {deadline}")
    if status:
        details.append(f"상태: {status}")
    suffix = f" ({' / '.join(details)})" if details else ""
    return {
        "text": task + suffix,
        "emphasis": list(action.get("emphasis", [])),
        "important": bool(action.get("important")),
    }


def build_preview_text(data: dict[str, Any]) -> str:
    metadata = data["metadata"]
    content = data["meeting_content"]
    result = data["meeting_result"]
    lines = [
        normalized_text(data.get("document_title"), fallback="회 의 록"),
        "",
        f"안건: {normalized_text(metadata.get('agenda'))}",
        f"일시: {normalized_text(metadata.get('datetime'))}",
        f"책임기관: {normalized_text(metadata.get('responsible_org'))}",
        f"장소: {normalized_text(metadata.get('location'))}",
        f"참석인원: {normalized_text(metadata.get('participants'))}",
        f"주요안건: {normalized_text(metadata.get('main_agenda'))}",
        "",
        "회의 요지",
        content["summary"]["text"],
        "",
        "2. 주요 논의",
    ]
    for index, topic in enumerate(content["topics"], start=1):
        lines.append(f"2.{index}. {topic['title']}")
        lines.extend(f"- {point['text']}" for point in topic["points"])
    lines.extend(["", "[요약]"])
    lines.extend(f"- {point['text']}" for point in result["summary_points"])
    lines.extend(["", "[후속 조치]"])
    lines.extend(f"- {action_as_point(action)['text']}" for action in result["action_items"])
    if result["review_items"]:
        lines.extend(["", "[확인 필요 사항]"])
        lines.extend(f"- {point['text']}" for point in result["review_items"])
    return "\n".join(lines).rstrip() + "\n"


def update_content_metadata(path: Path, title: str, agenda: str) -> None:
    tree = parse_xml(path)
    root = tree.getroot()
    title_elem = root.find(f".//{qname(OPF, 'title')}")
    if title_elem is not None:
        title_elem.text = title
    for meta in root.iter(qname(OPF, "meta")):
        name = meta.get("name")
        if name == "creator":
            meta.set("content", "write-korean-meeting-minutes-hwpx")
            meta.text = "write-korean-meeting-minutes-hwpx"
        elif name == "subject":
            meta.set("content", agenda)
        elif name == "lastsaveby":
            meta.set("content", "write-korean-meeting-minutes-hwpx")
            meta.text = "write-korean-meeting-minutes-hwpx"
        elif name == "ModifiedDate":
            timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
            meta.set("content", timestamp)
            meta.text = timestamp
    tree.write(path, encoding="utf-8", xml_declaration=True)


def build_document(workdir: Path, data: dict[str, Any]) -> dict[str, str]:
    header_path = workdir / "Contents" / "header.xml"
    section_path = workdir / "Contents" / "section0.xml"
    content_path = workdir / "Contents" / "content.hpf"

    header_tree = parse_xml(header_path)
    section_tree = parse_xml(section_path)
    header_root = header_tree.getroot()
    section_root = section_tree.getroot()

    title_paragraph = next((child for child in list(section_root) if child.tag == qname(HP, "p")), None)
    if title_paragraph is None:
        raise RuntimeError("문서 대제목 문단을 찾을 수 없음")
    title_run = next(iter(direct_children(title_paragraph, HP, "run")), None)
    if title_run is None:
        raise RuntimeError("문서 대제목 텍스트 구간을 찾을 수 없음")
    title_base_style = title_run.get("charPrIDRef", "5")
    title_bold_style = ensure_bold_style(header_root, title_base_style)

    content_cell = find_cell(section_root, 5, 0)
    content_sublist = get_sublist(content_cell)
    content_paragraphs = direct_children(content_sublist, HP, "p")
    if len(content_paragraphs) < 4:
        raise RuntimeError("회의 내용 셀에는 최소 4개의 문단 템플릿이 필요함")
    heading_template = copy.deepcopy(content_paragraphs[0])
    normal_template = copy.deepcopy(content_paragraphs[1])
    blank_template = copy.deepcopy(content_paragraphs[2])
    subheading_template = copy.deepcopy(content_paragraphs[3])

    result_cell = find_cell(section_root, 7, 0)
    result_sublist = get_sublist(result_cell)
    result_paragraphs = direct_children(result_sublist, HP, "p")
    if not result_paragraphs:
        raise RuntimeError("회의 결과 셀에 문단 템플릿이 없음")
    result_heading_template = copy.deepcopy(result_paragraphs[0])

    body_style = paragraph_first_style(normal_template, "0")
    heading_style = paragraph_first_style(heading_template, "8")
    blue_style = ensure_bold_style(header_root, body_style, color=BLUE)

    title = normalized_text(data.get("document_title"), fallback="회 의 록")
    replace_runs(title_paragraph, [(title_bold_style, title)])
    remove_lineseg(title_paragraph)

    metadata = data["metadata"]
    set_cell_value(section_root, 0, 1, normalized_text(metadata.get("agenda")), body_style)
    set_cell_value(section_root, 1, 1, normalized_text(metadata.get("datetime")), body_style)
    set_cell_value(section_root, 1, 3, normalized_text(metadata.get("responsible_org")), body_style)
    set_cell_value(section_root, 2, 1, normalized_text(metadata.get("location")), body_style)
    set_cell_value(section_root, 2, 3, normalized_text(metadata.get("participants")), body_style)
    set_cell_value(section_root, 3, 1, normalized_text(metadata.get("main_agenda")), body_style)

    for paragraph in direct_children(content_sublist, HP, "p"):
        content_sublist.remove(paragraph)

    content = data["meeting_content"]
    content_sublist.append(clone_paragraph(heading_template, [(heading_style, "회의 요지")]))
    content_sublist.append(
        clone_paragraph(
            normal_template,
            point_segments(content["summary"], body_style, blue_style),
        )
    )
    content_sublist.append(clone_paragraph(blank_template, [(body_style, "")]))
    content_sublist.append(clone_paragraph(subheading_template, [(heading_style, "2. 주요 논의")]))

    for index, topic in enumerate(content["topics"], start=1):
        content_sublist.append(
            clone_paragraph(
                subheading_template,
                [(heading_style, f"2.{index}. {str(topic['title']).strip()}")],
            )
        )
        for point in topic["points"]:
            content_sublist.append(
                clone_paragraph(
                    normal_template,
                    point_segments(point, body_style, blue_style, prefix="- "),
                )
            )
        if index != len(content["topics"]):
            content_sublist.append(clone_paragraph(blank_template, [(body_style, "")]))

    content_sublist.append(clone_paragraph(blank_template, [(body_style, "")]))

    for paragraph in direct_children(result_sublist, HP, "p"):
        result_sublist.remove(paragraph)

    result = data["meeting_result"]
    result_sublist.append(clone_paragraph(result_heading_template, [(heading_style, "[요약]")]))
    if result["summary_points"]:
        for point in result["summary_points"]:
            result_sublist.append(
                clone_paragraph(
                    normal_template,
                    point_segments(point, body_style, blue_style, prefix="- "),
                )
            )
    else:
        result_sublist.append(clone_paragraph(blank_template, [(body_style, "")]))

    result_sublist.append(clone_paragraph(blank_template, [(body_style, "")]))
    result_sublist.append(clone_paragraph(result_heading_template, [(heading_style, "[후속 조치]")]))
    if result["action_items"]:
        for action in result["action_items"]:
            point = action_as_point(action)
            result_sublist.append(
                clone_paragraph(
                    normal_template,
                    point_segments(point, body_style, blue_style, prefix="- "),
                )
            )
    else:
        result_sublist.append(clone_paragraph(blank_template, [(body_style, "")]))

    if result["review_items"]:
        result_sublist.append(clone_paragraph(blank_template, [(body_style, "")]))
        result_sublist.append(
            clone_paragraph(result_heading_template, [(heading_style, "[확인 필요 사항]")])
        )
        for point in result["review_items"]:
            result_sublist.append(
                clone_paragraph(
                    normal_template,
                    point_segments(point, body_style, blue_style, prefix="- "),
                )
            )

    result_sublist.append(clone_paragraph(blank_template, [(body_style, "")]))

    header_tree.write(header_path, encoding="utf-8", xml_declaration=True)
    section_tree.write(section_path, encoding="utf-8", xml_declaration=True)
    update_content_metadata(content_path, title, normalized_text(metadata.get("agenda")))

    preview_path = workdir / "Preview" / "PrvText.txt"
    preview_path.parent.mkdir(parents=True, exist_ok=True)
    preview_path.write_text(build_preview_text(data), encoding="utf-8")

    return {
        "title_style": title_bold_style,
        "body_style": body_style,
        "heading_style": heading_style,
        "blue_style": blue_style,
    }


def repack_hwpx(workdir: Path, output: Path) -> None:
    mimetype = workdir / "mimetype"
    if not mimetype.is_file():
        raise RuntimeError("템플릿에 mimetype 파일이 없음")
    output.parent.mkdir(parents=True, exist_ok=True)
    temp_output = output.with_suffix(output.suffix + ".tmp")
    if temp_output.exists():
        temp_output.unlink()
    with zipfile.ZipFile(temp_output, "w") as zf:
        zf.write(mimetype, "mimetype", compress_type=zipfile.ZIP_STORED)
        for path in sorted(workdir.rglob("*")):
            if not path.is_file() or path == mimetype:
                continue
            zf.write(path, path.relative_to(workdir).as_posix(), compress_type=zipfile.ZIP_DEFLATED)
    temp_output.replace(output)


def quick_validate(output: Path) -> None:
    with zipfile.ZipFile(output, "r") as zf:
        names = zf.namelist()
        if not names or names[0] != "mimetype":
            raise RuntimeError("mimetype가 첫 번째 ZIP 항목이 아님")
        info = zf.getinfo("mimetype")
        if info.compress_type != zipfile.ZIP_STORED:
            raise RuntimeError("mimetype는 압축하지 않고 저장해야 함")
        if zf.read("mimetype") != b"application/hwp+zip":
            raise RuntimeError("HWPX mimetype 값이 올바르지 않음")
        for name in (
            "Contents/header.xml",
            "Contents/section0.xml",
            "Contents/content.hpf",
            "META-INF/manifest.xml",
        ):
            ET.fromstring(zf.read(name))


def main() -> None:
    parser = argparse.ArgumentParser(description="구조화된 한국어 회의록 데이터를 HWPX로 작성합니다.")
    parser.add_argument("--template", required=True, type=Path, help="호환되는 HWPX 템플릿 경로")
    parser.add_argument("--data", required=True, type=Path, help="검증을 마친 minutes.json 경로")
    parser.add_argument("--output", required=True, type=Path, help="출력 HWPX 경로")
    parser.add_argument("--overwrite", action="store_true", help="기존 출력 파일을 덮어씁니다.")
    args = parser.parse_args()

    template = args.template.expanduser().resolve()
    data_path = args.data.expanduser().resolve()
    output = args.output.expanduser().resolve()

    if not template.is_file():
        emit({"status": "error", "code": "TEMPLATE_NOT_FOUND", "message": "HWPX 템플릿을 찾을 수 없습니다.", "template": str(template)}, exit_code=2)
    if not data_path.is_file():
        emit({"status": "error", "code": "DATA_NOT_FOUND", "message": "회의록 데이터 JSON을 찾을 수 없습니다.", "data": str(data_path)}, exit_code=2)
    if output.suffix.lower() != ".hwpx":
        emit({"status": "error", "code": "INVALID_OUTPUT_EXTENSION", "message": "출력 확장자는 .hwpx여야 합니다."}, exit_code=2)
    if output.exists() and not args.overwrite:
        emit({"status": "error", "code": "OUTPUT_EXISTS", "message": "덮어쓰려면 --overwrite를 사용하세요.", "output": str(output)}, exit_code=2)
    if output == template:
        emit({"status": "error", "code": "TEMPLATE_OUTPUT_COLLISION", "message": "템플릿을 직접 덮어쓸 수 없습니다."}, exit_code=2)

    try:
        data = json.loads(data_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        emit({"status": "error", "code": "INVALID_JSON", "message": str(exc)}, exit_code=2)

    required = {"document_title", "metadata", "meeting_content", "meeting_result", "quality"}
    if not isinstance(data, dict) or not required.issubset(data):
        emit(
            {
                "status": "error",
                "code": "INVALID_DATA_SHAPE",
                "message": "먼저 scripts/validate_minutes.py로 minutes.json을 검증하세요.",
            },
            exit_code=2,
        )

    try:
        with tempfile.TemporaryDirectory(prefix="minutes_hwpx_") as temp_dir:
            workdir = Path(temp_dir)
            with zipfile.ZipFile(template, "r") as zf:
                zf.extractall(workdir)
            styles = build_document(workdir, data)
            repack_hwpx(workdir, output)
        quick_validate(output)
    except (OSError, RuntimeError, zipfile.BadZipFile, ET.ParseError, KeyError, TypeError) as exc:
        if output.exists():
            output.unlink(missing_ok=True)
        emit(
            {
                "status": "error",
                "code": "HWPX_RENDER_FAILED",
                "message": str(exc),
                "template": str(template),
                "data": str(data_path),
            },
            exit_code=1,
        )

    emit(
        {
            "status": "ok",
            "template": str(template),
            "data": str(data_path),
            "output": str(output),
            "bytes": output.stat().st_size,
            "blue": BLUE,
            "styles": styles,
            "note": "XML과 HWPX 패키지 검사를 통과했습니다. 실제 페이지 흐름은 한컴오피스에서 확인해야 합니다.",
        }
    )


if __name__ == "__main__":
    main()
