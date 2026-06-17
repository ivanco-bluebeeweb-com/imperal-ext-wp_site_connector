"""Entrypoint — `imperal validate`/`build` and the web-kernel import `main`, not `app`.
Insert the extension directory on sys.path so the flat-layout absolute imports
(`from app import ...`, `import storage`, etc.) resolve regardless of the caller's cwd,
then import the modules so their decorators register on the same Extension instance."""
import os
import sys

_EXT_DIR = os.path.dirname(os.path.abspath(__file__))
if _EXT_DIR not in sys.path:
    sys.path.insert(0, _EXT_DIR)

from app import ext, chat  # noqa: E402,F401
