# Architecture

How VibeCon-SMIP is wired and why. Reference rather than narrative — dip in
for the section you need.

If you're trying to get the template running for the first time, start with
[QUICKSTART](QUICKSTART.md). If you have it running and want to know how to
work with it well, see [WORKFLOW](WORKFLOW.md).

## Architecture at a glance

```
SMIP_IO/         transport
  smip_client.py             SMIPClient — JWT challenge/response + GraphQL POST.
                             Based on the CESMII "Simple SMIP Client Example".
  smip_methods.py            SMIPMethods — high-level operations
                             (one method per business question).
  model/                     Optional: Python dataclasses for typed responses.

SMIP_MCP/        single source of truth for tools
  smip_tools.py              TOOL_REGISTRY — descriptions, params, dispatch fns.
  smip_mcp_server.py         FastMCP server exposing tools to MCP clients.
  agent_prompt.py            SYSTEM_INSTRUCTIONS shared by chat agent + MCP.

SMIP_API/        Flask surface
  smip_flask_api.py          /, /chat[/_stack/_canvas], /api/tool/<name>,
                             /api/chat, /api/graphql, /api/smip_origin.
  smip_flask_api_documentation.html      Vue docs page (TOOL_REGISTRY_PUBLIC).
  smip_chat[/_stack/_canvas].html        three chat UIs.

DISPLAY_SCRIPTS/    SMIP-side node-bound twins (mirror of SMIP Display Scripts)
  <name>/
    __init__.py              Side-effect: runs component.py.
    component.py             Exposes register(app).
    local_twin.html          Vue body; paste target is
                             ___SMIP_SAAS_SIDE___/SMIP Display Scripts/<name>.html.

BROWSER_SCRIPTS/    SMIP-side standalone twins (mirror of SMIP Browser Scripts)
  <name>/
    __init__.py
    component.py
    local_twin.html          Paste target is
                             ___SMIP_SAAS_SIDE___/SMIP Browser Scripts/<name>.html.

_shims/             shared runtime shim consumed by both twin flavors
  tiq_runtime.js             Polyfills tiqContext, tiqJSHelper,
                             apiDemoMethods, SMIP-only-link interception.

_shim_routes.py     shared shim-route helper (one /shims/<path> mount per app)

PLAYGROUND/         the workbench
  playground.py              Flask launcher on port 5105 — mounts every twin,
                             registers /playground, exposes /playground/config.
  playground.html            Vue SPA: instance tree + browser-script list,
                             iframe render pane, self-documenting landing
                             pane, "Export type" button.

SCRIPTS/         worker / automation scripts — local Python only
  <NN>_<task>.py             e.g. 01_list_libraries.py. Headless, run-and-exit.
                             No SMIP-side counterpart by design — see the
                             "opinion" section in the top-level README.

___SMIP_SAAS_SIDE___/   reference material + SMIP-side libraries
  GraphQL Schema/            Introspection export of the SMIP GraphQL API.
  SMIP Exports/              Drop-zone for SMIP library / type export JSONs.
                             The playground's "Export type" button writes here.
  SMIP JS SDK/               Generic, tenant-agnostic JS SDK (grown in this
                             repo). apiDemoMethods + apiDemoTools wrappers.
  JS SDK Template/           Domain/tenant-specific JS SDK (vendored from
                             DevCon-SMIP). Edits go upstream first.
  SMIP Display Scripts/      Paste targets for DISPLAY_SCRIPTS/ twins.
  SMIP Browser Scripts/      Paste targets for BROWSER_SCRIPTS/ twins.
```

The directional convention: data flows in via SMIP_IO, business semantics
live in SMIP_MCP's TOOL_REGISTRY (one source of truth), SMIP_API and the
twin frameworks are the surfaces. Adding a new tool means editing
`smip_tools.py` and `smip_methods.py`; everything else (REST endpoint,
OpenAI tool spec, MCP wrapper schema, docs page section) is derived.

## The tool registry

Adding a new query to the agent + REST + MCP at the same time is a
three-step job:

1. **Add the method** to `SMIPMethods` in `SMIP_IO/smip_methods.py` —
   does the GraphQL round-trip(s) and returns plain Python.
2. **Add the registry entry** in `SMIP_MCP/smip_tools.py` —
   `name / summary / description / parameters / ui / fn`. The
   `description` is what the LLM sees; the `fn` lambda dispatches to the
   SMIPMethods method. Add `"llm_exposed": False` for tools that should
   reach `/api/tool/<name>` but stay out of the chat agent's tool spec
   (e.g. mutations, bulk fetches, file-writing utilities).
3. **Add the typed MCP wrapper** in `SMIP_MCP/smip_mcp_server.py` (3
   lines) so FastMCP can build the JSON schema from the Python signature
   — only needed when `llm_exposed` is true.

Everything else is derived: the `/api/tool/<name>` endpoint picks it up
automatically, the OpenAI tool spec for `/api/chat` includes it, the
docs page renders a section for it.

### Conventions across the registry

- **Empty input means "all"** wherever it makes sense.
- **Server-side filters where possible** (PostGraphile's `*Filter` types
  expose `includesInsensitive`, `contains`, `overlaps`).
- **Flat rows over nested trees** so callers don't have to cross-reference.

## The three script flavors

VibeCon-SMIP distinguishes three kinds of "script" that play different roles:

| Where it runs | Bucket | Triggered by | When to reach for it |
| --- | --- | --- | --- |
| Your dev machine | `SCRIPTS/` | `python SCRIPTS/<NN>_<task>.py` | Migrations, model refactors, data fixups, batch operations. Modern Python, no port, no Vue. |
| Inside SMIP (browser) | `BROWSER_SCRIPTS/` ↔ `SMIP Browser Scripts/` | Open `/applications/<routing>` in SMIP | Standalone pages — dashboards, list views, anything page-level not tied to one instance. |
| Inside SMIP (browser) | `DISPLAY_SCRIPTS/` ↔ `SMIP Display Scripts/` | View an instance whose type binds this script | Per-instance views — details, edit forms, anything that needs `std_inputs.node_id`. |

What's deliberately absent: a counterpart for SMIP's **Headless Scripts**
(the third flavor in the SMIP "Add Script" dialog, run on a cron from
inside SMIP). That surface is PHP / older Python; this template's
opinion is that batch/automation work belongs in `SCRIPTS/` where the
Python is modern and the iteration loop is fast. Drop a Headless Script
into SMIP by hand if you ever need one, but don't expect the template
to scaffold for it.

## The PLAYGROUND convention

The playground is the one Flask process this template ships with. It
imports the shared `SMIP_API.app`, mounts every twin module's
`register(app)` hook, and runs on port 5105. Same-origin fetches with
relative URLs, no CORS dance, no proxy. Everything you'd want to look
at lives behind that one port.

```
python PLAYGROUND/playground.py
# then visit http://localhost:5105/playground
```

Left pane: the instance tree (sourced from `/api/tool/get_object_subtree`,
rooted at `PLAYGROUND_ROOT_FQN` from `.env`) and a flat list of browser
scripts (from `/playground/config`). Right pane: either the matching
twin's iframe or the landing pane (which doubles as inline documentation).

Adding a new twin:

1. Decide whether it's node-bound (display) or page-level (browser).
2. Create `DISPLAY_SCRIPTS/<folder>/` or `BROWSER_SCRIPTS/<folder>/` with
   `__init__.py`, `component.py`, and `local_twin.html`.
3. Add the SMIP-side paste target under `___SMIP_SAAS_SIDE___/SMIP
   Display Scripts/<folder>.html` (or `SMIP Browser Scripts/`).
4. Register the module in `PLAYGROUND/playground.py`
   (`DISPLAY_SCRIPT_MODULES` or `BROWSER_SCRIPT_MODULES`).
5. For display scripts, add a type binding to `DISPLAY_SCRIPTS_BY_TYPE`
   in the same file. For browser scripts, add a row to
   `BROWSER_SCRIPTS_CATALOG`.
6. Restart the playground.

`DISPLAY_SCRIPTS_BY_TYPE` is a hand-edited map for now. A future
iteration can replace it with on-the-fly discovery that walks the
selected type's inheritance via GraphQL and intersects with the on-disk
folder set. The render path doesn't change when that lands.

## The SCRIPTS convention

A "script" is a single runnable Python file directly under `SCRIPTS/`,
numbered for ordering:

```
SCRIPTS/
  01_migrate_units.py
  02_refactor_model.py
  03_backfill_displaynames.py
```

Each script imports `SMIPClient` (or `SMIPMethods`) from `SMIP_IO/`, does
its work, prints / logs progress, and exits. The numeric prefix is for
sort order and rough chronology, not a required execution sequence —
each script should be independently runnable and idempotent where
practical.

## The runtime shim

`_shims/tiq_runtime.js` is the small file that lets a SMIP-side display
or browser script body run unmodified on localhost. It polyfills the
SMIP runtime globals (`window.tiqContext`, `window.tiqJSHelper`,
`window.apiDemoMethods`), routes `invokeGraphQLAsync` through
`/api/graphql`, and intercepts SMIP-only `/applications/*` links on
localhost (copy-to-clipboard + toast) so they keep working when pasted
into a real SMIP browser tab. On SMIP itself the shim isn't loaded; the
SMIP runtime provides the globals natively and `/applications/*` links
follow their default behavior.

The shim lives at the top level (`_shims/`) rather than under
`DISPLAY_SCRIPTS/` or `BROWSER_SCRIPTS/` because both flavors consume it
— it isn't owned by either. `_shim_routes.py` exports the
`register_shim_routes(app)` helper that mounts `/shims/<path>` on a
Flask app idempotently; both `DISPLAY_SCRIPTS/__init__.py` and
`BROWSER_SCRIPTS/__init__.py` call it when registering a twin.

## The two-layer JS SDK on the SMIP side

`___SMIP_SAAS_SIDE___/` holds two JS SDK folders, deliberately split
along a generic/domain seam:

| Folder | Scope | Lifecycle |
| --- | --- | --- |
| `SMIP JS SDK/` | **Generic** SMIP plumbing | Grows in *this* repo. Edit here directly. |
| `JS SDK Template/` | **Domain / tenant-specific** tools | Vendored snapshot from DevCon-SMIP. Edits go upstream first. |

Both libraries use an additive-merge pattern at the top of their
`02 API Tools.html`:

```js
var apiDemoTools   = (typeof apiDemoTools   !== 'undefined') ? apiDemoTools   : [];
var apiDemoMethods = (typeof apiDemoMethods !== 'undefined') ? apiDemoMethods : {};
apiDemoTools.push( /* this library's descriptors */ );
Object.assign(apiDemoMethods, { /* this library's methods */ });
```

Whichever loads first establishes the globals; later loads merge their
contributions in. Order doesn't matter.

When a Python `SMIPMethods` method gets ported into the SMIP-side world,
it lands in `SMIP JS SDK/` (if it's a generic helper any SMIP project
would benefit from) or `JS SDK Template/` (if it's tenant-specific).

## Type / library extension and the base-library lock

The base ThinkIQ libraries are `locked: true`. You cannot mutate a
base-library type's definition (attributes, scripts, inheritance) from
outside. To bind a custom Display Script to instances of a base type:

1. **Derive** the type in your own (unlocked) library, setting
   `sub_type_of_fqn` to point at the base type. The derived type
   inherits the base attribute schema.
2. **Attach** your Display Script to the derived type.
3. **Re-type** existing instances to the derived type so the script
   fires when they're viewed.

Deleting a type is a hard cascade — instances typed as it get deleted
with no prompt. The reliable recovery surface is a peer SMIP tenant
held as a reference mirror; capture values from there and rebuild.

## Tools available today

| Tool | What it does | LLM-exposed |
| --- | --- | --- |
| `get_libraries` | Smoke-test query — every library as `{id, displayName}`. | yes |
| `get_object_subtree` | Root object + flat descendants list for a given `root_fqn` or `root_id`. Powers the playground tree. | no |
| `update_attribute` | Update one attribute by id. Used by display-script edit forms. | no |
| `export_type_to_smip_exports` | Pull a tiqType's JSON and write it to `___SMIP_SAAS_SIDE___/SMIP Exports/<fqn>.json`. | no |

`llm_exposed: False` means the tool is reachable at `/api/tool/<name>`
(the playground and twins call it directly) but excluded from the chat
agent's tool spec — the agent doesn't get blind access to mutations or
file-writing utilities.

## Key dependencies

- `flask`, `python-dotenv` — the API server.
- `openai` — Azure OpenAI for `/api/chat`.
- `requests` — `SMIPClient` HTTP transport.
- `mcp` — FastMCP server framework.
- `gunicorn`, `uvicorn` — for serving the MCP SSE app on Azure.

## Conventions that travel through the codebase

- **One process, one purpose.** The playground is the single Flask
  process. Twins mount on it via `register(app)`; no separate ports.
- **Empty input means "all".** Default pattern for filter parameters.
- **Vibe-code twins freely.** Edit `local_twin.html`, refresh the
  iframe in the playground, see real data. Paste back into SMIP when
  ready.
- **Numbered scripts under `SCRIPTS/`.** Headless run-and-exit; not
  pages, not long-running services.
- **The base library is locked.** Extend in your own library; don't
  try to mutate base types in place.
