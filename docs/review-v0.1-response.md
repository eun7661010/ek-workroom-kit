# v0.1 검수 응답 — v0.1.1

검수 보고서 bullet 순서로 1~24를 부여했습니다. 기준 HEAD는 `25b60ae`이며, 판매자가 복원한 D-1 제어문자 수정은 유지했습니다. 맞는 부분만 고치며 심각도는 원 보고서 표기를 보존했습니다.

원 검수 24건: 맞음 12 / 틀림 3 / 부분 9. 추가 6건: 맞음 6. 합계 30건: 맞음 18 / 틀림 3 / 부분 9.

| 번호 | 심각도 | 판정 | 근거(원문·재현·최종 코드) | 조치 |
|---|---|---|---|---|
| 1 | P0 | 맞음 | `bootstrap/bootstrap.ps1:45` — 기존 상위 .tmp 의존·위치 미출력 확인. Test-V011 고정 배치/재실행 거부 실측. | 홈/ek-workroom/kit-0.1.1 고정, 경로·재실행 명령 출력. |
| 2 | P0 | 맞음 | `plugins/ek-workroom/scripts/common.ps1:13` — CP949 설정·프로필을 주입한 Test-V011에서 strict 디코딩 거부 및 원본 SHA 동일. v0.1 ReadAllText는 대체문자 허용. | UTF-8/BOM 허용, CP949·U+FFFD 거부. 오류 원인과 UTF-8 재저장 안내. |
| 3 | P0 | 맞음 | `bootstrap/bootstrap.ps1:120` — v0.1 scriptblock exit 0 후 AFTER_INSTALLER 출력 0건. 가짜 installer exit 0/7 자식 프로세스 회귀 통과. | 다운로드 파일을 별도 PowerShell/bash로 실행하고 종료 코드 확인. |
| 4 | P1 | 틀림 | `bootstrap/bootstrap.sh:3` — git show 25b60ae의 .sh 6개 모두 CR 바이트 0. 현 HEAD가 전부 CRLF라는 전제가 틀림. | 해당 결함 수정 없음. 추가 요구 d로 LF 속성·ZIP 검사만 별도 추가. |
| 5 | P1 | 맞음 | `plugins/ek-workroom/scripts/statusline.ps1:2` — CP949 입출력을 강제하고 UTF-8 한글 JSON을 전달하면 원본은 실패. test_v011.py에서 수정본 한글 stdin/stdout 통과. | 원시 UTF-8 stdin, UTF-8 stdout 명시. |
| 6 | P1 | 부분 | `plugins/ek-workroom/scripts/common.ps1:62` — 기존 모든 ReparsePoint/상위 symlink 차단은 의도된 보호지만 정상 연결·Mac /tmp도 막음. Windows junction 보조 시험. Cloud Filter 실기는 미확인. | 최종 홈 경계 안 쓰기 허용, Cloud reparse와 실제 링크 구분, Mac 시스템 상위 별칭 허용. |
| 7 | P1 | 부분 | `kit/ek-setup.ps1:13` — es는 Everything GUI와 별개. 공식 winget PACKAGE_ALREADY_INSTALLED=0x8A150061 확인. UAC는 설치 권한 특성으로 제품 결함 아님. | GUI 설치 위치 확인, 기설치 종료 코드 허용, VS Code user 범위, UAC 본인 승인/보류 안내. |
| 8 | P0 | 부분 | `plugins/ek-workroom/scripts/common.ps1:73` — 실존/연결 최종 경로 미검사는 맞음. 기존 드라이브 루트는 이미 거부. 공식 permission specifier는 괄호를 literal로 허용. | 실존·입력+실제 경로·실제 대소문자·Mac NFC/NFD 추가. 사용자 지시대로 루트/홈 전체 계속 거부, 괄호 제한은 추가하지 않음. |
| 9 | P0 | 부분 | `plugins/ek-workroom/skills/ek-safety/SKILL.md:20` — 공식 settings는 permissions 변경을 실시간 reload함. 재시작이 항상 필요하다는 전제는 틀림. 적용 확인 없는 시험 순서는 개선 필요. | /permissions와 /status 먼저 확인, 미반영 시 재시작, 더미 Read 차단 뒤 Edit 시험. |
| 10 | P0 | 부분 | `plugins/ek-workroom/scripts/common.ps1:127` — 기존 수집은 고정 라벨·숫자 allowlist라 실제 두 글자 이름 노출은 재현 안 됨. 마스킹 함수의 길이/전화·IPv6 누락은 코드상 확인. | 두 글자·홈 구분자·전화 점/유선/0507·IPv6 주입 회귀와 방어 보강. |
| 11 | P2 | 부분 | `bootstrap/bootstrap.ps1:120` — 공식 pipe 설치 문구는 원 명세가 지정했으므로 문구 자체를 결함으로 보지 않음. 서명 확인 누락과 child 격리 필요는 확인. | 파일 다운로드+자식 실행으로 정리, Windows 신규 Claude 설치 뒤 Valid 서명 확인. |
| 12 | P2 | 맞음 | `bootstrap/bootstrap.ps1:45` — v0.1은 검증/추출 때 ZIP을 따로 열고 폴더 원본에서 실행. HTTPS 미리보기·적용 중복 다운로드 구조 확인. | snapshot 복사 검증, 동일 잠금 ZIP 핸들 검증/추출, 검증 캐시 재사용 명령, 호출 staging 정리. |
| 13 | P2 | 부분 | `plugins/ek-workroom/scripts/statusline.ps1:16` — 기존에도 계정 별칭과 /status 확인을 명시해 로그인 연동으로 속인 것은 아님. 가이드의 별칭 변경 명령은 빠짐. | 수동 고정값 문구, profile.accountLabel 수정 후 apply-statusline 재실행 안내. |
| 14 | P0 | 맞음 | `docs/d-1-guide-customer.md:4` — 25b60ae 원문에 0x08 3건, 작업 시작 때 판매자 복원본은 0건. 판매자의 수정을 확인·보존. | 새 D-1 블록 안내로 재작성, 저장소 텍스트 전체 제어문자 회귀 추가. |
| 15 | P1 | 맞음 | `plugins/ek-workroom/skills/ek-start/SKILL.md:17` — Windows 지시에 PowerShell & 연산자를 써 Bash 문법·실행 정책 경계에서 실패 가능. | Windows 실행을 powershell.exe -NoProfile -ExecutionPolicy Bypass -File로 통일, 영구 정책 변경 없음. |
| 16 | P1 | 틀림 | `plugins/ek-workroom/skills/ek-start/SKILL.md:14` — 공식 plugins-reference Where each variable resolves: Skill/command/agent Markdown 본문에서도 인라인 치환 지원. hooks/MCP 전용이라는 주장이 틀림. | 변수 제거/경로 수동 계산 변경 안 함. 치환된 실제 경로를 사용한다는 설명만 명확화. |
| 17 | P1 | 맞음 | `plugins/ek-workroom/skills/ek-codex-link/SKILL.md:19` — 공식 non-interactive 문서와 로컬 codex exec --help에 Git 검사 및 --skip-git-repo-check 확인. 키트는 Git 초기화를 보장하지 않음. | 고객이 확인한 비식별 작업실에서 read-only와 skip-git-repo-check 병기. |
| 18 | P1 | 맞음 | `plugins/ek-workroom/skills/ek-start/SKILL.md:21` — 원문에 Claude 승인 코드 복귀와 Codex device-auth 경로 없음. 로컬 0.162.1 login --help에도 옵션 존재 확인. | 런북·D-1·가이드에 본인 URL/코드와 codex login --device-auth 추가. |
| 19 | P1 | 맞음 | `bootstrap/bootstrap.ps1:127` — 자식 installer의 PATH 변경은 부모에 반영되지 않음. mock 설치 뒤 process PATH 보강 회귀 통과. | 홈 .local/bin·현재/User/Machine PATH를 프로세스에만 반영, 새 터미널·Claude 재시작 안내. |
| 20 | P1 | 맞음 | `plugins/ek-workroom/scripts/common.ps1:31` — 기존 최상위 catch가 자체 입력 오류도 고정 문구로 지움. UTF-8/없는 경로 오류 회귀 확인. | 전용 안전 오류만 구체 안내, 시스템 예외의 경로·원문은 비공개. |
| 21 | P1 | 부분 | `plugins/ek-workroom/scripts/ek_engine.py:218` — systemsetup 일반 권한의 미확인은 보수적 정상 동작. 모든 Mac에서 항상 실패라는 단정은 과함. QuickAssist 누락은 맞음. | sshd/launchctl 보조, QuickAssist 추가, 자동 결과 유지하며 Mac GUI 본인 확인을 인계 근거로 기록. |
| 22 | P2 | 맞음 | `plugins/ek-workroom/templates/flows/A.md:14` — A~E의 위 더미 입력/위 한 줄은 새 대화 입력 파일을 지정하지 않음. | ./입력/<코드>-입력.txt와 새 결과 경로 명시, 파일 없으면 탐색 없이 중단. |
| 23 | P2 | 부분 | `docs/session-runbook-seller.md:24` — 진단 반복·Codex 설치 시점 불일치는 맞음. 외부 설계 문서의 옛 플러그인 이름은 현재 코드 오류가 아니며 수정 범위 밖. | 10~30분 ek-start/설치로그인, 60~70분 검토; D-1 진단 재사용. 외부 문서는 건드리지 않고 이름 매핑 기록. |
| 24 | P2 | 틀림 | `kit/ek-setup.ps1:105` — 공식 chatgpt.com/codex/install.ps1 원문 직접 fetch 성공(releases.openai.com으로 연결). 원 명세도 이 주소를 기본으로 지정. | URL 교체/대안 설치 옵션을 추가하지 않음. 실패 시 보류·판매자 문의 유지. |
| 추가 a | 필수 | 맞음 | `bootstrap/make-release.ps1:80` — Windows/Mac 붙여넣기 전체를 가짜 HTTPS 다운로드로 시험. 해시 일치 DryRun/불일치 실행 전 중단 통과. | 버전·URL·bootstrap/ZIP 해시를 채운 paste-block 두 파일 생성. |
| 추가 b | 필수 | 맞음 | `bootstrap/bootstrap.ps1:45` — PS API와 Mac --prepare-only에서 고정 배치/동버전 재실행 거부 통과. | 홈/ek-workroom/kit-0.1.1 배치와 절대 경로 출력, marketplace 문서 통일. |
| 추가 c | 필수 | 맞음 | `plugins/ek-workroom/scripts/common.ps1:73` — 실제 연결 폴더·입력 소문자/실제 표기 deny, NFC/NFD, 없는 경로/루트/홈 거부 회귀. | 입력+최종 경로 차단, Mac 두 정규화, 눈에 띄는 셸 승인 거절 안내. |
| 추가 d | 필수 | 맞음 | `.gitattributes:2` — make-release와 test_v011.py가 릴리스 ZIP .sh/.py의 CR=0 검사. 저장소 PS CRLF 검사. | Mac LF·PS CRLF 속성 고정. 기존 CRLF라는 지적과 별개의 예방 요구. |
| 추가 e | 필수 | 맞음 | `tests/test_v011.py:77` — git 대상 텍스트 전체를 UTF-8 디코딩 후 탭/개행 외 Unicode Cc 검사. .tmp/.git 제외. | 제어문자 0건 검사 run-all 연결. |
| 추가 f | 필수 | 맞음 | `docs/d-1-guide-customer.md:16` — 로컬 codex login --help + Claude 공식 authentication 코드 복귀 절차 대조. | D-1·런북·가이드에 원격 로그인 대처 통일. |

재현 진입점: `powershell -NoProfile -ExecutionPolicy Bypass -File tests/run-all.ps1`. 개별 회귀는 `tests/Test-V011.ps1 -RunDirectory <저장소/.tmp/새폴더>`와 `tests/test_v011.py`입니다. 두 진입점 자체도 홈을 격리합니다. 설치 테스트는 가짜 installer 또는 준비 전용 API만 사용합니다.

판정의 원문 근거: [권한 괄호 문법](https://code.claude.com/docs/en/permissions#permission-rule-syntax), [플러그인 본문 변수 치환](https://code.claude.com/docs/en/plugins-reference#where-each-variable-resolves), [설정 자동 reload](https://code.claude.com/docs/en/settings#when-edits-take-effect), [Claude 로그인 코드](https://code.claude.com/docs/en/authentication), [Codex Git 검사](https://learn.chatgpt.com/docs/non-interactive-mode#git-repository-required), [공식 Codex 설치 파일](https://chatgpt.com/codex/install.ps1), [공식 winget 오류 상수](https://raw.githubusercontent.com/microsoft/winget-cli/master/src/AppInstallerSharedLib/Public/AppInstallerErrors.h).

실측 한계: Windows의 가짜 홈·Git Bash·Python 공통 엔진까지 검증합니다. 실제 Mac/OneDrive Cloud Filter, 실제 설치·서명, Claude deny 집행은 지인 PC 리허설에서 확인합니다. 외부 파일/설정에 대한 완전한 OS 격리를 제공하지 않습니다.

테스트 과정의 범위 이탈 기록: 초회 단독 fixture 테스트에서 홈 격리가 누락되어 실제 홈의 `ek-workroom`에 102바이트 가짜 bootstrap.ps1 2개가 생성되었습니다. 설치/실제 사용자 설정 적용은 없었습니다. 이후 두 테스트 진입점에 격리를 강제했고, 범위 밖 파일을 삭제·수정하지 않았습니다. 정리는 별도 허용이 필요합니다.
