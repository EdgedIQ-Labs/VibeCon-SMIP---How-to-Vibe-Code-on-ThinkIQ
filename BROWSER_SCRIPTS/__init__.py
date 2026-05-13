"""BROWSER_SCRIPTS — local plain-HTML twins of the SMIP-side browser scripts.

Mirror of DISPLAY_SCRIPTS/ for the second SMIP script flavor. The difference:

  * Display scripts are NODE-BOUND. SMIP renders them when an instance is
    viewed, and passes the instance id as `std_inputs.node_id`. The twin
    queries against that id.

  * Browser scripts are STANDALONE pages. SMIP renders them at
    `/applications/<routing>`, with no instance binding. `std_inputs.node_id`
    is empty / absent; the twin renders whatever it wants — usually a query
    that fetches global state (a list of libraries, a dashboard, etc.).

Both share the same browser-side runtime shim (tiq_runtime.js — provides
tiqContext, tiqJSHelper, apiDemoMethods, SMIP-only-link interception),
which lives at top-level `_shims/tiq_runtime.js`. Route wiring for
/shims/<path> comes from `_shim_routes.register_shim_routes(app)`.

Each subdirectory is one browser script:

  BROWSER_SCRIPTS/
    <script_name>/
      __init__.py           Import-side-effect that runs component.py.
      component.py          Thin wrapper that exposes `register(app)`.
      local_twin.html       Byte-identical (or as close as practical) to the
                            SMIP-side script body. Paste target lives at
                            ___SMIP_SAAS_SIDE___/SMIP Browser Scripts/
                            <script_name>.html.

Routes registered per call to `register_browser_script(app, name, here)`:
  GET /browser_script/<name>     -> <here>/local_twin.html
  GET /shims/<path:filename>     -> _shims/<filename>
                                    (idempotent across many components)
"""

from pathlib import Path
from flask import send_from_directory

from _shim_routes import register_shim_routes


def register_browser_script(app, *, name: str, here: Path) -> None:
    """Register a browser script's HTML + shared shim routes on `app`.

    Parameters
    ----------
    app : flask.Flask
        The Flask app to mount routes on. Each consumer brings its own.
    name : str
        Browser-script identifier — both the URL segment
        (/browser_script/<name>) and the folder name under BROWSER_SCRIPTS/.
    here : pathlib.Path
        Filesystem directory containing this script's `local_twin.html`.

    Idempotent: a duplicate `register()` call for the same (app, name)
    pair is a no-op (we check view_functions before adding the rule),
    so a launcher that imports a component twice doesn't crash.
    """
    endpoint = f"browser_script_{name}"
    route = f"/browser_script/{name}"

    if endpoint not in app.view_functions:
        def _view(_here=here):
            return send_from_directory(str(_here), "local_twin.html")
        _view.__name__ = endpoint
        app.add_url_rule(route, endpoint=endpoint, view_func=_view)

    register_shim_routes(app)


__all__ = ["register_browser_script"]
