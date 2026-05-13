"""DISPLAY_SCRIPTS — local plain-HTML twins of the SMIP-side display scripts.

Each subdirectory is one display script. The pattern, mirrored from the
sibling SMIP browser-script library (___SMIP_SAAS_SIDE___/SMIP Display Scripts):

  DISPLAY_SCRIPTS/
    <script_name>/
      __init__.py           Import-side-effect that runs component.py.
      component.py          Thin wrapper that exposes `register(app)` — the
                            function each consumer (the PLAYGROUND launcher)
                            calls to mount this script's routes on its Flask
                            app.
      local_twin.html       Byte-identical (or as close as practical) to the
                            SMIP-side script body. Paste target lives at
                            ___SMIP_SAAS_SIDE___/SMIP Display Scripts/
                            <script_name>.html.

The browser-side runtime shim (tiq_runtime.js — provides tiqContext,
tiqJSHelper, apiDemoMethods, SMIP-only-link interception) lives at
top-level `_shims/tiq_runtime.js`, not under DISPLAY_SCRIPTS — the same
shim is consumed by both display-script twins AND browser-script twins,
so neither pattern owns it. Route wiring for /shims/<path> comes from
the top-level `_shim_routes.register_shim_routes(app)` helper.

Routes registered per call to `register_display_script(app, name, here)`:
  GET /display_script/<name>     -> <here>/local_twin.html
  GET /shims/<path:filename>     -> _shims/<filename>
                                    (idempotent across many components)

Why explicit `register(app)` instead of side-effect on import:
  The first cut of this pattern (in TrueMeter) registered display scripts
  on the API app at import time. That worked fine when only the playground
  consumed them, but a second consumer (e.g. a SPA Flask app, or this
  template's playground-vs-API split) means the same routes need to land
  on more than one app. Side-effect-on-import can't target two different
  apps. The `register(app)` form lets each caller mount on its own app
  and stays idempotent on repeat calls.
"""

from pathlib import Path
from flask import send_from_directory

from _shim_routes import register_shim_routes


def register_display_script(app, *, name: str, here: Path) -> None:
    """Register a display script's HTML + shared shim routes on `app`.

    Parameters
    ----------
    app : flask.Flask
        The Flask app to mount routes on. Each consumer brings its own.
    name : str
        Display-script identifier — both the URL segment
        (/display_script/<name>) and the folder name under DISPLAY_SCRIPTS/.
    here : pathlib.Path
        Filesystem directory containing this script's `local_twin.html`.

    Idempotent: a duplicate `register()` call for the same (app, name)
    pair is a no-op (we check view_functions before adding the rule),
    so a launcher that imports a component twice doesn't crash.
    """
    endpoint = f"display_script_{name}"
    route = f"/display_script/{name}"

    if endpoint not in app.view_functions:
        def _view(_here=here):
            return send_from_directory(str(_here), "local_twin.html")
        _view.__name__ = endpoint
        app.add_url_rule(route, endpoint=endpoint, view_func=_view)

    register_shim_routes(app)


__all__ = ["register_display_script"]
