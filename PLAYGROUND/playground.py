"""Display / Browser-script playground — the workbench.

Tree-on-the-left, render-on-the-right SPA for iterating on the two
SMIP-side script flavors this template supports:

  * DISPLAY_SCRIPTS — node-bound. When a tree node is picked, the right
    pane mounts the matching display-script twin (if any) for that node's
    type. The twin receives the node id as `std_inputs.node_id` and
    renders against it.

  * BROWSER_SCRIPTS — standalone. Listed in a second left-pane section,
    not tied to any tree node. Clicking opens the right pane with no
    node binding.

Both kinds share the same browser-side runtime shim
(/shims/tiq_runtime.js — provides tiqContext, tiqJSHelper, apiDemoMethods,
and SMIP-only-link interception) so the local body is paste-identical to
the SMIP-side body modulo the PHP/Joomla wrapper.

The playground is also the only Flask process that ships in the template
by default — it imports the shared SMIP_API.app, attaches the two script
trees as iframe targets, and runs everything on one port. No separate
launchers per page.

Run from project root:
    python PLAYGROUND/playground.py
    # then visit http://localhost:5105/playground
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Project root so SMIP_API / SMIP_MCP / SMIP_IO / DISPLAY_SCRIPTS /
# BROWSER_SCRIPTS resolve regardless of cwd.
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from flask import send_from_directory, jsonify                  # noqa: E402

from SMIP_API.smip_flask_api import app                         # noqa: E402

# ---------------------------------------------------------------------------
# Mount the script twins on the shared Flask app.
#
# Each component module exposes `register(app)`; calling it adds its
# /display_script/<name> or /browser_script/<name> route plus the shared
# /shims/<path> route (idempotently). Order doesn't matter — registration
# is by exact (endpoint, route) tuple, so duplicates are no-ops.
# ---------------------------------------------------------------------------

from DISPLAY_SCRIPTS.application_details import component as _ds_app_details   # noqa: E402
from BROWSER_SCRIPTS.list_libraries     import component as _bs_libraries      # noqa: E402

DISPLAY_SCRIPT_MODULES = (_ds_app_details,)
BROWSER_SCRIPT_MODULES = (_bs_libraries,)

for _mod in DISPLAY_SCRIPT_MODULES + BROWSER_SCRIPT_MODULES:
    _mod.register(app)

PAGE_DIR  = Path(__file__).resolve().parent
PAGE_HTML = "playground.html"
PAGE_PATH = "/playground"
PAGE_PORT = 5105


# ---------------------------------------------------------------------------
# Display-script ↔ type binding.
#
# This was a hardcoded literal in playground.html on the first cut; promoted
# to the launcher so the UI doesn't have to know about every twin. Slice C
# of the rebuild replaces this static map with a server-side inheritance-
# aware discovery endpoint — but until then, this lives here as a single
# editable source of truth.
# ---------------------------------------------------------------------------

DISPLAY_SCRIPTS_BY_TYPE = {
    "application":                  [{"folder": "application_details", "label": "Details"}],
    "application_with_display_script": [{"folder": "application_details", "label": "Details"}],
}


# ---------------------------------------------------------------------------
# Browser-script catalog.
#
# Browser scripts are page-level, not type-bound — so the UI just needs
# a flat list. Order here is presentation order in the playground's
# left pane.
# ---------------------------------------------------------------------------

BROWSER_SCRIPTS_CATALOG = [
    {"folder": "list_libraries", "label": "List Libraries"},
]


@app.route(PAGE_PATH, endpoint="playground")
def playground_page():
    """Serve the Vue single-file playground page as a static file (no Jinja)."""
    return send_from_directory(str(PAGE_DIR), PAGE_HTML)


@app.route("/playground/config", endpoint="playground_config")
def playground_config():
    """Return the playground's runtime config as JSON.

    {
      "root_fqn":               "<PLAYGROUND_ROOT_FQN, default 'thinkiq_system'>",
      "display_scripts_by_type": { "<typeRelativeName>": [{folder,label}, ...] },
      "browser_scripts":         [{folder, label}, ...]
    }

    The UI reads this once on mount. Keep the playground HTML
    project-agnostic — anyone cloning the template adjusts script bindings
    here in playground.py (and .env for the root FQN).
    """
    return jsonify({
        "ok": True,
        "data": {
            "root_fqn":               os.environ.get("PLAYGROUND_ROOT_FQN", "thinkiq_system"),
            "display_scripts_by_type": DISPLAY_SCRIPTS_BY_TYPE,
            "browser_scripts":         BROWSER_SCRIPTS_CATALOG,
        },
    })


if __name__ == "__main__":
    print(
        f"SMIP Automation Template — playground running at "
        f"http://localhost:{PAGE_PORT}{PAGE_PATH}"
    )
    app.run(debug=True, port=PAGE_PORT)
