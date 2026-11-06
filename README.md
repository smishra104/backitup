# Backitup

A local file catalog that records metadata and SHA-256 hashes in SQLite, with a
Flask table viewer and duplicate-content indicators. Source files are read
without modifying their contents. Files are not copied or backed up.

## Requirements

- Windows with Windows PowerShell and Python 3.12 or newer for scanning.
- Flask and Pillow for the viewer (installed below).

Scanning uses Windows metadata APIs and System.Drawing. It does not require
Flask or Pillow. The viewer can read an existing catalog on other platforms,
but thumbnails require accessible source paths.

## Setup and usage

Run these commands from the project directory in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py scan --folder "C:\path\to\media"
.\.venv\Scripts\python.exe web_app.py
```

Open http://127.0.0.1:9001. Refresh after scanning to see updated records.
Supply the scan folder explicitly; no personal sample directory is built into
the application. Both commands default to `app.db` beside the scripts,
regardless of the working directory.

To use another database or port:

```powershell
.\.venv\Scripts\python.exe main.py scan --folder "C:\path\to\media" --database "catalog.sqlite3"
.\.venv\Scripts\python.exe web_app.py --database "catalog.sqlite3" --port 9001
```

Use the same database path for scanning and viewing. Relative custom database
paths resolve from the current working directory. The parent directory must
already exist. `--help` lists options. The original `basic` and `db` modes remain
available; `db` creates a test table.

## Stored data

The scanner recursively records every file in the selected folder, including
unsupported media and companion files. Each absolute path has one row in
`file_metadata`. Rescanning updates that row; records for unavailable files remain.
Changing the contents at a recorded path replaces that path's previous metadata;
this is a current catalog, not a version history.

Records include size, SHA-256, filesystem dates, and available photo or video
metadata. Missing values are NULL. `raw_metadata_json` preserves queried Windows
properties and original capture tags, not every embedded metadata tag.

Timestamp columns ending in `_ms` are INTEGER milliseconds since the Unix epoch
(UTC). `date_taken_raw` preserves the original EXIF camera date;
`date_taken_offset` preserves an explicit EXIF offset. `date_taken_ms` stays NULL
unless the date and offset are present and valid. Windows-normalized dates remain
in the metadata JSON. The viewer formats timestamps for reading and shows stored
epoch values on hover.

Image previews appear beside each ID. Video previews use a same-name companion
image when available. Unavailable or unsupported files show a placeholder.

## Duplicate detection

The non-unique index `idx_file_metadata_content` covers
`(file_size_bytes, file_hash_sha256)`. The `file_metadata_with_duplicates` view
adds `duplicate_count`, the number of other records with matching size and hash,
including records whose files are unavailable. Counts update with database
changes and appear beside the file name. Matching hashes provide strong evidence
of identical content; no byte-for-byte verification is performed. No files are
deleted or merged.

## Privacy and sharing

Publish the source code, requirements, templates, tests, and documentation.
Keep local databases, virtual environments, logs, and media out of distributions.
Database files are ignored by Git, but copying or zipping the entire working
directory can still include them. Catalogs contain absolute paths and potentially
sensitive capture metadata, including location if available. Reading files may
update filesystem access timestamps.

Build a source-only archive using the explicit file allowlist:

```powershell
python package_source.py
```

Share `dist/backitup-source.zip`. The package excludes databases, media, logs,
virtual environments, and Git history.

The viewer binds only to `127.0.0.1` and has no authentication. It is intended
for local desktop use. Public or shared hosting needs a separate deployment and
access-control design; the bundled Flask development server is not intended for
that use.

## Tests

```powershell
.\.venv\Scripts\python.exe -m unittest
```

The duplicate test uses temporary files and a temporary database, without any
personal media or fixed directories.

## License

GNU GPL v3. See [LICENSE](LICENSE).
