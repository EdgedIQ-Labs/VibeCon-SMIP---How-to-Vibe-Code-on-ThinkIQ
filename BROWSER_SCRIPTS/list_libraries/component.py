"""BROWSER_SCRIPTS/list_libraries — thin register-on-call wrapper.

Mounts the list_libraries browser-script twin on a Flask app:
  GET /browser_script/list_libraries  -> local_twin.html
  GET /shims/<path>                    -> _shims/*

Called by PLAYGROUND/playground.py (and any future consumer) to attach
this twin to a specific Flask app instance. Idempotent — duplicate calls
for the same (app, name) pair are no-ops.
"""

from pathlib import Path
from BROWSER_SCRIPTS import register_browser_script


_HERE = Path(__file__).resolve().parent
_NAME = "list_libraries"


def register(app) -> None:
    """Mount /browser_script/list_libraries and shared /shims/ on app."""
    register_browser_script(app, name=_NAME, here=_HERE)
