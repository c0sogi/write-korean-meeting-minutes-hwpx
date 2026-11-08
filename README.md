# write-korean-meeting-minutes-hwpx

한국어 회의 음성·영상 또는 전사 Markdown을 근거로 공식 회의록을 구성하고 HWPX로 생성하는 Claude Code/Codex 플러그인이자 Agent Skill입니다.

## 주요 기능

- 기존 전사본 우선 사용 및 `meetdown` 기반 선택적 음성 전사
- 제안, 우려, 결정, 후속 조치와 미결 사항 구분
- 확인되지 않은 일시, 참석자, 담당자와 기한의 추정 방지
- 구조화된 `minutes.json` 검증
- 번들 HWPX 템플릿 렌더링
- 한글 글자 단위 줄 나눔과 좌우 용지 여백 기본 적용
- 제목 교체 및 반복 생성 시 템플릿의 용지·단 설정 보존
- HWPX ZIP, XML, 본문과 강조 스타일 검증
- API 인증정보와 문서 메타데이터 노출 방지

## 요구사항

- `uv`와 `uvx`
- Python 3.12 이상
- 음성·영상 처리 시 `ffmpeg`
- 음성 전사 시 인터넷 연결과 CLOVA Speech, OpenAI 또는 Gemini 인증정보

## 설치

Claude Code:

```bash
claude plugin marketplace add c0sogi/write-korean-meeting-minutes-hwpx
claude plugin install write-korean-meeting-minutes-hwpx@c0sogi-hwpx
```

Codex:

```bash
codex plugin marketplace add c0sogi/write-korean-meeting-minutes-hwpx
codex plugin add write-korean-meeting-minutes-hwpx@c0sogi-hwpx
```

설치 후 새 세션을 시작하면 스킬을 사용할 수 있습니다.

다른 에이전트에서는 저장소 안의 `plugins/write-korean-meeting-minutes-hwpx/skills/write-korean-meeting-minutes-hwpx/` 폴더 전체를 사용하는 에이전트의 스킬 디렉터리에 복사합니다. 최종 폴더명과 `SKILL.md`의 `name`은 같아야 합니다.

## 검증

스킬 폴더를 현재 디렉터리로 두고 실행합니다.

```bash
cd plugins/write-korean-meeting-minutes-hwpx/skills/write-korean-meeting-minutes-hwpx
uv run scripts/self_test.py
```

자체 테스트는 네트워크나 음성인식 API를 호출하지 않고 전사 Markdown 검사, JSON 검증, HWPX 생성과 구조 검증을 수행합니다. 반복 생성과 별도 템플릿 사용 시에도 여백 및 줄 나눔 설정이 유지되는지 확인합니다. 문서 작성·검증에 한컴오피스 실행이나 화면 자동화를 사용하지 않습니다.

기본 템플릿은 한글을 글자 단위, 영문을 단어 단위로 줄 나눔하며, 용지 여백은 왼쪽 약 10.1mm·오른쪽 약 10.6mm입니다. 별도 템플릿을 제공하면 해당 템플릿의 설정을 유지합니다.

## 배포

새 버전을 배포할 때는 `plugins/write-korean-meeting-minutes-hwpx/` 아래 `.claude-plugin/plugin.json`과 `.codex-plugin/plugin.json`의 `version`을 함께 올립니다. 값을 그대로 두면 Claude Code 사용자에게 업데이트가 전달되지 않습니다.

## 주의사항

- 녹음이나 전사본을 외부 음성인식 서비스에 보내기 전에 조직의 보안·개인정보 정책을 확인하세요.
- 번들 템플릿과 구조가 크게 다른 HWPX는 렌더러 조정이 필요합니다.
- 현재 PDF 변환은 지원하지 않습니다.

## 공개 형식 참고

본 스킬은 한컴의 HWP 문서 파일(.hwp) 공개 문서를 참고하여 개발하였습니다.

## 라이선스

MIT License
