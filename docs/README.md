# AI 작업실 키트 v0.2.0 구조·검증

고객 본인 Claude Code가 런북을 실행하고 판매자는 Zoom 작업 창으로 감독합니다. 판매자 AI에는 고객이 직접 검토한 마스킹 진단만 전달합니다. 설정은 미리보기→항목 승인→스크립트 적용→확인 순서입니다. PDF·텍스트 추출·교차 검토 스크립트는 실행 도구이며 기존 출력 파일을 거부합니다.

| 경로 | 내용 |
|---|---|
| .claude-plugin/marketplace.json | 로컬 마켓플레이스 |
| plugins/ek-workroom/.claude-plugin/plugin.json | 플러그인 0.2.0 |
| plugins/ek-workroom/skills | 진행용 6개·고객용 10개 |
| plugins/ek-workroom/scripts | Windows/Mac 설정·진단·작업 실행기 |
| plugins/ek-workroom/profiles | 비밀값 없는 로컬 프로필 |
| plugins/ek-workroom/templates | AGENTS·검토 브리프·A~E 업무 실행법 |
| bootstrap | 해시 검증·공식 CLI 설치·로컬 릴리스 |
| console | 165분 세션 기록·사전 설문 |
| tests/run-all.ps1 | 통합 검증 진입점 |

## 설치와 업무
부트스트랩의 4단계는 키트 검증·고정 위치 배치, Claude Code 확인/설치, Codex CLI 확인/설치, 진단입니다. Codex 실패는 Claude 설치를 되돌리지 않고 미완료로 표시합니다. 공식 설치 파일은 다운로드 후 별도 프로세스에서 실행합니다. Windows Git은 선택 사항이며 없어도 PowerShell을 사용합니다. Node·Python·Git 설치·업데이트는 하지 않습니다. Mac은 기존 Python 3가 필요합니다.

부트스트랩이 출력한 고정 키트 절대 경로로 `claude plugin marketplace add "<키트 절대 경로>"`와 `claude plugin install ek-workroom@ek-workroom`을 실행합니다. 출처·버전을 확인한 뒤 `/ek-workroom:ek-start`부터 시작합니다. [D-1 안내](d-1-guide-customer.md)와 [판매자 진행표](session-runbook-seller.md)를 따릅니다. [고객 가이드북](customer-guidebook.md)은 판매자가 별도로 정리하는 문서입니다.

`apply-workspace`가 선택 workspacePath 또는 `<홈>/AI작업실`에 입력/결과/원본/검토와 규칙·검토 양식·실행법을 만듭니다. 학생 폴더와 입력·실제 경로가 서로 포함되면 거부합니다. 기존 파일은 유지합니다. `CLAUDE.md`의 `@AGENTS.md`로 Claude와 Codex가 공통 규칙을 사용합니다.

`cross-check`는 Claude의 브리프 계획 승인→검토 요청 저장→ek-codex-review→지적별 맞음/틀림/부분 판정→반영 계획 승인→새 파일 생성 순서입니다. Codex는 직접 수정하지 않습니다. 대안 초안도 결과 파일로만 받습니다. `worksheet-pdf`와 `lesson-slides`는 HTML을 만든 뒤 `ek-pdf`로 PDF를 만듭니다. `hwpx-read`는 `ek-hwpx-text`로 텍스트만 읽습니다. 표 입력은 CSV UTF-8입니다.

상태줄은 프로필 없이 모델·작업 폴더·대화 사용량·제공되는 경우 5시간 사용량을 표시합니다. 실제 로그인은 고객 본인이 확인합니다. 창 배치는 Windows Terminal이 있으면 `Alt+Shift+=`, 아니면 터미널 창 두 개입니다.

## 검증과 릴리스
```powershell
claude plugin validate .
claude plugin validate plugins/ek-workroom
powershell -NoProfile -ExecutionPolicy Bypass -File tests/run-all.ps1
```
통합 검증은 `.tmp/` 가짜 홈 설정 병합·백업·멱등, 경로 경계·연결 경로, HWPX 합성 입력, 가짜 Codex 인자, 실제 Edge PDF, 설치 스크립트 exit 격리, 실제 홈 설정 무변경을 검사합니다. Mac 엔진은 Python 테스트로 확인하며 Mac 실기 검증을 대신하지 않습니다. 실제 Codex 검토는 테스트에서 호출하지 않습니다. Windows 새 로컬 사용자에서 실제 read-only 샌드박스·고객 로그인·단독 재실행을 리허설해야 합니다.

로컬 ZIP은 `powershell -NoProfile -ExecutionPolicy Bypass -File bootstrap/make-release.ps1 -OutputDirectory .tmp/release-0.2.0 -Version 0.2.0`으로 새 빈 폴더에 만듭니다. 기본 HTTPS 릴리스 URL은 GitHub `https://github.com/eun7661010/ek-workroom-kit/releases/download`를 유지합니다. 버전 태그 `0.2.0` 아래 ZIP·bootstrap 두 파일과 SHA256SUMS를 확인하고 생성된 paste-block-windows.txt / paste-block-mac.txt를 고객 안내에 사용합니다. 만드는 도구는 업로드·외부 전달을 하지 않습니다. 개발 작업의 설치·실제 홈 적용·커밋·push·외부 발송은 금지합니다.

## 안전과 남은 확인
Read/Edit deny는 Claude 도구 규칙이며 OS 권한 격리가 아닙니다. 셸·웹·MCP 전체 ask를 유지하고 학생 경로 접근·삭제·이동·외부 전송은 거절합니다. 적용 뒤 `/permissions`와 개인정보 없는 시험 파일 Read/Edit 차단을 확인해야 합니다. 인증은 고객이 화면 공유를 끄고 직접 수행하며 인증 파일을 읽지 않습니다. 원격 종료 점검과 Zoom 공유 종료는 사람이 확인합니다.

실제 홈 settings.json과 Codex 설정·인증·AGENTS 파일은 전후 해시를 비교합니다. 실행 중 세션·로그·SQLite WAL/SHM은 호스트 동작으로 바뀔 수 있어 설정 판정과 분리합니다. 연결 디렉터리는 따라가지 않습니다. 권한·잠금으로 읽을 수 없으면 메타데이터로 비교하며 잠금을 해제하지 않습니다.

A~E 업무 한 개를 완성하고 결과를 열어 검수합니다. 발송·게시·수납 원장 반영은 범위에 없습니다. 165분은 설계 기준입니다. 깨끗한 Windows/Mac 실기, 고객 단독 재실행과 2주 정착 점검은 현장에서 확인할 항목입니다. [이전 검수 판정표](review-v0.1-response.md)와 validation 이력은 변경하지 않습니다.
