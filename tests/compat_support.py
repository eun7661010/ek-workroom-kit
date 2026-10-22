"""Test fixture writers that also work with Apple's Python 3.9."""


def write_text(path, data, encoding='utf-8', newline=None):
    # Path.write_text gained newline in 3.10; file.open supports it on 3.9.
    with path.open('w', encoding=encoding, newline=newline) as stream:
        return stream.write(data)
