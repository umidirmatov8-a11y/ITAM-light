"""Wazuh Security Analyzer - application entry point (GUI by default, see ``--help``)."""

import multiprocessing
import sys

from app.cli import main

if __name__ == "__main__":
    multiprocessing.freeze_support()  # required for PyInstaller on Windows
    sys.exit(main())
