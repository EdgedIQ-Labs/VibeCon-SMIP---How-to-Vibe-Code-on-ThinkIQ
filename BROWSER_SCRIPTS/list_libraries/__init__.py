"""BROWSER_SCRIPTS/list_libraries — local twin package.

Importing this package runs `component.py`, which registers the Flask
routes that serve the twin.
"""
from . import component  # noqa: F401  side-effect: registers routes
