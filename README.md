# 원장님 AI 작업실 원격 세팅 키트 v0.1.1

80만 원 1:1 상품의 시제품입니다. 고객 본인 Claude Code가 런북을 실행하고, 판매자는 Zoom으로 감독합니다. 판매자 AI에는 고객이 직접 읽고 붙여 넣은 마스킹 진단만 전달합니다.

- [고객 D-1 안내](docs/d-1-guide-customer.md)
- [판매자 진행표](docs/session-runbook-seller.md)
- [구조·검증·릴리스 방법](docs/README.md)
- [세션 콘솔](console/session-console.md)
- [사전 설문](console/intake-survey.md)

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tests/run-all.ps1
```

기본은 미리보기이며 설치·계정 로그인·실제 사용자 설정 적용은 현장 검증 전입니다. 이 저장소의 테스트는 `.tmp/`를 가짜 홈으로 사용합니다. Mac 실행기는 기존 Python 3가 필요하며 없으면 설치 없이 멈춥니다.

검증한 로컬 키트의 마켓플레이스를 고객 홈에 등록한 뒤 설치합니다. 아래 경로에는 압축을 푼 키트 폴더의 절대 경로를 넣습니다.

```text
claude plugin marketplace add "<홈>/ek-workroom/kit-0.1.1"
claude plugin install ek-workroom@ek-workroom
```

[v0.1.1 검수 판정표](docs/review-v0.1-response.md): 원 검수24건과 추가6건의 근거·조치를 기록했습니다. 릴리스 폴더의 paste-block-windows.txt / paste-block-mac.txt가 고객 D-1 기본 경로입니다.
