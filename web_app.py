"""Read-only web viewer for the scanner's SQLite records."""

from contextlib import closing
import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from io import BytesIO
import sqlite3

from flask import Flask, abort, render_template, send_file, Response
from PIL import Image, ImageOps, UnidentifiedImageError

from config import DEFAULT_DATABASE


app = Flask(__name__)
app.config['DATABASE'] = DEFAULT_DATABASE


@app.template_filter('epoch_ms')
def format_epoch_ms(value):
    instant = datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(milliseconds=value)
    return instant.strftime('%b %d, %Y, %I:%M:%S %p UTC')


@app.template_filter('capture_date')
def format_capture_date(value):
    try:
        return datetime.strptime(value, '%Y:%m:%d %H:%M:%S').strftime('%b %d, %Y, %I:%M:%S %p')
    except (TypeError, ValueError):
        return value


@app.get('/thumbnail/<int:record_id>')
def thumbnail(record_id):
    database = Path(app.config['DATABASE']).resolve()
    if not database.is_file():
        abort(404)
    with closing(sqlite3.connect(database.as_uri() + '?mode=ro', uri=True)) as connection:
        if not connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='file_metadata'"
        ).fetchone():
            abort(404)
        row = connection.execute(
            'SELECT file_path FROM file_metadata WHERE id = ?', (record_id,)
        ).fetchone()
    if row is None:
        abort(404)
    path = Path(row[0])
    is_video = path.suffix.lower() in {'.mpg', '.mpeg', '.mp4', '.mov', '.avi', '.mkv', '.wmv'}
    candidates = [] if is_video else [path]
    if is_video and path.parent.is_dir():
        # Older cameras store a same-name JPEG or THM alongside the video.
        candidates = [item for item in path.parent.iterdir()
                      if item.stem.lower() == path.stem.lower()
                      and item.suffix.lower() in {'.jpg', '.jpeg', '.thm', '.png'}]
    for candidate in candidates:
        try:
            with Image.open(candidate) as source:
                image = ImageOps.exif_transpose(source)
                image.thumbnail((96, 72))
                output = BytesIO()
                image.convert('RGB').save(output, format='JPEG', quality=80)
            output.seek(0)
            response = send_file(output, mimetype='image/jpeg', max_age=0)
            if is_video:
                response.headers['X-Thumbnail-Source'] = 'companion-image'
            return response
        except (OSError, UnidentifiedImageError, Image.DecompressionBombError):
            continue
    label = 'VIDEO' if is_video else 'NO PREVIEW'
    return Response(
        '<svg xmlns="http://www.w3.org/2000/svg" width="96" height="72" viewBox="0 0 96 72">'
        '<rect width="96" height="72" rx="6" fill="#edf2f9"/>'
        f'<text x="48" y="40" text-anchor="middle" font-family="sans-serif" font-size="10" fill="#64748b">{label}</text></svg>',
        mimetype='image/svg+xml',
    )


@app.get('/')
def home():
    database = Path(app.config['DATABASE']).resolve()
    columns, records = [], []
    message = None
    if not database.is_file():
        message = 'No scan database yet. Run python main.py scan --folder "path/to/media", then refresh this page.'
    else:
        with closing(sqlite3.connect(database.as_uri() + '?mode=ro', uri=True)) as connection:
            connection.row_factory = sqlite3.Row
            exists = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='view' AND name='file_metadata_with_duplicates'"
            ).fetchone()
            if exists:
                cursor = connection.execute('SELECT * FROM file_metadata_with_duplicates ORDER BY file_name, file_path')
                columns = [column[0] for column in cursor.description]
                if 'date_taken_raw' in columns and 'file_size_bytes' in columns:
                    columns.remove('date_taken_raw')
                    columns.insert(columns.index('file_size_bytes') + 1, 'date_taken_raw')
                columns.remove('duplicate_count')
                columns.insert(columns.index('file_name') + 1, 'duplicate_count')
                records = cursor.fetchall()
            else:
                message = 'Scan setup is needed. Run python main.py scan --folder "path/to/media" using this database, then refresh this page.'
    return render_template('index.html', columns=columns, records=records, message=message)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='View scanned file metadata locally.')
    parser.add_argument('--database', default=str(DEFAULT_DATABASE), help='SQLite database path.')
    parser.add_argument('--port', default=9001, type=int, help='Local HTTP port (default: 9001).')
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error('--port must be between 1 and 65535')
    app.config['DATABASE'] = Path(args.database).resolve()
    app.run(host='127.0.0.1', port=args.port, debug=False)
