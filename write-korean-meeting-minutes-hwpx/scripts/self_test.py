#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from _console import configure_utf8_output

configure_utf8_output()


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
