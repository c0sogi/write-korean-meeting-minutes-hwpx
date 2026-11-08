#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Iterable

from _console import configure_utf8_output

configure_utf8_output()

MEETDOWN_VERSION = "0.2.1"
PROVIDER_ENV = {
    "clova": ("CLOVA_SPEECH_INVOKE_URL", "CLOVA_SPEECH_SECRET_KEY"),
    "openai": ("OPENAI_API_KEY",),
    "gemini": ("GEMINI_API_KEY",),
}


def emit(payload: dict, *, exit_code: int = 0) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    raise SystemExit(exit_code)


def configured_providers(env: dict[str, str]) -> list[str]:
    result: list[str] = []
    for provider, names in PROVIDER_ENV.items():
        if all(env.get(name, "").strip() for name in names):
            result.append(provider)
    return result


def missing_credentials(provider: str, env: dict[str, str]) -> list[str]:
    return [name for name in PROVIDER_ENV[provider] if not env.get(name, "").strip()]


def redact(text: str, secret_values: Iterable[str]) -> str:
    redacted = text
    for value in sorted({v for v in secret_values if v}, key=len, reverse=True):
        redacted = redacted.replace(value, "<redacted>")
    return redacted


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "환경변수 인증정보와 버전이 고정된 meetdown을 사용해 로컬 음성·영상 파일 하나를 전사합니다. "
            "비밀값은 명령 인자로 받지 않습니다."
        )
    )
    parser.add_argument("input", type=Path, help="입력 음성 또는 영상 파일")
    parser.add_argument("-o", "--output", required=True, type=Path, help="출력 Markdown 경로")
    parser.add_argument(
        "--provider",
        choices=("auto", "clova", "openai", "gemini"),
        default="auto",
        help="음성인식 제공자입니다. auto는 완전히 설정된 제공자가 정확히 하나일 때만 사용합니다.",
    )
    parser.add_argument("--language", default="ko-KR", help="음성인식 언어 코드")
    parser.add_argument(
        "--compress",
        choices=("smallest", "lossless", "none"),
        default="smallest",
        help="업로드용 임시 음성의 압축 방식",
    )
    parser.add_argument("--chunk-duration", help="10m과 같은 분할 길이입니다. 필요한 경우에만 사용합니다.")
    parser.add_argument("--start", help="10m 또는 00:10:00 형식의 시작 지점")
    parser.add_argument("--end", help="45m 또는 00:45:00 형식의 종료 지점")
    parser.add_argument("--model", help="제공자 모델을 지정합니다. CLOVA에서는 사용할 수 없습니다.")
    parser.add_argument("--api-url", help="비밀값이 아닌 API 엔드포인트 또는 기본 URL을 선택적으로 지정합니다.")
    parser.add_argument("--timeout", type=float, default=3600.0, help="음성인식 요청 제한 시간(초)")
    parser.add_argument("--no-diarization", action="store_true", help="화자 분리를 사용하지 않습니다.")
    parser.add_argument("--overwrite", action="store_true", help="기존 출력 파일을 덮어씁니다.")
    parser.add_argument(
        "--meetdown-version",
        default=MEETDOWN_VERSION,
        help="고정할 meetdown 버전입니다. 호환성 검사 후에만 변경합니다.",
    )
    parser.add_argument("--dry-run", action="store_true", help="실행하지 않고 명령과 설정만 출력합니다.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    env = dict(os.environ)
    env.setdefault("PYTHONUTF8", "1")

    input_path = args.input.expanduser().resolve()
    output_path = args.output.expanduser().resolve()

    if not input_path.is_file():
        emit(
            {
                "status": "error",
                "code": "INPUT_NOT_FOUND",
                "message": "입력 음성·영상 파일을 찾을 수 없습니다.",
                "input": str(input_path),
            },
            exit_code=2,
        )

    if input_path.suffix.lower() in {".md", ".txt", ".json", ".hwpx", ".hwp", ".docx", ".pdf"}:
        emit(
            {
                "status": "error",
                "code": "INPUT_NOT_MEDIA",
                "message": "입력 파일이 음성·영상 파일로 보이지 않습니다.",
                "input": str(input_path),
            },
            exit_code=2,
        )

    if output_path.suffix.lower() != ".md":
        emit(
            {
                "status": "error",
                "code": "INVALID_OUTPUT_EXTENSION",
                "message": "출력 파일 확장자는 .md여야 합니다.",
                "output": str(output_path),
            },
            exit_code=2,
        )

    if input_path == output_path:
        emit(
            {
                "status": "error",
                "code": "INPUT_OUTPUT_COLLISION",
                "message": "입력과 출력 경로가 같을 수 없습니다.",
            },
            exit_code=2,
        )

    if output_path.exists() and not args.overwrite:
        emit(
            {
                "status": "error",
                "code": "OUTPUT_EXISTS",
                "message": "출력 파일이 이미 있습니다. 덮어쓰려면 --overwrite를 사용하세요.",
                "output": str(output_path),
            },
            exit_code=2,
        )

    if shutil.which("uvx") is None:
        emit(
            {
                "status": "error",
                "code": "UVX_NOT_FOUND",
                "message": "uvx를 찾을 수 없습니다. 먼저 uv를 설치하세요.",
            },
            exit_code=2,
        )

    warnings: list[str] = []
    provider = args.provider
    available = configured_providers(env)
    if provider == "auto":
        if len(available) == 1:
            provider = available[0]
        elif len(available) == 0:
            if args.dry_run:
                provider = "clova"
                warnings.append("시험 실행: 인증정보가 없어 예시 제공자로 clova를 사용함.")
            else:
                emit(
                    {
                        "status": "error",
                        "code": "NO_PROVIDER_CREDENTIALS",
                        "message": "완전히 설정된 음성인식 제공자가 없습니다.",
                        "required": PROVIDER_ENV,
                    },
                    exit_code=3,
                )
        else:
            emit(
                {
                    "status": "error",
                    "code": "AMBIGUOUS_PROVIDER",
                    "message": "여러 제공자가 설정되어 있습니다. --provider를 명시하세요.",
                    "configured_providers": available,
                },
                exit_code=3,
            )

    missing = missing_credentials(provider, env)
    if missing:
        if args.dry_run:
            warnings.append("시험 실행: 다음 필수 환경변수가 설정되지 않음: " + ", ".join(missing))
        else:
            emit(
                {
                    "status": "error",
                    "code": "MISSING_PROVIDER_CREDENTIALS",
                    "message": "선택한 제공자의 인증 환경변수가 부족합니다.",
                    "provider": provider,
                    "missing": missing,
                },
                exit_code=3,
            )

    if provider == "clova" and args.model:
        emit(
            {
                "status": "error",
                "code": "MODEL_UNSUPPORTED_FOR_CLOVA",
                "message": "CLOVA Speech 모델은 Invoke URL/domain에서 결정되므로 --model을 사용할 수 없습니다.",
            },
            exit_code=2,
        )

    command = [
        "uvx",
        "--from",
        f"meetdown=={args.meetdown_version}",
        "meetdown",
        "transcribe",
        str(input_path),
        "-o",
        str(output_path),
        "--provider",
        provider,
        "--language",
        args.language,
        "--compress",
        args.compress,
        "--timeout",
        str(args.timeout),
    ]

    if args.chunk_duration:
        command.extend(["--chunk-duration", args.chunk_duration])
    if args.start:
        command.extend(["--start", args.start])
    if args.end:
        command.extend(["--end", args.end])
    if args.model:
        command.extend(["--model", args.model])
    if args.api_url:
        command.extend(["--api-url", args.api_url])
    if args.no_diarization:
        command.append("--no-diarization")

    if args.dry_run:
        emit(
            {
                "status": "dry-run",
                "provider": provider,
                "input": str(input_path),
                "output": str(output_path),
                "command": shlex.join(command),
                "warnings": warnings,
            }
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists() and args.overwrite:
        output_path.unlink()

    completed = subprocess.run(
        command,
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )

    secrets = [env.get(name, "") for names in PROVIDER_ENV.values() for name in names]
    stdout = redact(completed.stdout, secrets)
    stderr = redact(completed.stderr, secrets)

    if completed.returncode != 0:
        emit(
            {
                "status": "error",
                "code": "MEETDOWN_FAILED",
                "message": "meetdown 전사 실행이 실패했습니다.",
                "provider": provider,
                "returncode": completed.returncode,
                "stdout": stdout[-6000:],
                "stderr": stderr[-6000:],
                "hints": [
                    "인증 환경변수와 Invoke URL을 확인하세요.",
                    "용량 또는 시간 제한이면 --chunk-duration 10m으로 재시도하세요.",
                    "패키지 저장소 또는 네트워크 접근이 가능한지 확인하세요.",
                ],
            },
            exit_code=completed.returncode or 1,
        )

    if not output_path.is_file() or output_path.stat().st_size == 0:
        emit(
            {
                "status": "error",
                "code": "OUTPUT_NOT_CREATED",
                "message": "전사 명령은 종료됐지만 유효한 Markdown 파일이 생성되지 않았습니다.",
                "stdout": stdout[-3000:],
                "stderr": stderr[-3000:],
            },
            exit_code=4,
        )

    sample = output_path.read_text(encoding="utf-8", errors="replace")[:20000]
    if "<html" in sample.lower() or "<!doctype html" in sample.lower():
        emit(
            {
                "status": "error",
                "code": "HTML_ERROR_SAVED_AS_MARKDOWN",
                "message": "HTML 오류 응답이 Markdown으로 저장된 것으로 보입니다.",
                "output": str(output_path),
            },
            exit_code=4,
        )

    has_full_text = "## Full text" in sample
    has_transcript = "## Transcript" in sample
    if not (has_full_text or has_transcript):
        warnings.append("표준 Full text/Transcript 섹션이 보이지 않습니다. inspect 스크립트로 확인하세요.")

    emit(
        {
            "status": "ok",
            "provider": provider,
            "input": str(input_path),
            "output": str(output_path),
            "bytes": output_path.stat().st_size,
            "has_full_text": has_full_text,
            "has_transcript": has_transcript,
            "warnings": warnings,
            "stdout": stdout[-3000:],
            "stderr": stderr[-3000:],
        }
    )


if __name__ == "__main__":
    main()
