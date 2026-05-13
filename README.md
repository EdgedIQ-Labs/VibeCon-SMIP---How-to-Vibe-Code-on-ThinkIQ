# VibeCon-SMIP — How to Vibe-Code on ThinkIQ

A localhost-first automation template for the CESMII SMIP (ThinkIQ).
Sibling to [DevCon-SMIP](https://github.com/gregorvilkner/DevCon-SMIP---How-to-Code-on-ThinkIQ):
DevCon teaches you to code on ThinkIQ, VibeCon teaches you to vibe-code
on it.

## What you get

Three buckets of script-shaped things, each with a clear job:

1. **`SCRIPTS/`** — **local Python automation**. Modern Python on your dev
   machine, talks to SMIP over GraphQL via `SMIPMethods`. Headless,
   one-shot or batch (migrations, data fixups, model refactors).
   Intentionally has no SMIP-side counterpart — SMIP's headless-script
   runtime is behind on Python and PHP isn't a language this template
   wants to spend on. Reach for `SCRIPTS/` first when something doesn't
   have to live inside SMIP's runtime.

2. **`DISPLAY_SCRIPTS/`** ↔ **`___SMIP_SAAS_SIDE___/SMIP Display Scripts/`**
   — node-bound Vue twins. SMIP renders these when an instance is
   viewed, passing the instance id as `std_inputs.node_id`. The local
   twin renders against the same id via a runtime shim
   (`_shims/tiq_runtime.js`) so the body is paste-identical to the
   SMIP-side script.

3. **`BROWSER_SCRIPTS/`** ↔ **`___SMIP_SAAS_SIDE___/SMIP Browser Scripts/`**
   — standalone Vue twins. Page-level, not bound to any node. Same shim,
   same paste-identical contract.

Plus three shared layers:

- **`SMIP_IO/`** — transport (`SMIPClient` JWT challenge-response + GraphQL
  POST) and the high-level operations (`SMIPMethods`) that wrap it.
- **`SMIP_MCP/`** — the single source of truth for tools. One
  `TOOL_REGISTRY` entry fans out to the REST endpoint, the MCP server,
  the agentic chat tool spec, and the docs page section automatically.
- **`SMIP_API/`** — Flask surface: `/`, `/chat`, `/api/tool/<name>`,
  `/api/chat`, plus `/api/graphql` and `/api/smip_origin` for the shim.

## The playground

`PLAYGROUND/playground.py` is the one process this template ships with —
a single Flask app on port 5105 that mounts every twin (display and
browser) plus a tree-on-the-left, render-on-the-right SPA for iterating
on them. Left pane is the instance tree (rooted at `PLAYGROUND_ROOT_FQN`
from `.env`) plus a flat list of browser scripts. Right pane is either
the matching twin's iframe or a self-documenting landing pane. The
right-pane details panel has an "Export type to SMIP Exports/" button
that captures the selected node's type as JSON for source control.

Run from project root:
```
python PLAYGROUND/playground.py
# then visit http://localhost:5105/playground
```

## The opinion this template defends

Use modern Python for automation, SMIP-side scripts for things that have
to live in SMIP's runtime (UI rendering, QR routing, anything
user-clickable in the tenant). Don't pretend the headless-script surface
is where you'd start.

## Read next

- **[docs/QUICKSTART.md](docs/QUICKSTART.md)** — get from `git clone` to a
  working chat agent calling tools against your SMIP.
- **[docs/WORKFLOW.md](docs/WORKFLOW.md)** — how to use the template well.
  Bootstrapping with library exports, building tools before pages, the
  inherit-and-export workflow for SMIP types, the two-layer JS SDK
  convention.
- **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** — what's where and why.
  Reference for the tool registry mechanics, the script-flavor
  conventions, and the design choices that thread through the codebase.

## A note on adding a SMIP display script

The base ThinkIQ libraries are `locked: true`. You can't add a script
directly to a base-library type. The three-beat workaround:

1. **Derive** in your own (unlocked) library — make `Application_` (or
   similar) a sub-type of base `Application` so the derived type inherits
   the base attribute schema (Enable QR Code Routing, Routing Template,
   etc.) for free.
2. **Attach** your Display Script to the derived type and edit it in the
   SMIP IDE (or vibe-edit the localhost twin and paste).
3. **Re-type** the four shipped Application instances (Details, Model
   Explorer, Timeseries Dashboard, Trend) to your derived type so the
   script fires when they're opened.

Deleting a type cascades — instances typed as it get hard-deleted, no
prompt, no soft-delete. If you keep a second SMIP tenant (TrimTabs, a
sandbox, anything stable) as a reference mirror, you can recover by
reading the values off and recreating. SMIP doesn't give you
point-in-time recovery at the modeling layer, so an intact peer tenant
*is* the recovery surface.
