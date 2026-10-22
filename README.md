# 원장님 AI 작업실 원격 세팅 키트 v0.2.1

학원 원장 PC의 Claude Code·Codex CLI와 개인정보 없는 작업실을 준비하는 키트입니다. Claude가 초안을 만들고 Codex가 읽기 전용으로 교차 검토합니다. HTML→PDF와 HWPX 텍스트 추출은 정해진 스크립트로 실행합니다. 고객 본인 AI가 작업하고 판매자는 Zoom 작업 창으로 감독합니다.

- [고객 D-1 안내](docs/d-1-guide-customer.md)
- [판매자 165분 진행표](docs/session-runbook-seller.md)
- [구조·검증·릴리스](docs/README.md)
- [세션 콘솔](console/session-console.md)
- [사전 설문](console/intake-survey.md)

부트스트랩은 해시 검증·키트 고정 위치 배치 → Claude Code 확인/공식 설치 → Codex CLI 확인/공식 설치 → 진단의 4단계입니다. 기본은 DryRun이고 승인한 Apply만 설치합니다. Codex 설치 실패 시 Claude를 유지하고 미완료를 표시합니다. Node·Python·Git을 설치하지 않으며 관리자 권한을 요구하지 않습니다. Mac 실행기는 기존 Python 3가 필요합니다.

부트스트랩이 출력한 **고정 키트 절대 경로**를 사용합니다.
```text
claude plugin marketplace add "<부트스트랩이 출력한 키트 절대 경로>"
claude plugin install ek-workroom@ek-workroom
```

진행용 6개와 고객용 10개, 총 16개 스킬을 제공합니다. `/ek-workroom:ek-start` → `ek-safety` → `ek-mode` → `ek-codex-link` → `ek-flow` → `ek-handoff` 순서로 실행하며 모두 `/ek-workroom:` 접두사를 붙입니다. 작업실 `CLAUDE.md` 첫 줄은 `@AGENTS.md`로 공통 규칙을 가져오고 Codex도 AGENTS.md를 읽습니다.

v0.2.1은 Codex의 파일·명령·인터넷 도구와 웹 검색을 비활성화하고, 실제 경로·크기·UTF-8·하드링크 여부를 확인한 브리프와 대상 내용을 직접 전달합니다. 실행 폴더는 매번 새 빈 임시 폴더입니다. PDF는 작업실 안의 보호 경로와 겹치지 않는 HTML 폴더만 제공합니다. 임시 HTTP 서버의 난수 토큰·경로 제한·CSP와 해당 포트만 허용하는 프록시 설정으로 다른 파일과 로컬 서비스 접근을 제한합니다. 그림·로고는 HTML과 같은 폴더 또는 하위 폴더에 두고 상대 경로로 연결합니다.

```powershell
claude plugin validate .
claude plugin validate plugins/ek-workroom
powershell -NoProfile -ExecutionPolicy Bypass -File tests/run-all.ps1
```

개발 검증은 저장소 `.tmp/` 가짜 홈에서만 실행합니다. 실제 고객 PC와 Windows Codex read-only 동작은 새 로컬 사용자 리허설에서 확인해야 합니다. 고객 단독 재실행·결과 파일 열람 전 완료로 표시하지 않습니다. [이전 검수 이력](docs/review-v0.1-response.md)은 보존합니다.
