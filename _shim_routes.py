"""Shared shim-route registration for both DISPLAY_SCRIPTS and BROWSER_SCRIPTS.

Both kinds of SMIP-side script twin consume the same browser-side runtime
shim — tiq_runtime.js provides tiqContext / tiqJSHelper / apiDemoMethods /
SMIP-only-link interception for whichever twin happens to be loaded. The
shim itself lives at top-level `_shims/tiq_runtime.js` (not under either
DISPLAY_SCRIPTS/ or BROWSER_SCRIPTS/) precisely so neither pattern owns it.

`register_shim_routes(app)` is idempotent per Flask app instance — a
sentinel attribute on the app prevents Flask's double-registration error
when both DISPLAY_SCRIPTS and BROWSER_SCRIPTS call it during boot.
"""

from pathlib import Path
from flask import send_from_directory


_SHIMS_DIR = Path(__file__).resolve().parent / "_shims"


def _serve_shim(filename: str):
    """Serve any file under <project_root>/_shims/ as a static asset."""
    return send_from_directory(str(_SHIMS_DIR), filename)


def register_shim_routes(app) -> None:
    """Register the shared /shims/<path> route. Idempotent per app.

    The sentinel attribute on the app keeps repeat calls from triggering
    Flask's double-registration error. Each Flask app instance gets its
    own sentinel — registering on more than one app inside the same
    process is fine.
    """
    if getattr(app, "_shim_routes_registered", False):
        return
    app.add_url_rule(
        "/shims/<path:filename>",
        endpoint="shim_routes",
        view_func=_serve_shim,
    )
    app._shim_routes_registered = True


__all__ = ["register_shim_routes"]
