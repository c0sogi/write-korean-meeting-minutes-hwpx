#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from _console import configure_utf8_output

configure_utf8_output()

NS = {
    "hp": "http://www.hancom.co.kr/hwpml/2011/paragraph",
    "hh": "http://www.hancom.co.kr/hwpml/2011/head",
}


def tree_signature(node: ET.Element) -> tuple:
    return (node.tag, tuple(sorted(node.attrib.items())), tuple(tree_signature(child) for child in node))


def read_layout(path: Path) -> tuple:
    with ZipFile(path) as archive:
        section = ET.fromstring(archive.read("Contents/section0.xml"))
        header = ET.fromstring(archive.read("Contents/header.xml"))
    sections = section.findall(".//hp:secPr", NS)
    columns = section.findall(".//hp:ctrl/hp:colPr", NS)
    assert len(sections) == len(columns) == 1, "Section and column settings must survive title replacement"
    margin = sections[0].find("hp:pagePr/hp:margin", NS)
    assert margin is not None
    used = {p.get("paraPrIDRef") for p in section.findall(".//hp:p", NS)}
    breaks = {
        p.get("id"): dict(p.find("hh:breakSetting", NS).attrib)
        for p in header.findall(".//hh:paraPr", NS)
        if p.get("id") in used
    }
    return tree_signature(sections[0]), tree_signature(columns[0]), breaks, dict(margin.attrib)


def assert_layout_preserved(source: Path, output: Path) -> None:
    expected = read_layout(source)
    actual = read_layout(output)
    assert actual[:2] == expected[:2], "Section/page or column settings changed"
    for prop_id, settings in actual[2].items():
        assert settings == expected[2][prop_id], f"Paragraph wrapping changed: {prop_id}"


def make_custom_layout(source: Path, target: Path) -> None:
    with ZipFile(source) as archive:
        with ZipFile(target, "w") as output:
            for entry in archive.infolist():
                data = archive.read(entry.filename)
                if entry.filename == "Contents/section0.xml":
                    section = ET.fromstring(data)
                    margin = section.find(".//hp:pagePr/hp:margin", NS)
                    assert margin is not None
                    margin.set("left", "5102")
                    margin.set("right", "4535")
                    data = ET.tostring(section, encoding="utf-8", xml_declaration=True)
                elif entry.filename == "Contents/header.xml":
                    header = ET.fromstring(data)
                    for rule in header.findall(".//hh:breakSetting", NS):
                        rule.set("breakNonLatinWord", "KEEP_WORD")
                    data = ET.tostring(header, encoding="utf-8", xml_declaration=True)
                output.writestr(entry, data)


def run(command: list[str]) -> dict:
    completed = subprocess.run(
        command,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    result = {
        "command": command,
        "returncode": completed.returncode,
        "stdout": completed.stdout[-6000:],
        "stderr": completed.stderr[-6000:],
    }
    if completed.returncode != 0:
        raise RuntimeError(json.dumps(result, ensure_ascii=False, indent=2))
    return result


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    python = sys.executable
    results: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="meeting_skill_test_") as temp:
        temp_path = Path(temp)
        inspect_output = temp_path / "inspect.json"
        rendered = temp_path / "rendered.hwpx"
        template = root / "assets" / "meeting-minutes-template.hwpx"
        baseline = read_layout(template)
        assert baseline[3]["left"] == "2850" and baseline[3]["right"] == "3008"
        assert all(rule["breakNonLatinWord"] == "BREAK_WORD" and rule["breakLatinWord"] == "KEEP_WORD" for rule in baseline[2].values())
        results.append(
            run([python, str(root / "scripts" / "validate_skill.py"), str(root)])
        )
        results.append(
            run([python, str(root / "scripts" / "validate_minutes.py"), str(root / "assets" / "example-minutes.json")])
        )
        results.append(
            run(
                [
                    python,
                    str(root / "scripts" / "inspect_transcript.py"),
                    str(root / "assets" / "synthetic-transcript.md"),
                    "-o",
                    str(inspect_output),
                    "--require-segments",
                ]
            )
        )
        results.append(
            run(
                [
                    python,
                    str(root / "scripts" / "render_hwpx.py"),
                    "--template",
                    str(root / "assets" / "meeting-minutes-template.hwpx"),
                    "--data",
                    str(root / "assets" / "example-minutes.json"),
                    "--output",
                    str(rendered),
                ]
            )
        )
        results.append(
            run(
                [
                    python,
                    str(root / "scripts" / "validate_hwpx.py"),
                    str(rendered),
                    "--expect-data",
                    str(root / "assets" / "example-minutes.json"),
                ]
            )
        )
        assert_layout_preserved(template, rendered)
        repeated = temp_path / "repeated.hwpx"
        custom_template = temp_path / "custom-template.hwpx"
        custom_output = temp_path / "custom-output.hwpx"
        make_custom_layout(template, custom_template)
        for source, output in [(rendered, repeated), (custom_template, custom_output)]:
            results.append(run([
                python, str(root / "scripts" / "render_hwpx.py"),
                "--template", str(source),
                "--data", str(root / "assets" / "example-minutes.json"),
                "--output", str(output),
            ]))
            assert_layout_preserved(source, output)
            results.append(run([
                python, str(root / "scripts" / "validate_hwpx.py"), str(output),
                "--expect-data", str(root / "assets" / "example-minutes.json"),
            ]))

    print(
        json.dumps(
            {
                "status": "ok",
                "tests": len(results),
                "message": "네트워크를 사용하지 않는 스킬 자체 검사를 통과했습니다.",
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
