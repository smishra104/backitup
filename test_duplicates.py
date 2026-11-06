"""Exercise duplicate detection when original files are no longer available."""

from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from scan import scan
from web_app import app


class DuplicateTests(unittest.TestCase):
    def test_missing_original_and_changed_copy(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as temporary:
            folder = Path(temporary)
            database = folder / 'catalog.db'
            original = folder / 'original.txt'
            copy = folder / 'copy.txt'
            original.write_bytes(b'original content')

            def run_scan(paths):
                entries = [{'path': str(path), 'metadata': {}} for path in paths]
                with patch('scan.windows_metadata', return_value=entries):
                    scan(folder, database)

            def counts():
                with closing(sqlite3.connect(database)) as connection:
                    return dict(connection.execute(
                        'SELECT file_name, duplicate_count FROM file_metadata_with_duplicates'
                    ))

            run_scan([original])
            self.assertEqual(counts(), {'original.txt': 0})
            original.unlink()
            copy.write_bytes(b'original content')
            run_scan([copy])
            self.assertEqual(counts(), {'original.txt': 1, 'copy.txt': 1})
            run_scan([copy])
            self.assertEqual(counts(), {'original.txt': 1, 'copy.txt': 1})

            with patch.dict(app.config, DATABASE=database):
                response = app.test_client().get('/')
                self.assertEqual(response.status_code, 200)
                self.assertIn(b'1 other match', response.data)

            copy.write_bytes(b'changed content!')
            run_scan([copy])
            self.assertEqual(counts(), {'original.txt': 0, 'copy.txt': 0})
            with closing(sqlite3.connect(database)) as connection:
                indexes = connection.execute('PRAGMA index_list(file_metadata)').fetchall()
                self.assertTrue(any(row[1] == 'idx_file_metadata_content' and row[2] == 0
                                    for row in indexes))


if __name__ == '__main__':
    unittest.main()
