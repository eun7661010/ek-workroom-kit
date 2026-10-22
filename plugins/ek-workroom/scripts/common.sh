#!/usr/bin/env bash
# Mac Python 감지 정본. bootstrap의 내장 사본과 테스트로 일치를 확인합니다.
ek_python_install_guidance() {
  printf '%s\n' "Mac에 Apple 개발 도구가 필요합니다. 터미널에 \`xcode-select --install\`을 입력하고 뜨는 창에서 '설치'를 누르세요(약 10분, Apple 공식). 끝나면 판매자가 보낸 블록을 다시 붙여 넣으세요." >&2
}

ek_detect_python() {
  EK_PYTHON=''
  EK_PYTHON_DESCRIPTION='없음(설치 필요)'
  local candidate developer_dir version_text major minor patch label
  candidate=$(command -v python3 2>/dev/null) || return 1
  label='python3'
  if [ "$candidate" = '/usr/bin/python3' ]; then
    # CLT 미설치 Mac의 /usr/bin/python3는 실행만 해도 설치 창을 띄웁니다.
    developer_dir=$(xcode-select -p 2>/dev/null) || return 1
    candidate="$developer_dir/usr/bin/python3"
    [ -f "$candidate" ] && [ -x "$candidate" ] || return 1
    label='Apple 개발 도구'
  fi
  [ -f "$candidate" ] && [ -x "$candidate" ] || return 1
  version_text=$("$candidate" --version 2>/dev/null) || return 1
  if [[ "$version_text" =~ ^Python[[:space:]]+([0-9]+)\.([0-9]+)\.([0-9]+) ]]; then
    major=${BASH_REMATCH[1]}; minor=${BASH_REMATCH[2]}; patch=${BASH_REMATCH[3]}
  else
    return 1
  fi
  if [ "$major" -lt 3 ] || { [ "$major" -eq 3 ] && [ "$minor" -lt 9 ]; }; then
    return 1
  fi
  EK_PYTHON="$candidate"
  EK_PYTHON_DESCRIPTION="$label $major.$minor.$patch"
  export EK_PYTHON EK_PYTHON_DESCRIPTION
}

ek_require_python() {
  if ek_detect_python; then return 0; fi
  ek_python_install_guidance
  return 4
}
