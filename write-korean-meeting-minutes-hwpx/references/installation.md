# 설치 및 사용 안내

## 1. 설치 위치

스킬 폴더 전체를 사용하는 에이전트의 스킬 디렉터리에 복사한다. 설치 위치와 관계없이 아래 명령은 스킬 루트를 현재 디렉터리로 둔 상대경로로 실행한다.

```text
write-korean-meeting-minutes-hwpx/
├── SKILL.md
├── agents/
├── scripts/
├── references/
└── assets/
```

최종 경로의 디렉터리명은 `SKILL.md`의 `name`과 동일해야 한다.

```text
write-korean-meeting-minutes-hwpx/SKILL.md
```

사용하는 에이전트 제품이 별도 스킬 위치를 정해 두었다면 해당 제품의 규칙을 따른다.

## 2. 설치 확인

```bash
cd write-korean-meeting-minutes-hwpx
uv run scripts/validate_skill.py .
```

스킬 루트에서 전체 로컬 검사를 실행하려면 다음 명령을 사용한다.

```bash
uv run scripts/self_test.py
```

## 3. 일반 사용자 요청 예시

전사본이 있는 경우:

```text
첨부한 meetdown 전사 Markdown을 근거로 정식 회의록을 작성하고 HWPX로 만들어줘.
회의 일시는 2026-07-24 14:00~15:00이고 장소는 제1회의실이야.
```

녹음파일만 있는 경우:

```text
이 m4a 녹음을 먼저 전사한 뒤 결정 사항과 후속 조치 중심으로 회의록 HWPX를 만들어줘.
```

기존 HWPX 양식을 수정하는 경우:

```text
첨부 HWPX의 표와 서식을 유지하면서 새 전사본 내용으로 회의록을 교체해줘.
제목과 소제목은 굵게, 중요한 결정과 업무는 파란색으로 표시해줘.
```

## 4. 운영자 준비 사항

음성 전사를 사용할 때는 다음이 필요하다.

- `uv`와 `uvx`
- Python 3.12 이상(`meetdown==0.2.1` 요구사항)
- 인터넷 연결
- CLOVA Speech, OpenAI, Gemini 중 하나의 인증정보
- 외부 음성인식 서비스 사용이 조직 보안 정책에 맞는지 확인

한국어 회의의 기본 제공자로 CLOVA Speech를 사용할 경우 다음 환경변수를 설정한다.

```text
CLOVA_SPEECH_INVOKE_URL
CLOVA_SPEECH_SECRET_KEY
```

비밀값을 채팅, 소스코드, 회의록 파일에 직접 저장하지 않는다.

## 5. 산출물

- 필요한 경우 meetdown 전사 Markdown
- 전사 검사 결과 JSON
- 구조화 회의록 JSON
- 근거 장부 JSON
- 검토 필요 사항 문서
- 최종 HWPX

현재 버전은 PDF 변환을 포함하지 않는다.
