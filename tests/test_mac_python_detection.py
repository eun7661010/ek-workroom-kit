"""Exercise Mac detection without invoking the real /usr/bin/python3 stub."""
import hashlib
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import zipfile

from compat_support import write_text


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'plugins/ek-workroom/scripts'
GUIDANCE = ("Mac에 Apple 개발 도구가 필요합니다. 터미널에 `xcode-select --install`을 입력하고 "
            "뜨는 창에서 '설치'를 누르세요(약 10분, Apple 공식). "
            "끝나면 판매자가 보낸 블록을 다시 붙여 넣으세요.")


def quote(path):
    return shlex.quote(path.as_posix() if isinstance(path, Path) else str(path))


def main():
    run = Path(sys.argv[1]).resolve() / 'mac-python-detection'
    assert run.is_relative_to(ROOT / '.tmp'), 'Tests must stay under repository .tmp.'
    run.mkdir(parents=True)
    bash = shutil.which('bash')
    assert bash, 'Bash is required for Mac detection regression tests.'
    common = (SCRIPTS / 'common.sh').read_text(encoding='utf-8')
    bootstrap = (ROOT / 'bootstrap/bootstrap.sh').read_text(encoding='utf-8')
    embedded = bootstrap.split('# BEGIN MAC PYTHON COMMON\n', 1)[1].split('# END MAC PYTHON COMMON\n', 1)[0]
    assert embedded == common, 'Standalone bootstrap detection must match common.sh exactly.'
    print('PASS bootstrap and every wrapper share one Mac detection implementation')
    archive = run / 'sample.zip'
    with zipfile.ZipFile(archive, 'w') as output:
        output.writestr('sample.txt', 'No install is performed.')
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()

    def fixture(name, version='3.9.6', clt=True, homebrew=False, missing_binary=False):
        case = run / name
        case.mkdir()
        log = case / 'python-executions.log'
        developer = case / 'Apple Developer Tools'
        candidate = (case / 'homebrew/bin/python3' if homebrew else developer / 'usr/bin/python3')
        candidate.parent.mkdir(parents=True)
        if not missing_binary:
            write_text(candidate,
                       '#!/usr/bin/env bash\n'
                       'printf "%s\\n" "candidate:$*" >> ' + quote(log) + '\n'
                       'if [ "$1" = "--version" ]; then printf "%s\\n" ' + quote('Python ' + version) + '; exit 0; fi\n'
                       'exec ' + quote(Path(sys.executable)) + ' "$@"\n', newline='\n')
            candidate.chmod(0o755)
        envfile = case / 'fake-environment.sh'
        command_path = candidate.as_posix() if homebrew else '/usr/bin/python3'
        write_text(envfile,
                   'command() { if [ "$#" -eq 2 ] && [ "$1" = "-v" ] && [ "$2" = "python3" ]; then '
                   'printf "%s\\n" ' + quote(command_path) + '; else builtin command "$@"; fi; }\n'
                   'xcode-select() { printf "%s\\n" "xcode-select:$*" >> ' + quote(log) + '; '
                   + ('printf "%s\\n" ' + quote(developer) if clt else 'return 2') + '; }\n'
                   # Any accidental execution of Apple's launcher is recorded and rejected.
                   '/usr/bin/python3() { printf "%s\\n" "FORBIDDEN_APPLE_STUB:$*" >> ' + quote(log) + '; return 99; }\n',
                   newline='\n')
        env = dict(os.environ, BASH_ENV=envfile.as_posix(), PYTHONDONTWRITEBYTECODE='1',
                   PYTHONIOENCODING='utf-8', HOME=(case / 'home').as_posix())
        return case, candidate, log, env

    def invoke(args, env):
        return subprocess.run([bash] + args, env=env, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, encoding='utf-8', timeout=30)

    for name, version, clt, homebrew, expected in [
            ('homebrew', '3.15.0', False, True, True),
            ('apple-clt', '3.9.6', True, False, True),
            ('no-clt', '3.9.6', False, False, False),
            ('old-homebrew', '3.8.20', True, True, False),
            ('old-clt', '3.8.20', True, False, False)]:
        case, candidate, log, env = fixture(name, version, clt, homebrew)
        result = invoke(['-c', 'source ' + quote(SCRIPTS / 'common.sh') + '\n'
                         'if ek_require_python; then printf "RESULT:%s|%s\\n" "$EK_PYTHON" "$EK_PYTHON_DESCRIPTION"; '
                         'else exit $?; fi'], env)
        assert result.returncode == (0 if expected else 4), (name, result.stdout, result.stderr)
        recorded = log.read_text(encoding='utf-8') if log.exists() else ''
        assert 'FORBIDDEN_APPLE_STUB' not in recorded, (name, recorded)
        if expected:
            label = ('python3 ' if homebrew else 'Apple 개발 도구 ') + version
            assert 'RESULT:' + candidate.as_posix() + '|' + label in result.stdout
            assert 'candidate:--version' in recorded
            if homebrew:
                assert 'xcode-select:' not in recorded
        else:
            assert GUIDANCE in result.stderr, (name, result.stderr)
            if not clt:
                assert 'candidate:' not in recorded, recorded
        print('PASS Mac python3 detection: ' + name + ' (Apple launcher executed 0 times)')

    # xcode-select succeeding is insufficient if its developer directory lacks python3.
    case, candidate, log, env = fixture('clt-missing-binary', missing_binary=True)
    result = invoke(['-c', 'source ' + quote(SCRIPTS / 'common.sh') + '; ek_require_python'], env)
    assert result.returncode == 4 and GUIDANCE in result.stderr
    assert 'FORBIDDEN_APPLE_STUB' not in log.read_text(encoding='utf-8')
    print('PASS CLT path without actual executable stops without launching Apple stub')

    case, candidate, log, env = fixture('bootstrap-no-clt', clt=False)
    for mode in ('--dry-run', '--apply'):
        result = invoke([str(ROOT / 'bootstrap/bootstrap.sh'), '--source', str(archive),
                         '--expected-sha256', digest, '--home', str(case / 'home'), mode], env)
        assert result.returncode == 4 and GUIDANCE in result.stderr, (mode, result.stdout, result.stderr)
        assert not (case / 'home').exists(), 'Missing Python must stop before filesystem preparation.'
    assert 'candidate:' not in log.read_text(encoding='utf-8')
    assert 'FORBIDDEN_APPLE_STUB' not in log.read_text(encoding='utf-8')
    print('PASS bootstrap DryRun/Apply: exit 4, full Korean guidance, no Python execution or writes')

    for wrapper in sorted(SCRIPTS.glob('*.sh')):
        if wrapper.name == 'common.sh':
            continue
        source = wrapper.read_text(encoding='utf-8')
        assert 'source "$script_dir/common.sh"' in source, wrapper.name
        result = invoke([str(wrapper)], env)
        if wrapper.name == 'statusline.sh':
            assert result.returncode == 0 and result.stdout.strip() == 'AI 작업실' and not result.stderr
        else:
            assert result.returncode == 4 and GUIDANCE in result.stderr, (wrapper.name, result.stdout, result.stderr)
            if wrapper.name == 'ek-diag.sh':
                assert 'python3: 없음(설치 필요)' in result.stdout
        print('PASS missing Python wrapper: ' + wrapper.name)
    recorded = log.read_text(encoding='utf-8')
    assert 'FORBIDDEN_APPLE_STUB' not in recorded and 'candidate:' not in recorded, recorded

    case, candidate, log, env = fixture('bootstrap-clt')
    result = invoke([str(ROOT / 'bootstrap/bootstrap.sh'), '--source', str(archive),
                     '--expected-sha256', digest, '--home', str(case / 'home'), '--dry-run'], env)
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert 'python3: Apple 개발 도구 3.9.6' in result.stdout, result.stdout
    assert not (case / 'home/ek-workroom/kit-0.2.3').exists()
    print('PASS bootstrap DryRun shows selected Apple developer Python version')
    print('Mac python3 detection regression passed (no real Mac developer-tool launcher invoked).')


if __name__ == '__main__':
    main()
