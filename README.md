# write-korean-meeting-minutes-hwpx

한국어 회의 음성·영상 또는 전사 Markdown을 근거로 공식 회의록을 구성하고 HWPX로 생성하는 Codex/Agent Skill입니다.

## 주요 기능

- 기존 전사본 우선 사용 및 `meetdown` 기반 선택적 음성 전사
- 제안, 우려, 결정, 후속 조치와 미결 사항 구분
- 확인되지 않은 일시, 참석자, 담당자와 기한의 추정 방지
- 구조화된 `minutes.json` 검증
- 번들 HWPX 템플릿 렌더링
- HWPX ZIP, XML, 본문과 강조 스타일 검증
- API 인증정보와 문서 메타데이터 노출 방지

## 요구사항

- `uv`와 `uvx`
- Python 3.12 이상
- 음성·영상 처리 시 `ffmpeg`
- 음성 전사 시 인터넷 연결과 CLOVA Speech, OpenAI 또는 Gemini 인증정보

## 설치

저장소 안의 `write-korean-meeting-minutes-hwpx/` 폴더 전체를 사용하는 에이전트의 스킬 디렉터리에 복사합니다. 최종 폴더명과 `SKILL.md`의 `name`은 같아야 합니다.

## 검증

스킬 폴더를 현재 디렉터리로 두고 실행합니다.

```bash
cd write-korean-meeting-minutes-hwpx
uv run scripts/self_test.py
```

자체 테스트는 네트워크나 음성인식 API를 호출하지 않고 전사 Markdown 검사, JSON 검증, HWPX 생성과 구조 검증을 수행합니다.

## 주의사항

- 녹음이나 전사본을 외부 음성인식 서비스에 보내기 전에 조직의 보안·개인정보 정책을 확인하세요.
- HWPX 구조 검증은 한컴오피스에서의 실제 페이지 흐름과 시각 검수를 대체하지 않습니다.
- 번들 템플릿과 구조가 크게 다른 HWPX는 렌더러 조정이 필요합니다.
- 현재 PDF 변환은 지원하지 않습니다.

## 공개 형식 참고

본 스킬은 한컴의 HWP 문서 파일(.hwp) 공개 문서를 참고하여 개발하였습니다.

## 라이선스

MIT License
