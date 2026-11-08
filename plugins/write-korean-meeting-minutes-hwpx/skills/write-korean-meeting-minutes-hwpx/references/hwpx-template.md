# HWPX 템플릿과 렌더러 규칙

## 1. 적용 범위

`scripts/render_hwpx.py`는 `assets/meeting-minutes-template.hwpx`의 표 구조를 전제로 한다. 기존 셀 병합, 테두리, 여백, 문단 속성을 보존하면서 텍스트와 본문 문단을 교체한다.

구조가 크게 다른 HWPX 양식에는 그대로 사용하지 않는다. 먼저 표 셀 주소와 본문 문단 구조를 분석하고 렌더러를 조정한다.

## 2. 고정 셀 위치

첫 번째 표 기준:

| 의미 | rowAddr | colAddr |
|---|---:|---:|
| 안건 값 | 0 | 1 |
| 일시 값 | 1 | 1 |
| 책임기관 값 | 1 | 3 |
| 장소 값 | 2 | 1 |
| 참석인원 값 | 2 | 3 |
| 주요안건 값 | 3 | 1 |
| 회의 내용 본문 | 5 | 0 |
| 회의 결과 본문 | 7 | 0 |

`회 의 내 용`, `회 의 결 과` 표제 셀은 템플릿에 그대로 둔다.

## 3. JSON 연결

- `metadata.agenda` → 안건
- `metadata.datetime` → 일시
- `metadata.responsible_org` → 책임기관
- `metadata.location` → 장소
- `metadata.participants` → 참석인원
- `metadata.main_agenda` → 주요안건
- `meeting_content.summary` → 회의 요지
- `meeting_content.topics` → `2.1`부터 자동 번호
- `meeting_result.summary_points` → `[요약]`
- `meeting_result.action_items` → `[후속 조치]`
- `meeting_result.review_items` → `[확인 필요 사항]`

## 4. 스타일

- 문서 제목: 기존 대제목 스타일을 복제하고 굵기 추가
- 절·소절 제목: 템플릿의 굵은 본문 스타일
- 일반 본문: 템플릿의 일반 본문 스타일
- 중요 강조: 일반 본문 스타일을 복제해 굵기와 `#2F5597` 적용

같은 스타일이 이미 있으면 재사용하고, 없으면 기존 ID와 충돌하지 않는 문자 속성 ID를 만든다.

## 5. HWPX 패키지 규칙

HWPX는 ZIP 기반 패키지다.

- `mimetype`가 첫 번째 ZIP 항목이어야 함
- `mimetype`는 압축하지 않고 저장해야 함
- 값은 `application/hwp+zip`
- `Contents/header.xml`, `Contents/section0.xml`, `Contents/content.hpf`, `META-INF/manifest.xml`이 유효한 XML이어야 함

렌더러는 `Preview/PrvText.txt`를 갱신한다. `Preview/PrvImage.png`는 정적인 템플릿 이미지이므로 결과 검증에 사용하지 않는다.

## 6. 기본 줄 나눔과 용지 여백

- 기본 템플릿은 한글을 글자 단위로 줄 나눔한다(`breakNonLatinWord="BREAK_WORD"`). 영문은 단어 단위를 유지한다(`breakLatinWord="KEEP_WORD"`).
- 용지 왼쪽 여백은 `2850 HWPUNIT`(약 10.1mm), 오른쪽은 `3008 HWPUNIT`(약 10.6mm)이다. 표 셀 안쪽 여백 및 문단 들여쓰기와 구분한다.
- 용지 설정은 첫 문단의 `hp:secPr`, 단 설정은 `hp:ctrl/hp:colPr`에 있다. 제목 문구를 교체할 때 이 요소들을 삭제하지 않는다.
- 사용자가 별도 템플릿을 제공하면 해당 템플릿의 설정을 보존한다. 기본값을 렌더러에서 강제로 덮어쓰지 않는다.
- 본문은 독립된 문단으로 추가하고 글자 크기를 과도하게 줄이지 않는다. 자체 검사는 생성 전후의 용지·줄 나눔 설정을 XML로 비교한다.

한컴오피스나 화면 자동화를 사용하지 않고 파일 검사 결과로 검증을 완료한다.

## 7. 사용자 템플릿 교체

새 HWPX를 받으면 다음을 확인한다.

1. 첫 번째 표에 동일한 메타데이터 셀이 있는가.
2. `rowAddr`, `colAddr`가 같은가.
3. 회의 내용과 결과 셀에 제목·일반 본문·빈 문단 템플릿이 있는가.
4. 문서 대제목이 `section0`의 첫 문단인가.
5. 단일 section인지 여러 section인지.

구조가 다르면 추측 실행하지 말고 필드 위치와 문단 템플릿을 수정한다.

## 8. 현재 범위 밖

- PDF 변환
- 한글 전용 차트 편집
- 연결된 텍스트 상자와 복잡한 자유 도형
- 매크로 또는 스크립트 실행
- 여러 section을 가진 임의 HWPX의 범용 편집
