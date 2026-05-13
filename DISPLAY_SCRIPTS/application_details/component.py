"""DISPLAY_SCRIPTS/application_details — thin register-on-call wrapper.

Mounts the application_details twin on a Flask app:
  GET /display_script/application_details   -> local_twin.html
  GET /shims/<path>                          -> DISPLAY_SCRIPTS/_shims/*

Called by PAGES/05_playground/playground.py (and any future consumer) to
attach this twin to a specific Flask app instance. Idempotent — duplicate
calls for the same (app, name) pair are no-ops.
"""

from pathlib import Path
from DISPLAY_SCRIPTS import register_display_script


_HERE = Path(__file__).resolve().parent
_NAME = "application_details"


def register(app) -> None:
    """Mount /display_script/application_details and shared /shims/ on app."""
    register_display_script(app, name=_NAME, here=_HERE)
