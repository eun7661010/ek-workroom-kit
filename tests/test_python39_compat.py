"""Reject Python syntax and standard-library APIs unavailable on Apple CLT 3.9."""
import ast
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]


def incompatibilities(source, filename):
    try:
        tree = ast.parse(source, filename=filename, feature_version=(3, 9))
    except SyntaxError as error:
        return ['{}:{}: Python 3.9 syntax: {}'.format(filename, error.lineno, error.msg)]
    errors = []

    def reject(node, reason):
        errors.append('{}:{}: {}'.format(filename, node.lineno, reason))

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            modules = ([item.name for item in node.names] if isinstance(node, ast.Import)
                       else [node.module or ''])
            if any(name.split('.')[0] == 'tomllib' for name in modules):
                reject(node, 'tomllib requires Python 3.11')
            if (isinstance(node, ast.ImportFrom) and node.module == 'datetime'
                    and any(item.name == 'UTC' for item in node.names)):
                reject(node, 'datetime.UTC requires Python 3.11')
        if isinstance(node, ast.Attribute) and node.attr in ('bit_count', 'UTC', 'is_junction'):
            reject(node, 'standard-library attribute {} is unavailable on Python 3.9'.format(node.attr))
        if isinstance(node, ast.Call):
            if (isinstance(node.func, ast.Attribute) and node.func.attr in ('write_text', 'read_text')
                    and any(key.arg == 'newline' for key in node.keywords)):
                reject(node, 'Path.{}(newline=) is unavailable on Python 3.9'.format(node.func.attr))
            if (isinstance(node.func, ast.Name) and node.func.id == 'zip'
                    and any(key.arg == 'strict' for key in node.keywords)):
                reject(node, 'zip(strict=) requires Python 3.10')
        annotations = []
        if isinstance(node, ast.AnnAssign):
            annotations.append(node.annotation)
        elif isinstance(node, ast.arg) and node.annotation is not None:
            annotations.append(node.annotation)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.returns is not None:
            annotations.append(node.returns)
        for annotation in annotations:
            if any(isinstance(part, ast.BinOp) and isinstance(part.op, ast.BitOr)
                   for part in ast.walk(annotation)):
                reject(node, 'union annotations require typing.Optional/Union on Python 3.9')
    return errors


def main():
    # Check that the gate detects both syntax errors and APIs that ast.parse alone accepts.
    forbidden = [
        'match value:\n    case 1: pass\n',
        'def f(value: str | None): pass',
        'p.write_text("x", newline="\\n")',
        'list(zip(a, b, strict=True))', 'n.bit_count()',
        'datetime.UTC', 'from datetime import UTC', 'import tomllib',
    ]
    for source in forbidden:
        assert incompatibilities(source, 'forbidden-fixture'), source
    assert not incompatibilities('with p.open("w", newline="\\n") as f:\n    f.write("x")\n', 'allowed-fixture')
    errors = []
    paths = sorted((ROOT / 'tests').glob('*.py'))
    paths += sorted((ROOT / 'plugins/ek-workroom/scripts').glob('*.py'))
    for path in paths:
        label = path.relative_to(ROOT).as_posix()
        found = incompatibilities(path.read_text(encoding='utf-8'), label)
        errors.extend(found)
        if not found:
            print('PASS Python 3.9 syntax/API: ' + label)
    bootstrap = ROOT / 'bootstrap/bootstrap.sh'
    source = bootstrap.read_text(encoding='utf-8')
    embedded = re.findall(r"<<'PY'\n(.*?)\nPY(?:\n|$)", source, re.DOTALL)
    assert embedded, 'bootstrap Python heredoc is missing'
    for index, block in enumerate(embedded, 1):
        label = 'bootstrap/bootstrap.sh heredoc {}'.format(index)
        found = incompatibilities(block, label)
        errors.extend(found)
        if not found:
            print('PASS Python 3.9 syntax/API: ' + label)
    if errors:
        raise AssertionError('\n'.join(errors))
    print('Python 3.9 compatibility gate passed (actual Mac 3.9 execution remains a seller check).')


if __name__ == '__main__':
    main()
