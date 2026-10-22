# ek-setup v0.1 - AI 작업 환경 원격 세팅 키트 (시제품)

고객 Windows PC에서 고객이 직접 실행하면 **진단 -> 설치 계획 -> (동의 시) 설치 -> 결과 리포트**까지 진행하는 PowerShell 스크립트입니다. 2026-10-22 기준 v0이며 DryRun(계획만 출력)까지 검증되었습니다. 실제 설치 코드는 작성되어 있으나 아직 어떤 PC에서도 실행해 검증하지 않았습니다.

## 서비스 흐름

| 단계 | 누가 | 내용 |
|---|---|---|
| 1. 예약 | 고객 + 운영자 | 상담/결제 후 세션 예약. 고객에게 사전 안내(동의 원칙, 준비물) 전달 |
| 2. 원라이너 실행 | 고객 | 고객이 직접 PowerShell 을 열어 한 줄 실행. 기본은 DryRun(설치 없음) |
| 3. 리포트 전달 | 고객 | `report\report.json` 을 운영자에게 전송(메일/카톡 등). 자동 전송은 하지 않음 |
| 4. AI 1차 분석 | 운영자 + AI | `analyze-report.md` 프롬프트로 Claude/Codex 가 1차 진단, 설치 계획 확정 |
| 5. 설치 | 고객 | 운영자가 확인해 준 뒤 고객이 `-Apply` 로 재실행(동의 Y 입력) |
| 6. 원격 세션 | 운영자 + 고객 | 문제가 있을 때만. 화면 공유/원격 데스크톱은 고객이 승인·종료 권한 보유 |

## 사용법

```powershell
# 1) 진단 + 계획만 (아무것도 설치하지 않음, 기본값)
powershell -NoProfile -ExecutionPolicy Bypass -File .\ek-setup.ps1 -Profile basic

# 2) 프로필: basic | creator | dev
powershell -NoProfile -ExecutionPolicy Bypass -File .\ek-setup.ps1 -Profile dev -ReportDir .\report

# 3) 실제 설치 (동의 Y 입력 필요. 운영자 확인 후에만)
powershell -NoProfile -ExecutionPolicy Bypass -File .\ek-setup.ps1 -Profile basic -Apply
```

`-DryRun` 은 기본 동작을 명시하는 스위치이며, `-Apply` 를 주지 않으면 항상 DryRun 입니다. `-Yes` 는 실제 모드에서 Y 입력을 생략합니다(고객이 배너를 읽고 동의한 경우에만).

원라이너 예시(배포 URL 은 가칭이며 아직 존재하지 않음. 실제 배포 시 해시 고정과 코드 서명 필요):

```powershell
# 고객용: 스크립트를 먼저 내려받아 눈으로 확인한 뒤 실행하는 2줄 방식을 권장
irm https://example.invalid/ek-setup/ek-setup.ps1 -OutFile $env:TEMP\ek-setup.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File $env:TEMP\ek-setup.ps1 -Profile basic
```

`irm ... | iex` 같은 즉시 실행형은 보안 교육 관점에서 권하지 않습니다. 다운로드 후 확인하는 방식을 기본으로 합니다.

## 프로필별 설치 대상

| 프로필 | winget | npm 전역 |
|---|---|---|
| basic | Git.Git, OpenJS.NodeJS.LTS, Microsoft.VisualStudioCode, voidtools.Everything | @anthropic-ai/claude-code, @openai/codex |
| creator | basic + Python.Python.3.12 | 동일 |
| dev | creator + GitHub.cli | 동일 |

이미 설치된 도구는 건너뜁니다.

## 진단 항목 (읽기 전용)

Windows 버전/빌드, CPU/RAM/디스크 여유, 사용자명 한글/공백 여부, 실행 정책, 관리자 여부, winget, git/node/npm/python/code/claude/codex/gh/everything, PATH(항목 수·중복·없는 폴더만), 프록시, 기본 셸, Defender 실시간 보호(조회만), 인터넷(github.com, registry.npmjs.org HEAD 1회씩).

## 동의·보안 원칙

- 기본은 DryRun. 실제 설치는 `-Apply` + 동의 확인을 모두 거쳐야 한다.
- 비밀번호, OTP, API 키는 스크립트가 묻지도 저장하지도 않는다. 로그인(claude/codex)은 고객이 직접 한다.
- 수집하지 않는 것: 환경변수 전체, 토큰, 파일 내용, 사용자명, 컴퓨터 이름. 경로는 `%USERPROFILE%`/`<user>` 로 마스킹한다. 사용자명은 한글 포함·공백 포함 여부만 기록한다.
- 리포트는 로컬 폴더에 저장만 하며 자동 전송하지 않는다. 고객이 내용을 열어 확인한 뒤 직접 보낸다.
- 레지스트리 쓰기, 실행 정책 변경, 환경변수 영구 변경, Defender 설정 변경은 이 스크립트가 하지 않는다. 필요하면 리포트에 경고로만 남기고 별도 동의 단계에서 안내한다.
- 원격 세션은 고객 화면 공유 승인 하에 진행하고, 고객이 언제든 종료할 수 있어야 한다.

## 한계 (v0)

- Windows PowerShell 5.1 에서만 검증. Windows 11 Home 1대(개발 PC)에서 DryRun 만 실행. 실제 설치 경로(`-Apply`)는 미검증이다.
- 관리자 권한이 없으면 일부 winget 패키지가 UAC 창을 띄우거나 실패할 수 있다.
- winget 이 없는 PC(구형 Windows 10, 기업 정책 차단)는 계획만 만들고 설치하지 못한다.
- Node.js 설치 직후에는 PATH 가 새 터미널에서야 반영되어 npm 단계가 보류될 수 있다. 재실행으로 해결한다.
- Claude Code·Codex 의 로그인, 구독, 승인 설정은 범위 밖이다.
- 회사 PC(보안 솔루션, 프록시, 도메인 정책)는 별도 사전 협의가 필요하다. Mac/Linux 미지원.
- winget ID 와 npm 패키지명은 2026-10-22 작성 시점의 값이며 이 문서 작성 중 외부 사이트로 재확인하지 않았다(미확인). 배포 전 `winget search` 로 확인한다.
- 코드 서명, 배포 URL, 해시 고정은 미구현.

## 테스트

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tests\Test-Setup.ps1
```

3개 프로필을 DryRun 으로 실행해 report.json/report.md 생성, JSON 파싱, schema, warnings/plan 배열, 설치 미실행, 개인정보 미포함을 확인한다. 실패 시 종료 코드 1.
