# Architecture

How VibeCon-SMIP is wired and why. Reference rather than narrative — dip in for
the section you need.

If you're trying to get the template running for the first time, start with
[QUICKSTART](QUICKSTART.md). If you have it running and want to know how to
work with it well, see [WORKFLOW](WORKFLOW.md).

## Architecture at a glance

```
SMIP_IO/      transport
  smip_client.py        SMIPClient — auth (JWT challenge/response) + GraphQL POST.
                        Based on the CESMII "Simple SMIP Client Example" template
                        (link in the file header).
  smip_methods.py       SMIPMethods — high-level operations (one method per business question)
  model/                Optional: Python dataclasses for typed responses (project-specific)

SMIP_MCP/     single source of truth for tools
  smip_tools.py         TOOL_REGISTRY — descriptions, params, dispatch fns
  smip_mcp_server.py    FastMCP server exposing each tool to MCP clients
  agent_prompt.py       SYSTEM_INSTRUCTIONS shared by chat agent + MCP

SMIP_API/     Flask surface
  smip_flask_api.py                   /, /chat[/_stack/_canvas], /api/tool/<name>, /api/chat
  smip_flask_api_documentation.html   Vue docs page (rendered from TOOL_REGISTRY_PUBLIC)
  smip_chat[/_stack/_canvas].html     three chat UIs

PAGES/        browser-side pages — runnable .py per page
  <NN>_<page_name>/                   one folder per page
    <page_name>.py                    standalone runner
    <page_name>.html                  Vue single-file page

SCRIPTS/      worker / automation scripts — runnable .py per task
  <NN>_<task>.py                      e.g. 01_migrate_units.py,
                                      02_refactor_model.py — one-shot
                                      or batch operations against the SMIP
                                      (migrations, model refactors, data
                                      fixups). Headless; no Vue, no Flask.

___SMIP_SAAS_SIDE___/   reference material + SMIP-side libraries
  GraphQL Schema/         introspection export of the SMIP GraphQL API
  SMIP Exports/           drop-zone for SMIP library export JSONs (type
                          libraries, script libraries) used as LLM context
  SMIP JS SDK/            generic, tenant-agnostic JS SDK — grown in this
                          repo. apiDemoMethods + apiDemoTools wrappers
                          around generic SMIP mutations/queries
                          (updateAttribute, updateObject, getTypes,
                          getObject, getEnumTypes). The home for new
                          generic SMIP plumbing.
  JS SDK Template/        domain/tenant-specific JS SDK — vendored snapshot
                          of DevCon-SMIP Topic 06 / Take 4. Per-project
                          methods live here (and merge additively into the
                          same apiDemoMethods / apiDemoTools globals).
  Sample Scripts/         vendored SMIP browser-script + display-script
                          templates — the conversion targets for PAGES.
                          Vibe-code a page in Python under PAGES/, then port
                          it back into one of these templates so it lives on
                          the SMIP side as a first-class script.
```

The directional convention: data flows in via SMIP_IO, business semantics live
in SMIP_MCP's TOOL_REGISTRY (one source of truth), and SMIP_API + PAGES are the
surfaces. Adding a new tool means editing `smip_tools.py` and `smip_methods.py`;
everything else (REST endpoint, OpenAI tool spec, MCP wrapper schema, docs page
section) is derived.

## The tool registry

Adding a new query to the agent + REST + MCP at the same time is a three-step
job:

1. **Add the method** to `SMIPMethods` in `SMIP_IO/smip_methods.py` — does the
   GraphQL round-trip(s) and returns plain Python (list of dicts is the
   standard shape).
2. **Add the registry entry** in `SMIP_MCP/smip_tools.py` —
   `name / summary / description / parameters / ui / fn`. The `description`
   is what the LLM sees; the `fn` lambda dispatches to the SMIPMethods
   method.
3. **Add the typed MCP wrapper** in `SMIP_MCP/smip_mcp_server.py` (3 lines)
   so FastMCP can build the JSON schema from the Python signature.

Everything else is derived: the `/api/tool/<name>` endpoint picks it up
automatically, the OpenAI tool spec for `/api/chat` includes it, the docs
page renders a section for it, and `attach_docstrings_to(SMIPMethods)` would
copy the description onto the method's `__doc__` for IDE tooltips.

### Conventions across the registry

- **Empty input means "all"** wherever it makes sense. Keeps callers from
  threading the needle of "what's the magic word for unfiltered?".
- **Server-side filters where possible.** PostGraphile's `*Filter` types
  expose `includesInsensitive`, `contains`, `overlaps` and friends — push
  the filter to the GraphQL layer rather than fetching everything and
  trimming client-side.
- **Flat rows over nested trees.** A row should be self-contained where
  practical so callers don't have to cross-reference a tree to get useful
  results.

## The PAGES convention

A "page" is a folder under `PAGES/` containing HTML + Vue + a tiny Python
launcher. Each page is its own runnable entry point:

```
python PAGES/<NN>_<page_name>/<page_name>.py     # boots its own port with the page mounted
```

The launcher pattern: add the project root to `sys.path`, import `app` from
`SMIP_API.smip_flask_api`, decorate it with `@app.route(PAGE_PATH,
endpoint=...)`, and run the combined app on its own port. Same-origin fetches
with relative URLs, no CORS dance, no proxy. Each page run is its own
process, so a buggy page can't break sibling pages.

Worked example: `PAGES/01_list_libraries/`. Two files — `list_libraries.py`
(launcher on port 5101) and `list_libraries.html` (Vue 3 from CDN, fetches
`/api/tool/get_libraries`, renders an `id` / `displayName` table).

To add a new page: copy an existing one, rename the folder + Python file,
update the route, and you're off.

## The SCRIPTS convention

A "script" is a single runnable Python file directly under `SCRIPTS/`,
numbered for ordering:

```
SCRIPTS/
  01_migrate_units.py
  02_refactor_model.py
  03_backfill_displaynames.py
```

Scripts are for **worker / automation** use cases — migrations, model
refactors, data fixups, one-off batch operations. They are headless: no Vue,
no Flask, no port. Each script imports `SMIPClient` (or `SMIPMethods`) from
`SMIP_IO/`, does its work, prints/logs progress, and exits.

Worked example: `SCRIPTS/01_list_libraries.py`. Builds a `SMIPMethods` around
a `SMIPClient`, calls `get_libraries()`, prints `id  displayName` rows, exits
0/non-zero so it can be wired into a pipeline.

The numeric prefix is just for sort order and rough chronology — it isn't a
required execution sequence (each script should be independently runnable
and idempotent where practical). To add a new script: pick the next number,
drop in a `.py`, import what you need from `SMIP_IO`, and run it.

## Tools available today

| Tool                          | What it does                                                                                                |
| ----------------------------- | ----------------------------------------------------------------------------------------------------------- |
| `get_libraries`               | Smoke-test query — every library as `{id, displayName}`. No parameters.                                     |

The starter ships exactly one tool — `get_libraries`, the smoke test —
on purpose. Add project-specific tools as you go; the
[QUICKSTART](QUICKSTART.md) step 5 walkthrough builds the first one
from a single LLM prompt against your library export. See
[WORKFLOW](WORKFLOW.md) for the recommended way to grow this list.

## The two-layer JS SDK on the SMIP side

`___SMIP_SAAS_SIDE___/` holds two JS SDK folders, deliberately split along
a generic/domain seam:

| Folder            | Scope                              | Lifecycle                                                    |
| ----------------- | ---------------------------------- | ------------------------------------------------------------ |
| `SMIP JS SDK/`    | **Generic** SMIP plumbing          | Grows in *this* repo. Edit here directly.                    |
| `JS SDK Template/`| **Domain / tenant-specific** tools | Vendored snapshot from DevCon-SMIP. Edits go upstream first. |

The split mirrors the Python side:

- `SMIP JS SDK/` is the JS analogue of the generic helpers on `SMIPClient`
  and `SMIPMethods` (low-level GraphQL wrappers like `updateAttribute`,
  `updateObject`, `getTypes`, `getObject`, `getEnumTypes`) — things that
  are useful on every tenant, regardless of the model.
- `JS SDK Template/` is the JS analogue of project-specific methods on
  `SMIPMethods` (`get_libraries`, `get_quantities_with_units`, …) — built
  for a particular tenant's vocabulary.

Both libraries use the same **additive merge pattern** at the top of their
`02 API Tools.html`:

```js
var apiDemoTools   = (typeof apiDemoTools   !== 'undefined') ? apiDemoTools   : [];
var apiDemoMethods = (typeof apiDemoMethods !== 'undefined') ? apiDemoMethods : {};
apiDemoTools.push( /* this library's descriptors */ );
Object.assign(apiDemoMethods, { /* this library's methods */ });
```

Whichever loads first establishes the globals; later loads merge their
contributions in. A consumer SMIP script does two `includeScript` calls —
one for `smip_js_sdk.api_tools`, one for the tenant SDK — and ends up with
both sets of methods on a single `apiDemoMethods` namespace and both sets
of descriptors on a single `apiDemoTools` catalog. Order doesn't matter.

**Why this matters for the round-trip.** When you port a Python
`SMIPMethods` method into the SMIP-side world (WORKFLOW step 5), it lands
in one of these two folders depending on what it is:

- A new generic helper that any SMIP project would benefit from →
  `SMIP JS SDK/` (and grows the in-repo generic surface).
- A tenant-specific method tied to your library's types and attributes →
  `JS SDK Template/` (and stays tenant-shaped).

Over time, `SMIP JS SDK/` becomes the JS-side counterpart of the generic
parts of `SMIP_IO/smip_methods.py`, and `JS SDK Template/` becomes the
counterpart of the tenant-specific parts.

## Sample SMIP browser scripts (vendored)

Under `___SMIP_SAAS_SIDE___/Sample Scripts/`:

| File                          | Upstream (DevCon-SMIP, Part I / Topic 01)                                           | What it does                                                  |
| ----------------------------- | ----------------------------------------------------------------------------------- | ------------------------------------------------------------- |
| `sample_browser_script.html`  | `02 Template with Vue GraphQL Context.php`                                          | Lists every `quantity` and its `measurementUnits`             |
| `sample_display_script.html`  | `02.2 Display Script Template with Vue GraphQL Context.php`                         | Renders the instance at `context.std_inputs.node_id` + children |

Both files carry their upstream URL in a header comment. The `.html` extension
is for editor convenience — the contents are SMIP-runtime templates, not
browser-loadable HTML. **Edits go upstream first, then re-vendor here.**

These files are the **conversion targets** for the `PAGES/` workflow — see
[WORKFLOW](WORKFLOW.md) for how the round-trip back to SMIP-side scripts works.

Upstream repo: <https://github.com/gregorvilkner/DevCon-SMIP---How-to-Code-on-ThinkIQ>

## Repository layout

```
.
├── README.md                       # high-level intro + pointers
├── docs/
│   ├── QUICKSTART.md               # step-by-step getting started
│   ├── WORKFLOW.md                 # recommended workflow / best practices
│   └── ARCHITECTURE.md             # this file
├── requirements.txt                # union of every surface's deps
├── .env / .env.example             # AZURE_OPENAI_* for /api/chat
├── .gitignore                      # ignores .env, __pycache__, .venv, etc.
│
├── SMIP_IO/                        # transport
│   ├── smip_client.py
│   ├── smip_methods.py
│   ├── model/                      # optional: typed dataclasses (project-specific)
│   ├── config.json (gitignored)
│   └── config.example.json
│
├── SMIP_MCP/                       # single source of truth for tools
│   ├── smip_tools.py               # TOOL_REGISTRY + derived OPENAI_TOOLS / make_dispatch
│   ├── smip_mcp_server.py          # FastMCP stdio + SSE entry points
│   └── agent_prompt.py             # SYSTEM_INSTRUCTIONS
│
├── SMIP_API/                       # Flask app
│   ├── smip_flask_api.py
│   └── smip_flask_api_documentation.html, smip_chat[/_stack/_canvas].html
│
├── PAGES/                          # one folder per browser-side page
│   └── 01_list_libraries/          #   sample page — lists libraries
│       ├── list_libraries.py       #     launcher (port 5101, /list_libraries)
│       └── list_libraries.html     #     Vue page (calls /api/tool/get_libraries)
│
├── SCRIPTS/                        # one runnable .py per worker/automation task
│   └── 01_list_libraries.py        #   sample script — prints every library
│
└── ___SMIP_SAAS_SIDE___/           # SMIP-side reference material + libraries
    ├── GraphQL Schema/             #   introspection export of the SMIP GraphQL API
    ├── SMIP Exports/               #   drop-zone for SMIP library export JSONs
    │                               #   (type libraries / script libraries used as LLM context)
    ├── SMIP JS SDK/                #   GENERIC, tenant-agnostic JS SDK — grown in this repo
    │                               #   apiDemoMethods + apiDemoTools wrappers around generic
    │                               #   SMIP mutations/queries (updateAttribute, updateObject,
    │                               #   getTypes, getObject, getEnumTypes). Edit here directly.
    ├── JS SDK Template/            #   DOMAIN/TENANT-SPECIFIC JS SDK
    │                               #   vendored snapshot of DevCon-SMIP Topic 06 / Take 4
    │                               #   (https://github.com/gregorvilkner/DevCon-SMIP---How-to-Code-on-ThinkIQ)
    │                               #   edits go upstream first, then re-vendor
    └── Sample Scripts/             #   vendored SMIP browser-script samples
                                    #   (Joomla/PHP templates rendered by the SMIP runtime)
                                    #   sample_browser_script.html  — Topic 01 / 02   "Template with Vue GraphQL Context"
                                    #   sample_display_script.html  — Topic 01 / 02.2 "Display Script Template with Vue GraphQL Context"
                                    #   upstream: github.com/gregorvilkner/DevCon-SMIP---How-to-Code-on-ThinkIQ
```

## Key dependencies

- `flask`, `python-dotenv` — the API server
- `openai` — Azure OpenAI for `/api/chat`
- `requests` — SMIPClient HTTP transport
- `mcp` — FastMCP server framework
- `gunicorn`, `uvicorn` — for serving the MCP SSE app on Azure

## Conventions that travel through the codebase

- **One process, one purpose.** SMIP_API runs the backend; each page py
  runs its own combined process for that page.
- **Empty input means "all".** The default pattern for filter parameters.
- **Vibe-code pages freely.** Pages live under `PAGES/`, each in its own
  process when run, using the standalone launcher pattern. The backend is
  unaffected by what they do.
- **Numbered scripts under `SCRIPTS/`.** Worker / automation tasks live as
  `01_do_this.py`, `02_do_that.py` — one-shot or batch operations like
  migrations or model refactors. Headless, run-and-exit; not pages, not
  long-running services.
