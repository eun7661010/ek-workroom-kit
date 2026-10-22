# ek-setup v0.2

Windows 사전 점검과 설치 계획을 만드는 보조 키트입니다. 기본은 DryRun입니다. 실제 설치는 이 시제품에서 실측하지 않았습니다. 표준 D-1 경로는 `bootstrap/`을 사용합니다.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\kit\ek-setup.ps1 -Profile basic -ReportDir .\.tmp\report
# 미리보기 확인과 원장 승인 후에만 실행
powershell -NoProfile -ExecutionPolicy Bypass -File .\kit\ek-setup.ps1 -Profile basic -Apply
```

`basic`, `creator`, `dev`는 기존 계획 수 6/7/8을 유지합니다. Node.js와 Python은 확인과 안내만 하며 이미 있어도 건드리지 않습니다. Claude Code는 네이티브 공식 설치가 기본이며 `-ClaudeInstaller winget`은 선택입니다. Codex는 공식 설치 스크립트를 사용합니다. 다른 선택 도구는 기존처럼 Git, VS Code, Everything, dev의 GitHub CLI입니다. 이미 있는 도구는 건너뜁니다.

`report.json`의 `schema: ek-setup/0.1`은 기존 소비자와의 호환을 위해 유지하고 `kitVersion: 0.2`로 구현 버전을 구별합니다. 진단에는 버전 번호·OS·PATH 항목 수·디스크 여유·실행 정책만 기록합니다. 파일 내용·폴더 목록·사용자명·연락처·IP·홈 경로는 수집하지 않습니다. 고객은 먼저 내용을 읽고 마스킹된 `ek-diag.txt`만 판매자에게 전달합니다. 리포트 자동 전송은 없습니다.

실행 정책·보안 SW·환경변수를 영구 변경하지 않습니다. 비밀번호·인증 코드는 고객 본인이 입력하며 고객 본인의 유료 구독 계정으로 로그인합니다. API 키는 받지 않습니다.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\kit\tests\Test-Setup.ps1
```

테스트 출력은 저장소 `.tmp/` 안에 남고 실제 홈 설정을 쓰지 않습니다. `-Apply` 설치, UAC, 설치 후 PATH 반영은 실제 고객 PC에서 별도 검증이 필요합니다.
