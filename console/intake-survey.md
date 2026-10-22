# 사전 설문과 고객 로컬 프로필
이름·이메일·전화번호·학생 자료는 이 설문에 받지 않습니다. 연락·계약 정보는 기존 고객관리 절차에서 별도 처리합니다. 학생 폴더 경로는 고객이 자기 PC의 프로필에만 직접 적습니다. 프로필 원본은 판매자 AI에 전달하지 않습니다.

| 질문 | 답 형식 | 프로필 대응 |
|---|---|---|
| 오늘 끝내고 싶은 업무는 무엇인가요? | A 상담 문자/안내문, B 공지+대상 표, C 주간 보고, D 블로그 원고, E 학습지 중 한 개 | workflow.code와 같은 글자의 workflow.template |
| Windows인가요, Mac인가요? 버전은 진단에서 확인합니다 | windows / macos | os |
| 고객 본인 Claude 유료 구독과 Codex 지원 구독이 준비됐나요? | 플랜 이름과 고객 화면에서 사용 가능 확인 여부만 | plans.claude, plans.codex |
| 보안 프로그램 이름과 관리 PC 여부는? | 프로그램 이름 배열, 관리 정책은 별도 메모 | securitySoftware |
| 학생정보 폴더는 어디인가요? 판매자에게 말하지 말고 로컬에 적어 주세요 | 와일드카드 없는 절대 경로, 폴더를 열 필요 없음 | studentDataPaths |
| 사용할 도구는 무엇인가요? | 아래 스킬 ID 중 선택 | selectedSkills |
| 상태줄에 어떤 별칭을 표시할까요? 실제 계정은 본인이 따로 확인합니다 | 업무용 / 개인용 | accountLabel |

스키마 버전 `schemaVersion`은 `0.1`입니다. `plugins/ek-workroom/profiles/example.json`을 복사해 채웁니다. 비밀번호·인증 코드·API 키·학생 이름을 넣지 않습니다.

스킬 ID: korean-review, offline-spacing, parent-message, director-column, blog-copy, explanation-draft, question-draft, hwp-convert, worksheet-pdf, scan-cleanup, spreadsheet-check, lesson-slides.

추가 준비 확인(프로필에 비밀값 필드를 추가하지 않음):
- 중요 원본 백업과 개인정보를 지운 샘플 3~5개가 있나요?
- 학생 폴더·메신저·메일을 닫고 작업 창만 공유할 수 있나요?
- 휴대폰 인증은 직접 하고 화면 공유를 잠시 끌 수 있나요?
- 연속 165분+버퍼, 안정적인 인터넷이 있나요?
- 기존 도구·보안 정책으로 설치가 막히면 PC 관리자와 연락할 수 있나요?
- Node/Python을 새로 설치·업데이트하지 않는 범위를 이해하셨나요?
