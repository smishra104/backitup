"""Build a source-only archive; never include local catalogs or media."""

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


SOURCE_FILES = (
    '.gitignore', 'LICENSE', 'README.md', 'requirements.txt', 'config.py',
    'main.py', 'scan.py', 'web_app.py', 'templates/index.html',
    'test_duplicates.py', 'test_portability.py', 'package_source.py',
)


def package_source():
    root = Path(__file__).resolve().parent
    output = root / 'dist' / 'backitup-source.zip'
    output.parent.mkdir(exist_ok=True)
    with ZipFile(output, 'w', compression=ZIP_DEFLATED) as archive:
        for name in SOURCE_FILES:
            archive.write(root / name, arcname=f'backitup/{name}')
    print(f'Source package created: {output}')
    return output


if __name__ == '__main__':
    package_source()
