# meetdown 전사 사용법

전사본이 없고 녹음·영상만 있을 때 읽는다. 일반 사용자에게는 “파일 업로드 → 전사 → 회의록 생성”만 안내하고, 설치·인증·오류 처리는 운영자나 실행 권한이 있는 에이전트가 담당한다.

## 1. meetdown의 역할

`meetdown`은 로컬 음성·영상 파일을 음성인식 서비스로 보내고 결과를 Markdown으로 저장하는 Python 명령줄 도구다. 이 스킬은 PyPI의 `meetdown==0.2.1`을 기준으로 고정한다.

생성되는 Markdown에는 보통 다음이 포함된다.

```markdown
# 회의 파일명

## Metadata

## Processing options

## Full text

## Transcript
```

- `Full text`: 전체 문맥 파악용 전사문
- `Transcript`: 타임스탬프와 화자별 근거 확인용 발언
- `Metadata`: 원본 파일과 전사 생성 정보
- `Processing options`: 제공자, 언어, 압축, 분할 처리 정보

meetdown은 회의 요약·결정·후속 조치를 작성하지 않는다. 전사 이후의 회의록 작성은 이 스킬이 수행한다.

## 2. 일반 사용자가 할 일

1. 회의 녹음 또는 영상 파일을 업로드한다.
2. 알고 있는 회의 일시, 장소, 참석자, 화자 이름을 함께 제공한다.
3. 시스템이 음성을 전사한다.
4. 전사본을 근거로 회의록을 작성한다.
5. HWPX 파일을 받는다.

일반적으로 `m4a`, `mp3`, `wav`, `aac`, `flac`, `mp4`, `mov`, `mkv` 등을 시도할 수 있다. 실제 성공 여부는 파일 손상 여부, 코덱, ffmpeg와 음성인식 제공자의 지원 범위에 따라 달라진다.

## 3. uv 설치 확인

```bash
uv --version
```

Windows PowerShell 설치 예시:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

macOS 또는 Linux 설치 예시:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

설치 후 터미널을 다시 열고 `uv --version`을 확인한다. 조직에서 승인한 설치 방법과 패키지 저장소가 있으면 그 정책을 우선한다.

## 4. 음성인식 제공자 설정

### CLOVA Speech

한국어 조직 회의의 기본값으로 권장한다. NAVER Cloud Platform에서 발급한 Invoke URL과 Secret Key를 환경변수로 저장한다.

PowerShell:

```powershell
$env:CLOVA_SPEECH_INVOKE_URL = "<Invoke URL>"
$env:CLOVA_SPEECH_SECRET_KEY = "<Secret Key>"
```

bash 또는 zsh:

```bash
export CLOVA_SPEECH_INVOKE_URL="<Invoke URL>"
export CLOVA_SPEECH_SECRET_KEY="<Secret Key>"
```

### OpenAI

```text
OPENAI_API_KEY
```

### Gemini

```text
GEMINI_API_KEY
```

### 보안 원칙

- API 키를 채팅이나 회의록에 붙여 넣지 않는다.
- 명령줄의 `--api-key`는 셸 기록에 남을 수 있으므로 사용하지 않는다.
- 클라우드 비밀값 저장소, CI Secret, Docker Secret 등 조직의 관리 방식을 사용한다.
- 녹음이 외부 서비스로 전송될 수 있으므로 민감 회의는 보안·개인정보 정책을 먼저 확인한다.

## 5. 준비 상태 확인

공식 CLI 확인:

```bash
uvx --from "meetdown==0.2.1" meetdown --help
uvx --from "meetdown==0.2.1" meetdown defaults
uvx --from "meetdown==0.2.1" meetdown quickstart
uvx --from "meetdown==0.2.1" meetdown transcribe --help
```

이 스킬에서는 오류 정리와 비밀값 보호를 위해 래퍼를 우선 사용한다.

```bash
uv run scripts/transcribe.py --help
```

## 6. 가장 간단한 한국어 전사

```bash
uv run scripts/transcribe.py "meeting.m4a" \
  -o "meeting.md" \
  --provider clova \
  --language ko-KR
```

Windows PowerShell 한 줄 예시:

```powershell
uv run scripts/transcribe.py "C:\회의자료\회의.m4a" -o "C:\회의자료\회의.md" --provider clova --language ko-KR
```

경로에 공백이나 한글이 있으면 따옴표로 감싼다.

래퍼 없이 공식 CLI를 직접 실행할 경우:

```bash
uvx --from "meetdown==0.2.1" meetdown transcribe \
  "meeting.m4a" \
  -o "meeting.md" \
  --provider clova \
  --language ko-KR \
  --compress smallest
```

## 7. 제공자 자동 선택

```bash
uv run scripts/transcribe.py "meeting.m4a" -o "meeting.md" --provider auto
```

- 완전히 설정된 제공자가 하나면 해당 제공자를 사용한다.
- 둘 이상이면 `--provider clova`, `--provider openai`, `--provider gemini` 중 하나를 명시한다.
- 하나도 없으면 전사를 시작하지 않고 필요한 환경변수를 안내한다.

## 8. 긴 녹음 처리

단일 업로드가 용량 또는 처리 시간 제한으로 실패했을 때만 10분 단위로 나눈다.

```bash
uv run scripts/transcribe.py "long-meeting.m4a" \
  -o "long-meeting.md" \
  --provider clova \
  --language ko-KR \
  --chunk-duration 10m
```

meetdown은 ffmpeg로 음성을 나누고, 각 구간을 전사한 뒤 타임스탬프를 원본 시간축에 맞춰 하나의 Markdown으로 합친다. 모든 파일을 습관적으로 분할하지 않는다.

## 9. 압축 선택

기본값:

```text
--compress smallest
```

일반 회의에는 기본값을 사용한다. 원본을 덮어쓰지 않고 업로드용 음성 사본을 만든다.

음질 저하가 전사 오류의 원인으로 보일 때만 다음으로 재시도한다.

```text
--compress lossless
```

압축하지 않으려면 다음을 사용한다.

```text
--compress none
```

무손실 또는 무압축은 전송량과 처리 시간이 커질 수 있다.

## 10. 일부 구간만 전사

10분부터 45분까지만 처리하는 예시:

```bash
uv run scripts/transcribe.py "meeting.mp4" \
  -o "meeting-range.md" \
  --provider clova \
  --language ko-KR \
  --start 10m \
  --end 45m
```

`00:10:00`, `00:45:00` 형식도 사용할 수 있다. 타임스탬프는 잘라낸 구간의 0분이 아니라 원본 미디어 시간축을 유지한다.

## 11. 화자 분리

회의록 목적이면 화자 분리를 기본으로 유지한다.

```markdown
### 00:01:20 - 00:01:30 / A

회의 일정부터 정리하겠습니다.
```

`A`, `B`, `[[SPEAKER_1]]`은 실명이 아니다. 사용자에게 받은 화자 매핑이 있을 때만 실제 이름으로 바꾼다.

1인 녹음이거나 제공자가 지원하지 않거나 사용자가 명시적으로 요청한 경우에만 다음 옵션을 사용한다.

```text
--no-diarization
```

## 12. 출력 검증

```bash
uv run scripts/inspect_transcript.py "meeting.md" -o "meeting.inspect.json"
```

확인 항목:

- 파일이 존재하고 비어 있지 않음
- `Full text` 또는 사용할 수 있는 타임스탬프 구간이 있음
- 시간 구간이 정상적으로 증가함
- HTML 오류 응답이 Markdown으로 저장되지 않음
- 원문 API 키가 기록되지 않음
- 낮은 인식 신뢰도가 경고로 표시됨

`Full text`는 전체 맥락을 파악하는 데 사용하고, `Transcript`는 결정과 후속 조치의 시간·화자 근거를 확인하는 데 우선 사용한다.

## 13. 흔한 오류

### uv 또는 meetdown을 실행할 수 없음

- `uv --version`을 확인한다.
- 조직 네트워크가 PyPI 접근을 허용하는지 확인한다.
- 버전 고정 실행이 차단되어 있지 않은지 확인한다.

### 인증정보 누락

- CLOVA: Invoke URL과 Secret Key가 모두 필요하다.
- OpenAI: `OPENAI_API_KEY`가 필요하다.
- Gemini: `GEMINI_API_KEY`가 필요하다.
- 여러 제공자가 설정되어 있으면 `--provider`를 명시한다.

### 파일을 찾을 수 없음

- 실제 로컬 경로를 확인한다.
- 경로를 따옴표로 감싼다.
- 첨부파일 참조만 있고 로컬 파일로 복사되지 않은 상태인지 확인한다.

### 지원되지 않거나 손상된 미디어

- 파일이 정상 재생되는지 확인한다.
- ffmpeg가 코덱을 읽을 수 있는지 확인한다.
- 필요하면 조직에서 승인한 도구로 WAV 또는 M4A 사본을 만들어 재시도한다.

### 용량 또는 시간 제한

- `--chunk-duration 10m`으로 재시도한다.
- 불필요한 앞뒤 구간이 명확하면 사용자 요구 범위 안에서 `--start`, `--end`를 사용한다.

### 전사 품질이 낮음

- 원본 잡음과 음량을 확인한다.
- `--compress lossless`로 재시도한다.
- 한국어 회의는 `--language ko-KR`을 명시한다.
- 인명·기관명·기술 용어 목록을 회의록 작성 단계에 제공한다.
- 불확실한 표기는 임의로 고치지 않고 `표기 확인 필요`로 남긴다.

## 14. 운영 흐름

```text
녹음 업로드
→ 입력 파일·인증정보 점검
→ meetdown 전사
→ Markdown 구조 검사
→ 근거 장부 작성
→ 회의록 JSON 작성·검증
→ HWPX 생성·검증
```

비밀값, ffmpeg, 분할 처리 같은 구현 세부사항은 일반 사용자 화면에 불필요하게 노출하지 않는다.
