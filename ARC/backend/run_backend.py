"""PyInstaller entry point (arc_backend/__main__.py uses package-relative imports)."""
import sys

from arc_backend.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
