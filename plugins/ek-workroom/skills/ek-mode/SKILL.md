---
name: ek-mode
description: 상태줄·작업실 폴더·읽기 편한 두 창을 설정할 때 사용한다.
disable-model-invocation: true
---

# 상태줄·작업실 폴더·읽기 편한 두 창을 설정할 때 사용한다.

고객 본인 Claude Code에서 진행합니다. 판매자는 Zoom 작업 창으로 감독합니다. 학생정보 폴더를 열지 않고 비밀번호·인증 코드·인증 파일을 받지 않습니다. 로그인은 본인이 화면 공유를 끄고 직접 합니다. 설정 변경은 미리보기→항목 승인→스크립트 적용→확인 순서입니다. 기존 파일 덮어쓰기 금지. 결과 파일을 열어 확인하기 전 완료라고 말하지 않는다. 같은 오류가 3회면 원인을 재검토합니다.
`${CLAUDE_PLUGIN_ROOT}`는 설치된 플러그인 절대 경로로 치환합니다. 고객 홈과 프로필도 고객이 지정한 절대 경로를 사용합니다.

## 상태줄
프로필 인자 없이 미리보기합니다.
Windows:
```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "${CLAUDE_PLUGIN_ROOT}/scripts/apply-statusline.ps1" -TargetHome "<고객 홈>" -DryRun
```
Mac:
```sh
bash "${CLAUDE_PLUGIN_ROOT}/scripts/apply-statusline.sh" --home "<고객 홈>" --dry-run
```
기존 설정 병합·백업 계획을 설명하고 승인 뒤 `-Apply` 또는 `--apply`로 실행합니다. 모델·작업 폴더·대화 사용량·제공되는 경우 5시간 사용량을 확인합니다. 실제 계정은 본인이 `/status`로 확인합니다.

## 작업실 만들기
Windows:
```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "${CLAUDE_PLUGIN_ROOT}/scripts/apply-workspace.ps1" -TargetHome "<고객 홈>" -ProfilePath "<프로필 JSON>" -DryRun
```
Mac:
```sh
bash "${CLAUDE_PLUGIN_ROOT}/scripts/apply-workspace.sh" --home "<고객 홈>" --profile "<프로필 JSON>" --dry-run
```
선택 `workspacePath` 또는 기본 `<홈>/AI작업실`의 생성 목록과 학생 폴더와 겹치지 않음을 확인합니다. 승인 뒤 `-Apply`/`--apply`로 실행합니다. 입력/결과/원본/검토, `CLAUDE.md` 첫 줄 `@AGENTS.md`, AGENTS.md, 검토 양식, 내-업무-실행법.md를 엽니다. 기존 파일 유지 결과도 확인합니다. 설정·폴더 생성 명령을 즉석에서 만들지 않습니다.

## 창 배치·완료
Windows Terminal이 있으면 `Alt+Shift+=`로 나누고 왼쪽 Claude·오른쪽 Codex로 둡니다. 없거나 단축키가 안 되면 터미널 창 두 개를 나란히 둡니다. Mac도 창 두 개를 사용합니다. 설치된 글꼴로 한글을 확인하고 `/ek-workroom:korean-review`로 비식별 한 문장 검수를 실행합니다. 상태줄·작업실 파일·한글·스킬 호출을 확인해야 완료입니다. 새 터미널·글꼴 설치는 하지 않습니다.
