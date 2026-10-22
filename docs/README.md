# 원장님 AI 작업실 원격 세팅 키트 v0.1.1
고객 본인 Claude Code가 런북 플러그인을 실행하고 판매자는 Zoom 작업 창으로 감독합니다. 판매자 AI는 고객 화면·파일에 접근하지 않으며 고객이 직접 검토해 붙여 넣은 마스킹 진단만 사용합니다. 기본은 미리보기이며 실제 변경은 항목별 원장 승인 뒤입니다. 이 저장소는 시제품으로 실제 고객 설치·원격 세션 3회 검증을 끝내지 않았습니다.

## 구조
| 경로 | 내용 |
|---|---|
| .claude-plugin/marketplace.json | ek-workroom 로컬 마켓플레이스 |
| plugins/ek-workroom/.claude-plugin/plugin.json | 플러그인 0.1.1 |
| plugins/ek-workroom/skills | 런북 6개와 고객 스킬 12개 |
| plugins/ek-workroom/scripts | Windows/Mac 설정·진단·종료 스크립트 |
| plugins/ek-workroom/profiles | 비밀값 없는 로컬 고객 프로필 스키마·예시 |
| plugins/ek-workroom/templates | AGENTS·검토 브리프·A~E 더미 업무 시안 |
| bootstrap | 해시 검증·D-1 실행·로컬 ZIP 릴리스 도구 |
| kit | 기존 Windows 세팅 키트 v0.2와 회귀 테스트 |
| console | 판매자 165분 기록과 사전 설문 템플릿 |
| docs | D-1 안내·판매자 런북·고객 가이드북 |
| tests/run-all.ps1 | 전체 검증 진입점 |

## 설치·사용 경로
개발 검증은 가짜 홈 `.tmp/`에서만 합니다. 실제 사용자 설정을 쓰지 않습니다. 고객 설치 안내는 출시 승인 뒤 [D-1 안내](d-1-guide-customer.md)와 [판매자 런북](session-runbook-seller.md)을 사용합니다. 원장 재실행은 [사용 가이드](customer-guidebook.md)를 봅니다.
고객 로컬 Claude의 `/plugin marketplace add "<홈>/ek-workroom/kit-0.1.1"` → `/plugin install ek-workroom@ek-workroom`으로 설치합니다. 출처·버전을 확인한 뒤 `/ek-workroom:ek-start`부터 실행합니다. 공식 플러그인은 스킬을 네임스페이스로 노출하므로 `/ek-start`로만 부르지 않습니다. 스킬 내부의 `<플러그인>`은 설치된 플러그인 루트로 대체하며 고객 홈과 프로필은 로컬 값만 씁니다.

## 릴리스 절차
외부 업로드·커밋·push·설치·실제 홈 적용은 이 시제품 작업에 포함하지 않습니다.
1. 문법·설정·진단·무누출·해시·실제 홈 불변 테스트를 통과시키고 실제 결과를 기록합니다.
2. 로컬 ZIP만 만듭니다: `powershell -NoProfile -ExecutionPolicy Bypass -File bootstrap/make-release.ps1 -OutputDirectory .tmp/release-0.1.1 -Version 0.1.1 -ReleaseBaseUrl https://example.invalid/ek-workroom`. 출력은 새 빈 디렉터리를 사용합니다.
3. ZIP, bootstrap.ps1/sh, SHA256SUMS.txt를 확인합니다. 릴리스에 비밀값·고객 프로필 실경로가 없도록 예시만 포함합니다. ZIP과 각 bootstrap 파일의 해시는 서로 다릅니다.
4. 고객에게 전달할 때 스크립트 파일과 ZIP 주소를 고정 버전으로 지정하고 각 SHA256을 별도 메신저 메시지 또는 Zoom으로 확인합니다. 이 작업은 외부 전달을 실행하지 않습니다.
5. 기본 D-1은 생성된 paste-block-windows.txt 또는 paste-block-mac.txt를 메신저로 전달합니다. 기대 해시를 넣은 블록이 HTTPS 파일을 받은 뒤 자동 대조하고 일치할 때만 DryRun을 실행합니다. 직접 64자 대조는 대안입니다. bootstrap은 ZIP을 ExpectedSha256과 다시 대조한 뒤 계획을 출력합니다. 초급 고객의 Source는 make-release가 만든 ZIP을 권장합니다. 폴더 입력의 해시는 별도 FOLDER-MANIFEST/FOLDER-SHA256 규칙이므로 ZIP 해시와 바꿔 쓰지 않습니다.

## 검증 명령
```powershell
claude plugin validate .
claude plugin validate plugins/ek-workroom
powershell -NoProfile -ExecutionPolicy Bypass -File tests/run-all.ps1
```
run-all은 기존 kit 회귀, 모든 PS 파서와 Git Bash `bash -n`, 가짜 홈 설정 병합·백업·멱등·잘못된 JSON 거부, 개인정보 미출력, bootstrap 해시 일치/불일치, 플러그인 누출 검사를 실행합니다. 테스트 전후 실제 Claude settings와 Codex 파일 해시를 비교합니다. v0.1.1 작업에서는 설치 금지 지시에 따라 플러그인 설치를 실행하지 않고 두 validate와 정적 스킬 목록만 검사합니다. CLI 설정 홈도 .tmp로 격리합니다. 검증 명령의 성공은 실제 설치 -Apply나 Mac 실기 검증을 뜻하지 않습니다.

## 안전·범위·가정
- 실제 홈의 Claude settings.json과 Codex config.toml/auth.json/AGENTS.md 지문은 읽기 전용으로 기록합니다. 세션·로그는 다른 호스트 작업이 계속 바꾸므로 비교하지 않습니다. OS가 읽기를 막은 파일·소켓은 잠금 해제 없이 크기·수정 시각을 대조합니다. 실행 중인 Codex가 자체 갱신하는 SQLite WAL/SHM과 부모 Claude의 실행 상태 파일 `.claude.json`은 전후 SHA256을 별도 보관하고 설정 불변 판정에서 분리합니다. 명세의 `.claude/settings.json`은 항상 해시 대조 대상입니다. 링크된 디렉터리는 따라가지 않습니다. 실행 중인 호스트 전체의 바이트 불변을 보장하는 검사는 아닙니다.
- 기존 제3자 mod·관리자 설정이 권한 판정에 영향을 줄 수 있으므로 현장에서 더미 파일로 Read/Edit 차단을 반드시 실측합니다. 종료 점검은 정지된 원격 서버의 설치 흔적도 보수적으로 표시하므로 기존 사용 목적을 확인합니다.
- Node/Python은 설치·업그레이드하지 않습니다. Mac 스크립트는 기존 Python3가 필요하며 없으면 멈춥니다. 스킬 의존 도구도 설치하지 않고 수동 대안/미완료를 표시합니다.
- Claude/Codex는 공식 네이티브 설치 경로와 고객 본인 유료 구독 로그인을 사용합니다. 계정 지원 여부는 고객 화면에서 확인하며 API 키·대리 로그인·계정 공유를 받지 않습니다.
- 상태줄 계정은 accountLabel 수동 별칭입니다. 실제 이메일·인증 파일을 읽지 않습니다. 로그인 계정은 본인 `/status` 확인이 기준입니다.
- Read/Edit deny는 Claude 도구 규칙이며 OS 격리가 아닙니다. 셸·웹·MCP 전체를 ask로 묶습니다. 학생정보 접근·삭제·이동·git push·외부 전송 요청은 사용자가 거절해야 합니다. 원격 종료 검사도 알려진 서비스·호스트만 확인하며 Zoom 공유 종료는 사람이 확인합니다.
- 위험 명령 ask를 구현하기 위해 개별 패턴 대신 전체 셸 ask를 쓰므로 일반 명령도 물어봅니다. 본인 계정의 공식 로그인 전환만 안내하며 자동 계정 전환 도구는 구현하지 않습니다.
- 작업 대상은 A~E 업무 한 개입니다. 선택 3개는 목록만 제공합니다: 시험지 HWPX 빌드, PDF·이미지 글자 추출, 강의 영상 받아쓰기. 자동 발송·게시·수납 원장 변경은 포함하지 않습니다.
- 가이드북은 13개 목차의 Markdown 사용 초안이며 24쪽 PDF 완성본은 후속 제작입니다. 165분과 권장 PC 사양은 설계 가정입니다. 깨끗한 Windows/Mac 실기 -Apply 각 3회, 실제 deny 차단, 고객 단독 재실행, 2주 정착 점검은 남은 검증입니다.

## 공식 문서와 형식
[플러그인](https://code.claude.com/docs/en/plugins), [플러그인 구조](https://code.claude.com/docs/en/plugins-reference), [마켓플레이스](https://code.claude.com/docs/en/plugin-marketplaces), [설정](https://code.claude.com/docs/en/settings), [상태줄](https://code.claude.com/docs/en/statusline), [설치](https://code.claude.com/docs/en/setup)를 기준으로 로컬 marketplace source, .claude-plugin 매니페스트, skills/SKILL.md와 statusLine 설정을 사용합니다. 문서 수집·직접 fetch 결과와 CLI 실제 결과는 최종 작업 보고에 별도로 남깁니다.

2026-10-22 위 6개 URL과 연결된 공식 permissions 원문을 직접 확인했습니다. Windows 절대 경로는 문서의 `//c/…/**` 형식으로 변환합니다. statusLine 입력에는 로그인 계정 필드가 없어 수동 별칭을 표시합니다. 플러그인 자체 settings로 권한을 자동 배포하지 않고 승인받은 스크립트가 고객 홈 설정에 병합합니다. `claude plugin validate`의 기본 검증은 로컬 사용 기준입니다. 공개 디렉터리 제출용 LICENSE·아이콘 검사 경고는 이 시제품의 로컬 검증 종료 코드와 별개이며 공개 제출은 하지 않았습니다.

## v0.1.1 검수 응답과 리허설
[24건+추가6건 판정표](review-v0.1-response.md)를 확인하세요. `.gitattributes`가 Mac LF·Windows PS CRLF를 고정하고, run-all은 실제 ZIP의 CR과 저장소 텍스트 제어문자도 검사합니다.
키트 배치는 `<홈>/ek-workroom/kit-0.1.1` 고정이며 동일 위치 재실행을 거부합니다. 테스트의 `-Library`/`Initialize-EkKit -Prepare`와 Mac `--prepare-only`는 설치 없이 가짜 홈의 키트 파일 배치만 시험하기 위한 API입니다. 일반 고객은 DryRun 후 승인한 Apply만 사용합니다.
릴리스 기본 URL은 `example.invalid`이므로 실제 HTTPS 배포 주소를 정해 -ReleaseBaseUrl로 다시 생성해야 합니다. 이 작업은 업로드·외부 전달하지 않습니다.
