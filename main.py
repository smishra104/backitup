import argparse
import sqlite3
import subprocess

from config import DEFAULT_DATABASE
from scan import scan


def basic():
    print('Hell World')


def db(database=DEFAULT_DATABASE):
    with sqlite3.connect(database) as connection:
        connection.execute(
            'CREATE TABLE IF NOT EXISTS db_test_table (text TEXT)'
        )
    print('db test: pass')


MODES = {
    'basic': basic,
    'db': db,
    'scan': scan,
}


def main():
    parser = argparse.ArgumentParser(description='Run the app in a selected mode.')
    parser.add_argument('mode', nargs='?', default='basic', choices=MODES)
    parser.add_argument('--folder', help='Folder to scan recursively; required for scan mode.')
    parser.add_argument('--database', default=str(DEFAULT_DATABASE), help='SQLite database path (default: app.db beside the scripts).')
    args = parser.parse_args()
    if args.mode == 'scan':
        if not args.folder:
            parser.error('scan mode requires --folder')
        try:
            scan(args.folder, args.database)
        except (OSError, ValueError, RuntimeError, sqlite3.Error, subprocess.CalledProcessError) as error:
            parser.exit(1, f'Scan failed: {error}\n')
    elif args.mode == 'db':
        db(args.database)
    else:
        MODES[args.mode]()


if __name__ == '__main__':
    main()
