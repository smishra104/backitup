"""Shared, machine-independent defaults for the CLI and web viewer."""

from pathlib import Path


DEFAULT_DATABASE = Path(__file__).resolve().parent / 'app.db'
