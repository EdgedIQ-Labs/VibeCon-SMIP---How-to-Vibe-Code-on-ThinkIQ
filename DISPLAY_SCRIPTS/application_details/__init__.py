"""DISPLAY_SCRIPTS/application_details — local twin package.

Importing this package runs `component.py`, which registers the Flask
routes that serve the twin.
"""
from . import component  # noqa: F401  side-effect: registers routes
