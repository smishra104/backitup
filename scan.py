"""Scan files using Windows' built-in metadata reader (no extra packages)."""

import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import time
from datetime import datetime, timezone

from config import DEFAULT_DATABASE


# Column name, SQLite type, and Windows property name where available.
FIELDS = [
    ('file_path', 'TEXT NOT NULL UNIQUE', None),
    ('file_name', 'TEXT NOT NULL', None),
    ('file_extension', 'TEXT', None),
    ('file_type', 'TEXT', 'System.ItemTypeText'),
    ('file_size_bytes', 'INTEGER', None),
    ('file_hash_sha256', 'TEXT', None),
    ('file_created_at_ms', 'INTEGER', None),
    ('file_modified_at_ms', 'INTEGER', None),
    ('file_accessed_at_ms', 'INTEGER', None),
    ('date_taken_raw', 'TEXT', None),
    ('date_taken_offset', 'TEXT', None),
    ('date_taken_ms', 'INTEGER', None),
    ('width_pixels', 'INTEGER', 'System.Image.HorizontalSize'),
    ('height_pixels', 'INTEGER', 'System.Image.VerticalSize'),
    ('bit_depth', 'INTEGER', 'System.Image.BitDepth'),
    ('horizontal_dpi', 'REAL', 'System.Image.HorizontalResolution'),
    ('vertical_dpi', 'REAL', 'System.Image.VerticalResolution'),
    ('orientation', 'TEXT', 'System.Photo.OrientationText'),
    ('camera_make', 'TEXT', 'System.Photo.CameraManufacturer'),
    ('camera_model', 'TEXT', 'System.Photo.CameraModel'),
    ('exif_version', 'TEXT', 'System.Photo.EXIFVersion'),
    ('exposure_time_seconds', 'REAL', 'System.Photo.ExposureTime'),
    ('exposure_bias_ev', 'REAL', 'System.Photo.ExposureBias'),
    ('exposure_program', 'TEXT', 'System.Photo.ExposureProgramText'),
    ('aperture_f_number', 'REAL', 'System.Photo.FNumber'),
    ('max_aperture_apex', 'REAL', 'System.Photo.MaxAperture'),
    ('focal_length_mm', 'REAL', 'System.Photo.FocalLength'),
    ('iso_speed', 'INTEGER', 'System.Photo.ISOSpeed'),
    ('flash', 'TEXT', 'System.Photo.FlashText'),
    ('white_balance', 'TEXT', 'System.Photo.WhiteBalanceText'),
    ('metering_mode', 'TEXT', 'System.Photo.MeteringModeText'),
    ('light_source', 'TEXT', 'System.Photo.LightSource'),
    ('title', 'TEXT', 'System.Title'),
    ('subject', 'TEXT', 'System.Subject'),
    ('rating', 'TEXT', 'System.RatingText'),
    ('gps_latitude', 'REAL', 'System.GPS.LatitudeDecimal'),
    ('gps_longitude', 'REAL', 'System.GPS.LongitudeDecimal'),
    ('gps_altitude_meters', 'REAL', 'System.GPS.Altitude'),
    ('duration_seconds', 'REAL', 'System.Media.Duration'),
    ('frame_rate_fps', 'REAL', 'System.Video.FrameRate'),
    ('audio_bitrate_bps', 'INTEGER', 'System.Audio.EncodingBitrate'),
    ('video_bitrate_bps', 'INTEGER', 'System.Video.EncodingBitrate'),
    ('video_compression', 'TEXT', 'System.Video.Compression'),
    ('raw_metadata_json', 'TEXT', None),
    ('extracted_at_ms', 'INTEGER NOT NULL', None),
]


def windows_metadata(folder):
    if os.name != 'nt':
        raise RuntimeError('Metadata scanning currently requires Windows.')
    properties = [prop for _, _, prop in FIELDS if prop]
    properties.append('System.Photo.DateTaken')
    environment = os.environ.copy()
    environment['SCAN_FOLDER'] = str(folder)
    environment['SCAN_PROPERTIES'] = json.dumps(properties)
    script = r'''
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$shell = New-Object -ComObject Shell.Application
Add-Type -AssemblyName System.Drawing
$properties = ConvertFrom-Json $env:SCAN_PROPERTIES
Get-ChildItem -LiteralPath $env:SCAN_FOLDER -File -Recurse -ErrorAction Stop | ForEach-Object {
    $folder = $shell.Namespace($_.DirectoryName)
    $item = $folder.ParseName($_.Name)
    $metadata = @{}
    foreach ($property in $properties) {
        $value = $item.ExtendedProperty($property)
        if ($null -ne $value) {
            if ($value -is [datetime]) { $value = $value.ToString('o') }
            $metadata[$property] = $value
        }
    }
    # Read the original EXIF text without Windows timezone normalization.
    $image = $null
    try {
        $image = [System.Drawing.Image]::FromFile($_.FullName)
        foreach ($tag in @(
            @{id=36867; name='EXIF.DateTimeOriginal'},
            @{id=36881; name='EXIF.OffsetTimeOriginal'},
            @{id=37521; name='EXIF.SubSecTimeOriginal'}
        )) {
            if ($image.PropertyIdList -contains $tag.id) {
                $metadata[$tag.name] = [System.Text.Encoding]::ASCII.GetString(
                    $image.GetPropertyItem($tag.id).Value
                ).Trim([char]0).Trim()
            }
        }
    } catch [System.OutOfMemoryException] {
        # Non-image and unsupported image files still get filesystem records.
    } catch [System.ArgumentException] {
        # Some companion files are not supported by System.Drawing.
    } finally {
        if ($null -ne $image) { $image.Dispose() }
    }
    @{path=$_.FullName; metadata=$metadata} | ConvertTo-Json -Depth 10 -Compress
}
'''
    result = subprocess.run(
        ['powershell', '-NoProfile', '-NonInteractive', '-Command', script],
        env=environment, capture_output=True, encoding='utf-8', check=True,
    )
    return [json.loads(line) for line in result.stdout.splitlines() if line.strip()]


def capture_timestamp(metadata):
    """Convert only an original camera date with an explicit EXIF offset."""
    raw = metadata.get('EXIF.DateTimeOriginal') or None
    offset = metadata.get('EXIF.OffsetTimeOriginal') or None
    if not raw or not offset:
        return raw, offset, None
    try:
        normalized = raw.replace(':', '-', 2)
        subseconds = metadata.get('EXIF.SubSecTimeOriginal', '')
        if subseconds.isdigit():
            normalized += '.' + subseconds
        value = datetime.fromisoformat(normalized + offset)
        if value.utcoffset() is None:
            return raw, offset, None
        delta = value.astimezone(timezone.utc) - datetime(1970, 1, 1, tzinfo=timezone.utc)
        epoch_ms = (delta.days * 86400 + delta.seconds) * 1000 + delta.microseconds // 1000
        return raw, offset, epoch_ms
    except ValueError:
        return raw, offset, None


def scan(folder, database=DEFAULT_DATABASE):
    folder = Path(folder).resolve()
    if not folder.is_dir():
        raise ValueError(f'Scan folder does not exist: {folder}')
    files = windows_metadata(folder)
    columns = [name for name, _, _ in FIELDS]
    schema = ', '.join(f'{name} {kind}' for name, kind, _ in FIELDS)
    placeholders = ', '.join('?' for _ in columns)
    updates = ', '.join(f'{name}=excluded.{name}' for name in columns if name != 'file_path')
    count = 0
    connection = sqlite3.connect(database)
    try:
        with connection:
            connection.execute(f'CREATE TABLE IF NOT EXISTS file_metadata (id INTEGER PRIMARY KEY, {schema})')
            connection.execute(
                'CREATE INDEX IF NOT EXISTS idx_file_metadata_content '
                'ON file_metadata (file_size_bytes, file_hash_sha256)'
            )
            connection.execute('''
                CREATE VIEW IF NOT EXISTS file_metadata_with_duplicates AS
                SELECT file.*, (
                    SELECT COUNT(*) FROM file_metadata AS other
                    WHERE other.file_size_bytes = file.file_size_bytes
                      AND other.file_hash_sha256 = file.file_hash_sha256
                      AND file.file_hash_sha256 IS NOT NULL
                      AND file.file_hash_sha256 != ''
                      AND other.id != file.id
                ) AS duplicate_count
                FROM file_metadata AS file
            ''')
            for entry in files:
                path = Path(entry['path'])
                if path.resolve() == Path(database).resolve():
                    continue
                stat = path.stat()
                digest = hashlib.sha256()
                with path.open('rb') as source:
                    for chunk in iter(lambda: source.read(1024 * 1024), b''):
                        digest.update(chunk)
                metadata = entry['metadata']
                taken_raw, taken_offset, taken_ms = capture_timestamp(metadata)
                row = {}
                for name, kind, prop in FIELDS:
                    value = metadata.get(prop) if prop else None
                    if isinstance(value, str):
                        value = value.strip() or None
                    if value is not None and kind in ('INTEGER', 'REAL'):
                        try:
                            value = int(value) if kind == 'INTEGER' else float(value)
                        except (TypeError, ValueError):
                            value = None
                    row[name] = value
                if row['duration_seconds'] is not None:
                    row['duration_seconds'] /= 10_000_000
                if row['frame_rate_fps'] is not None:
                    row['frame_rate_fps'] /= 1000
                row.update(
                    file_path=str(path), file_name=path.name,
                    file_extension=path.suffix.lower(), file_size_bytes=stat.st_size,
                    file_hash_sha256=digest.hexdigest(),
                    file_created_at_ms=stat.st_birthtime_ns // 1_000_000,
                    file_modified_at_ms=stat.st_mtime_ns // 1_000_000,
                    file_accessed_at_ms=stat.st_atime_ns // 1_000_000,
                    date_taken_raw=taken_raw, date_taken_offset=taken_offset,
                    date_taken_ms=taken_ms,
                    raw_metadata_json=json.dumps(metadata, ensure_ascii=False),
                    extracted_at_ms=time.time_ns() // 1_000_000,
                )
                connection.execute(
                    f'INSERT INTO file_metadata ({", ".join(columns)}) VALUES ({placeholders}) '
                    f'ON CONFLICT(file_path) DO UPDATE SET {updates}',
                    [row[name] for name in columns],
                )
                count += 1
            duplicate_records = connection.execute(
                'SELECT COUNT(*) FROM file_metadata_with_duplicates WHERE duplicate_count > 0'
            ).fetchone()[0]
    finally:
        connection.close()
    print(f'Scan complete: {count} files saved to {database}.')
    print(f'Duplicate content: {duplicate_records} matching records across the catalog (size + SHA-256).')
