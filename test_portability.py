"""Check first-run behavior without a personal catalog or sample folder."""

from pathlib import Path
from contextlib import closing
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from config import DEFAULT_DATABASE
from web_app import app


class PortabilityTests(unittest.TestCase):
    def test_scan_requires_explicit_folder(self):
        result = subprocess.run(
            [sys.executable, str(Path(__file__).parent / 'main.py'), 'scan'],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn('scan mode requires --folder', result.stderr)

    def test_default_catalog_is_shared(self):
        self.assertEqual(app.config['DATABASE'], DEFAULT_DATABASE)
        self.assertEqual(DEFAULT_DATABASE, Path(__file__).resolve().parent / 'app.db')

    def test_empty_install_and_uninitialized_database(self):
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / 'new.sqlite3'
            with patch.dict(app.config, DATABASE=database):
                response = app.test_client().get('/')
                self.assertEqual(response.status_code, 200)
                self.assertIn(b'No scan database yet', response.data)
                self.assertFalse(database.exists())
                with closing(sqlite3.connect(database)):
                    pass
                self.assertIn(b'Scan setup is needed', app.test_client().get('/').data)
                self.assertEqual(app.test_client().get('/thumbnail/1').status_code, 404)


if __name__ == '__main__':
    unittest.main()
