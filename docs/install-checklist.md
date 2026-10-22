# 키트 v0.2.3 설치·설정 체크리스트

판매자가 세션·리허설 중에 한 줄씩 확인하는 표입니다. **키트가 고객 PC에 하는 일을 빠짐없이** 적었습니다. 여기 없는 변경은 키트가 하지 않습니다. 각 줄의 "확인"을 고객 화면에서 직접 보고 ☐에 표시합니다.

## 1. 설치되는 프로그램 (2개, 없을 때만)과 Mac 사전 준비

| ☐ | 무엇 | 어디에 | 누가·어떻게 | 확인 | 통과 기준 |
|---|---|---|---|---|---|
| ☐ | Claude Code | `~/.local/bin/claude.exe` (Mac `~/.local/bin/claude`) | 부트스트랩이 공식 설치 파일(`claude.ai/install.ps1`)을 받아 별도 창에서 실행. 관리자 권한 불필요. 설치 뒤 Windows 서명 확인 | `claude --version` | 버전 번호 출력 |
| ☐ | Codex CLI | 공식 설치 위치 | 부트스트랩이 공식 설치 파일(`chatgpt.com/codex/install.ps1`)을 같은 방식으로 실행. 실패해도 Claude는 그대로 두고 "Codex 설치 미완료" 표시 | `codex --version` | 버전 번호 출력 |
| ☐ | Mac: Apple 개발 도구(고객이 D-1에 직접 설치, 키트는 설치하지 않음) | Apple 공식 Command Line Tools | python3가 없다는 안내가 나오면 고객이 터미널에서 `xcode-select --install` 입력 → 설치(약 10분) → 판매자 블록 다시 붙여넣기 | 진단의 `python3` 줄 | Apple 개발 도구의 python3 3.9.6 또는 기존 python3 3.9 이상 |

이미 깔려 있으면 건너뛰고 "이미 있어 그대로 사용"이라고 나옵니다. 업그레이드·재설치는 하지 않습니다. 공식 설치 프로그램은 자기 실행 폴더를 사용자 PATH에 추가할 수 있습니다. 이 동작은 키트가 아니라 공식 설치 프로그램이 합니다.

## 2. 내려받아 풀어 두는 파일 (설치 아님)

| ☐ | 무엇 | 어디에 | 확인 | 통과 기준 |
|---|---|---|---|---|
| ☐ | 키트 원본 | `~/ek-workroom/kit-0.2.3/` | 부트스트랩 출력의 "키트 고정 위치" 줄 | 확인값(SHA256) 일치 문구가 먼저 나옴 |
| ☐ | 진단 파일 | `~/ek-diag.txt` | 고객이 메모장으로 열기 | 이름·이메일·전화번호·홈 경로가 가려져 있음 |

## 3. Claude Code 플러그인 (1개)

| ☐ | 무엇 | 어떻게 | 확인 | 통과 기준 |
|---|---|---|---|---|
| ☐ | `ek-workroom` 플러그인 | `claude plugin marketplace add "<키트 고정 위치>"` → `claude plugin install ek-workroom@ek-workroom` | Claude 안에서 `/plugin` | ek-workroom 0.2.3 사용 중 |
| ☐ | 스킬 16개 | 플러그인에 포함 | `/ek-workroom:` 입력 후 목록 | 진행용 6개 + 고객용 10개(5절) |

이 두 명령은 Claude Code가 자기 설정(`~/.claude/settings.json`의 플러그인 사용 목록, 플러그인 캐시 폴더)에 기록합니다.

## 4. 바뀌는 설정 (파일 1개: `~/.claude/settings.json`)

기존 설정 파일을 변경할 때 같은 폴더에 `settings.json.ek-backup-<시각>` 백업을 만듭니다. **기존 권한 목록은 합치고, 아래 승인 모드·우회 모드·상태줄 명령은 지정 값으로 교체합니다.** 그 밖의 기존 항목은 유지합니다. JSON이 깨져 있으면 아무것도 바꾸지 않고 멈춥니다. 매번 미리보기(`-DryRun`)를 먼저 보여 주고 원장님 승인 뒤 적용합니다.

| ☐ | 항목 | 내용 | 적용 스킬 | 확인 | 통과 기준 |
|---|---|---|---|---|---|
| ☐ | 백업 | 기존 설정 변경 전 `settings.json.ek-backup-<시각>` 생성. 되돌릴 때 해당 변경 전 백업 내용으로 복원 | ek-safety·ek-mode | 기존 파일을 변경했다면 백업 파일 있음 | 백업은 변경 전 원본과 같음. 같은 설정 재적용은 새 백업 없음 |
| ☐ | 학생 폴더 읽기·수정 차단 | `permissions.deny`에 `Read(...)`, `Edit(...)`. 입력한 경로와 실제 경로(OneDrive·바로가기 연결을 따라간 경로) 둘 다. Mac 한글은 두 가지 저장 형태 모두 | ek-safety | `/permissions`에 규칙 보임 → 연습 폴더의 `차단확인.txt` 읽기 요청 | **읽기 거부, 수정 거부** |
| ☐ | 명령 실행 승인 | `permissions.ask`에 `Bash`, `PowerShell`, `WebFetch`, `WebSearch`, `mcp__*` | ek-safety | 아무 명령이나 시켜 보기 | 실행 전 승인 창이 뜸 |
| ☐ | 기본 승인 모드 교체 | `permissions.defaultMode`를 `default`로 설정. 되돌릴 때 변경 전 `settings.json.ek-backup-<시각>` 내용으로 복원 | ek-safety | 설정 파일의 해당 값 확인 | `default` |
| ☐ | 승인 우회 모드 교체 | `permissions.disableBypassPermissionsMode`를 `disable`로 설정. 되돌릴 때 변경 전 `settings.json.ek-backup-<시각>` 내용으로 복원 | ek-safety | 설정 파일의 해당 값 확인 | `disable` |
| ☐ | 상태줄 실행기 복사·표시 | Windows는 `~/.claude/ek-workroom/statusline.ps1`, Mac은 `~/.claude/ek-workroom/ek_engine.py` 복사 후 연결 | ek-mode | Claude 화면 아래 | 모델·폴더·제공되는 대화 사용량 표시. 5시간 사용량은 Claude가 유효한 값을 제공할 때만 표시하며, 없어도 설정 실패가 아님 |
| ☐ | 기존 상태줄 명령 교체 | `statusLine.type`은 `command`. `statusLine.command`는 Windows에서 `powershell -NoProfile -ExecutionPolicy Bypass -File "<홈>/.claude/ek-workroom/statusline.ps1"`, Mac에서 `"<적용 시 확인한 Python 절대 경로>" "<홈>/.claude/ek-workroom/ek_engine.py" statusline`으로 교체. 다른 하위 키는 유지. 되돌릴 때 변경 전 `settings.json.ek-backup-<시각>` 내용으로 복원 | ek-mode | 설정 파일의 `type`·`command` 확인 | 해당 OS의 키트 실행기 명령과 일치 |

**Codex 설정(`~/.codex`)은 바꾸지 않습니다.** 교차 검토는 매번 읽기 전용 옵션을 붙여 실행하므로 Codex 쪽 설정 파일이 필요 없습니다.

## 5. 스킬 16개

진행용 6개는 세션에서 판매자 안내로만 부르고(자동 호출 꺼짐), 고객용 10개는 평소에 씁니다.

| 구분 | 스킬 | 하는 일 | 쓰는 도구 |
|---|---|---|---|
| 진행 | ek-start | 진단·로그인·준비물 확인 | 진단 스크립트(읽기 전용) |
| 진행 | ek-safety | 학생 폴더 차단·명령 승인 설정과 차단 시험 | apply-safety |
| 진행 | ek-mode | 상태줄, 작업실 폴더 만들기, 창 배치 | apply-statusline, apply-workspace |
| 진행 | ek-codex-link | Codex 로그인 확인과 교차 검토 1회 시연 | cross-check |
| 진행 | ek-flow | 내 업무 1개를 더미→실제 샘플로 완성 | 업무 템플릿 A~E |
| 진행 | ek-handoff | 단독 재실행, 남은 원격 접속 점검, 인계 | 종료 점검 스크립트(읽기 전용) |
| 고객 | cross-check | Claude가 만든 결과를 Codex가 읽기 전용으로 검토, Claude가 지적별로 판정 | ek-codex-review |
| 고객 | worksheet-pdf | 학습지 학생용·정답용 A4 PDF 조판 | ek-pdf(Edge) |
| 고객 | lesson-slides | 설명회·수업 16:9 슬라이드 PDF | ek-pdf(Edge) |
| 고객 | hwpx-read | 한글(HWPX) 문서에서 글자 뽑기 | ek-hwpx-text |
| 고객 | parent-message | 학부모 안내·상담 문자 초안 | 없음 |
| 고객 | spreadsheet-check | 엑셀(CSV) 명단·일정 대조와 대상 표 | 없음 |
| 고객 | korean-review | 맞춤법·띄어쓰기·문체 검수(외부 전송 없음) | 없음 |
| 고객 | explanation-draft | 문항 해설 초안 | 없음 |
| 고객 | question-draft | 문항 초안과 검증표 | 없음 |
| 고객 | blog-column | 블로그 글·원장 칼럼 초안 | 없음 |

## 6. 만들어지는 작업실 (`~/AI작업실`, 프로필로 위치 변경 가능)

| ☐ | 무엇 | 용도 |
|---|---|---|
| ☐ | `입력/` `결과/` `원본/` `검토/` | 넣을 자료 / 만든 결과 / 손대지 않을 원본 / Codex 검토 요청·결과 |
| ☐ | `CLAUDE.md` | 첫 줄 `@AGENTS.md`. Claude가 작업실 규칙을 확실히 읽게 함 |
| ☐ | `.ek-workroom/protected-paths.json` | 학생 폴더 경로 목록. Codex에 넘길 파일이 학생 폴더 안인지 확인하는 데만 씀(폴더 내용은 담지 않음). 재실행하면 새 학생 폴더를 합침 |
| ☐ | `AGENTS.md` | Claude가 읽는 작업실 규칙(한국어로 짧게, 승인 후 변경, 발송은 사람, 학생 폴더 금지). 키트의 Codex 교차 검토는 빈 임시 폴더에서 브리프·지정 대상 내용만 전달받으므로 필요한 규칙은 브리프에 명시 |
| ☐ | `검토/검토요청-양식.md` | 교차 검토 브리프 양식 |
| ☐ | `내-업무-실행법.md` | 고른 업무(A~E)의 실행 한 줄과 검수 항목 |

학생 폴더 안이나 학생 폴더를 품는 위치에는 만들지 않습니다(키트가 거부). 이미 있는 파일은 덮어쓰지 않고 "기존 파일 유지"로 남깁니다.

## 7. 키트가 하지 않는 것

- Python 설치 없음(Mac은 Apple 개발 도구 예외): 고객이 D-1에 직접 설치하며 키트는 설치하지 않음
- Node·Git·글꼴 등 다른 프로그램 설치·업그레이드
- 관리자 권한 요구, 실행 정책·보안 프로그램·환경변수 영구 변경
- 원격 접속 프로그램 설치, 예약 작업 등록, 백그라운드 상시 실행
- 문자·알림톡·메일·SNS 자동 발송, 판매자에게 자동 전송
- 비밀번호·인증 코드·API 키 수집, 판매자 계정 로그인, 계정 공유
- 학생 폴더 열기·목록 보기, 기존 파일 덮어쓰기

## 8. 오류를 막는 장치

| 위험 | 막는 방법 |
|---|---|
| 받은 파일이 바뀜 | 붙여넣기 블록 안의 확인값과 다르면 키트를 받기 전에 멈춤 |
| 같은 버전 재실행으로 덮어쓰기 | 고정 위치가 이미 있으면 멈추고 재실행 안내 |
| 공식 설치 프로그램의 종료가 키트까지 끊음 | 별도 PowerShell 창에서 실행 |
| 기존 Claude 설정 손실 | 변경 전 백업, 권한 목록 병합, 승인 모드·우회 모드·상태줄 명령은 4절 값으로 교체, 깨진 JSON이면 중단, 한글(CP949)·BOM 파일 읽기 지원 |
| 한글·공백 들어간 사용자 이름 | 모든 경로를 따옴표로 처리, 실측(`홍 길동`) 통과 |
| 진단에 개인정보 | 이름·이메일·전화번호·홈 경로 가림, 2글자 한글 이름 포함 |
| 조판 프로그램 없음 | Windows 기본 Edge 사용. 없으면 "브라우저에서 인쇄→PDF" 안내 |
| Codex가 파일을 고침 | 항상 `--sandbox read-only`, 결과는 `검토/`의 새 파일로만 |
| Codex가 학생 폴더를 읽음(Claude 차단은 Codex에 적용 안 됨) | Codex를 셸·브라우저·이미지 보기·MCP 등 **도구를 모두 끈 상태**로 빈 임시 폴더에서 실행. 검토할 파일 내용은 키트가 직접 읽어 넘기며, 실제 경로가 작업실 안이고 학생 폴더(`.ek-workroom/protected-paths.json`) 밖인 파일만 허용. 실측: 도구를 끈 Codex는 작업실 파일도 "열 수 없음" |
| PDF에 다른 폴더 파일·인터넷 자료가 섞임 | `file://`로 열지 않고 HTML 폴더 하나만 내주는 임시 로컬 서버(127.0.0.1)로 렌더. 브라우저 규칙상 다른 파일을 끌어올 수 없고, 인터넷·스크립트도 끔 |
| 학생 폴더 안 HTML을 PDF로 만듦 | 작업실(`.ek-workroom` 표시가 있는 폴더) 안이고 학생 폴더 밖인 HTML만 허용. 하드링크로 연결된 파일 거부, 다른 로컬 서비스로의 이동 차단 |
| 폴더 이름의 특수문자로 명령이 깨짐 | Codex 호출 인자를 명령 문장에 넣지 않고 따로 전달 |
| 결과물 덮어쓰기 | PDF·텍스트·검토 결과 모두 같은 이름 파일이 있으면 거부 |

## 9. 리허설 회차 0 진행 순서 (새 Windows 사용자 `리허설`)

| ☐ | 단계 | 기대 화면 |
|---|---|---|
| ☐ | 붙여넣기 블록 실행(D-1) | `SHA256 일치` → `키트 고정 위치` → `[DryRun] 검증과 계획만 마쳤습니다` |
| ☐ | 출력된 `-Apply` 명령 실행 | Claude·Codex 설치(또는 "이미 있음") → 진단 파일 생성 |
| ☐ | 새 터미널에서 `claude` → 본인 로그인 | 로그인 중 Zoom 공유 끄기. `/status`로 본인 계정 확인 |
| ☐ | `codex` → 본인 로그인 | 막히면 `codex login --device-auth` |
| ☐ | Codex 전역 설정이 비었는지 확인 | `~/.codex/`에 `AGENTS.md`·`skills/`가 없고 `config.toml`에 `mcp_servers`가 없음. 있으면 고객이 쓰던 것이니 지우지 말고 판매자와 상의(교차 검토는 MCP를 끄지만 전역 지시문은 읽힐 수 있음) |
| ☐ | 플러그인 설치 2줄 | `/plugin`에 ek-workroom 0.2.3 |
| ☐ | `/ek-workroom:ek-safety` | 미리보기 → 승인 → 적용 → Claude 재시작 → 차단 시험 통과 |
| ☐ | `/ek-workroom:ek-mode` | 상태줄 표시, `~/AI작업실` 생성 |
| ☐ | 작업실에서 `claude` 다시 열기 → `/ek-workroom:ek-codex-link` | 검토 결과가 `검토/`에 새 파일로 생김 |
| ☐ | `/ek-workroom:ek-flow` (업무 E 권장: 학습지 PDF) | `결과/`에 학생용·정답용 PDF, 쪽수 출력 |
| ☐ | `/ek-workroom:ek-handoff` | 단독 재실행 성공, 종료 점검 "남은 원격 접속 없음" |

막히면 오류 문구(개인정보 지운 것)와 단계 번호만 기록합니다.

## 10. 원래대로 되돌리기

| 무엇 | 방법 |
|---|---|
| Claude 설정 | `~/.claude/settings.json`을 지우지 말고 가장 이른 `settings.json.ek-backup-*` 내용으로 바꿔 저장 |
| 플러그인 | `claude plugin uninstall ek-workroom@ek-workroom` |
| 키트 원본 | `~/ek-workroom` 폴더 삭제 |
| 작업실 | 필요 없으면 `~/AI작업실` 폴더 삭제(만든 결과물도 지워지니 먼저 옮기기) |
| Claude Code·Codex | 각 공식 제거 방법(Claude: `~/.local/bin/claude.exe`와 `~/.local/share/claude` 삭제) |
